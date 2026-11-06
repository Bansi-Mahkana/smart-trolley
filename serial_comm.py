import json
import logging
import threading
import time

try:
    import serial
except ImportError:
    serial = None

from config import Config

logger = logging.getLogger(__name__)


class SerialCommunicator:
    """Single-owner serial reader/writer for the Arduino trolley controller."""

    def __init__(self, app=None):
        self.app = app
        self.serial_conn = None
        self.running = False
        self.thread = None
        self.connected = False
        self._lock = threading.RLock()
        self._write_lock = threading.Lock()
        self.weight = 0.0
        self.ir_state = 'clear'

    def init_app(self, app):
        self.app = app

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.running = True
        self.thread = threading.Thread(target=self._read_serial, name='ArduinoSerialReader', daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        with self._write_lock:
            if self.serial_conn:
                try:
                    self.serial_conn.close()
                except Exception:
                    pass
                self.serial_conn = None
            self.connected = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2)

    def is_connected(self):
        return bool(self.connected and self.serial_conn and self.serial_conn.is_open)

    def get_trolley_status(self):
        return 'connected' if self.is_connected() else 'disconnected'

    def get_weight(self):
        with self._lock:
            return self.weight

    def get_ir_state(self):
        with self._lock:
            return self.ir_state

    def send_command(self, command):
        """Write a newline-delimited JSON command without interleaving bytes."""
        if not isinstance(command, dict):
            return False
        packet = (json.dumps(command, separators=(',', ':')) + '\n').encode('utf-8')
        with self._write_lock:
            if not self.is_connected():
                return False
            try:
                self.serial_conn.write(packet)
                self.serial_conn.flush()
                return True
            except Exception as exc:
                self.connected = False
                logger.warning('Arduino write failed: %s', exc)
                return False

    def set_led_state(self, state):
        return self.send_command({'command': 'led', 'state': state})

    def _dispatch_to_flask(self, endpoint, payload):
        """Deliver telemetry to Flask in-process; no second process/serial reader."""
        if self.app is None:
            return
        try:
            with self.app.test_client() as client:
                response = client.post(endpoint, json=payload)
                if response.status_code >= 400:
                    logger.warning('Arduino event rejected by %s (%s)', endpoint, response.status_code)
        except Exception as exc:
            logger.warning('Could not deliver Arduino event to Flask: %s', exc)

    def _connect(self):
        if serial is None:
            logger.error('pyserial is not installed')
            return False
        try:
            # Opening the Mega serial port resets the board; allow its bootloader to finish.
            self.serial_conn = serial.Serial(
                port=Config.SERIAL_PORT,
                baudrate=Config.SERIAL_BAUD,
                timeout=Config.SERIAL_TIMEOUT,
                write_timeout=1
            )
            time.sleep(2.0)
            self.connected = True
            return True
        except Exception as exc:
            self.serial_conn = None
            self.connected = False
            logger.warning('Arduino serial connection unavailable: %s', exc)
            return False

    def _read_serial(self):
        while self.running:
            if not self.is_connected():
                self._connect()
                if not self.is_connected():
                    time.sleep(2)
                    continue
            try:
                raw = self.serial_conn.readline()
                if not raw:
                    continue
                try:
                    payload = json.loads(raw.decode('utf-8', errors='ignore').strip())
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                packet_type = payload.get('type')
                if packet_type == 'rfid':
                    uid = str(payload.get('uid', '')).strip().upper()
                    if uid:
                        payload['uid'] = uid
                        self._dispatch_to_flask('/api/scan', payload)
                elif packet_type == 'weight':
                    try:
                        value = float(payload.get('value'))
                        if value == value and abs(value) != float('inf'):
                            with self._lock:
                                self.weight = round(value, 2)
                            self._dispatch_to_flask('/api/weight', {'value': value})
                    except (TypeError, ValueError):
                        continue
                elif packet_type == 'ir':
                    state = str(payload.get('state', 'clear'))
                    with self._lock:
                        self.ir_state = state
            except Exception as exc:
                logger.warning('Arduino serial read interrupted: %s', exc)
                self.connected = False
                try:
                    if self.serial_conn:
                        self.serial_conn.close()
                except Exception:
                    pass
                self.serial_conn = None
                time.sleep(1)


serial_communicator = SerialCommunicator()
