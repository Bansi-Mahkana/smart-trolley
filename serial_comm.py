import json
import logging
import threading
import time
import urllib.request
try:
    import serial
except ImportError:
    serial = None

from config import Config

logger = logging.getLogger(__name__)


class SerialCommunicator:
    """
    Handles background serial communication with Arduino hardware
    (RFID-RC522, HX711 Load Cell, IR Obstacle Sensor, Buzzer, LEDs, Servo).
    """

    def __init__(self, app=None):
        self.app = app
        self.serial_conn = None
        self.running = False
        self.thread = None
        self.connected = False

        self._lock = threading.Lock()
        self.weight = 0.0
        self.ir_state = 'clear'

    def init_app(self, app):
        """Allows binding the Flask app after instantiation."""
        self.app = app

    def start(self):
        """Starts a daemon background thread for continuous serial reading."""
        if self.thread is not None and self.thread.is_alive():
            logger.info("SerialCommunicator background thread is already running.")
            return

        self.running = True
        self.thread = threading.Thread(
            target=self._read_serial,
            name="SerialReaderThread",
            daemon=True
        )
        self.thread.start()
        logger.info("SerialCommunicator background thread started.")

    def stop(self):
        """Stops the serial reading thread and closes the serial port."""
        self.running = False
        if self.serial_conn:
            try:
                if self.serial_conn.is_open:
                    self.serial_conn.close()
            except Exception as e:
                logger.error("Error closing serial port: %s", e)
            finally:
                self.serial_conn = None
                self.connected = False

        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.5)
        logger.info("SerialCommunicator stopped.")

    def _read_serial(self):
        """
        Background loop reading incoming serial frames, parsing JSON packets,
        and forwarding them to app routes or shared internal state.
        """
        if serial is None:
            logger.info("pyserial is not installed; hardware serial loop is inactive.")
            while self.running:
                time.sleep(1)
            return

        while self.running:
            # Reconnection logic if disconnected
            if not self.serial_conn or not self.serial_conn.is_open:
                try:
                    self.serial_conn = serial.Serial(
                        port=Config.SERIAL_PORT,
                        baudrate=Config.SERIAL_BAUD,
                        timeout=Config.SERIAL_TIMEOUT
                    )
                    self.connected = True
                    logger.info("Serial port '%s' connected successfully at %d baud.", Config.SERIAL_PORT, Config.SERIAL_BAUD)
                except (serial.SerialException, OSError) as e:
                    self.connected = False
                    self.serial_conn = None
                    if Config.DEMO_MODE:
                        logger.warning("Serial port '%s' unavailable (%s). Continuing in DEMO_MODE.", Config.SERIAL_PORT, e)
                    else:
                        logger.warning("Could not open serial port '%s': %s. Will retry...", Config.SERIAL_PORT, e)

                    # Pause before attempting reconnection so CPU is not saturated
                    for _ in range(50):
                        if not self.running:
                            return
                        time.sleep(0.1)
                    continue

            # Read and process lines
            try:
                raw_bytes = self.serial_conn.readline()
                if not raw_bytes:
                    continue

                line_str = raw_bytes.decode('utf-8', errors='ignore').strip()
                if not line_str:
                    continue

                try:
                    payload = json.loads(line_str)
                except json.JSONDecodeError:
                    logger.debug("Received non-JSON serial line: %s", line_str)
                    continue

                msg_type = payload.get('type')

                if msg_type == 'rfid':
                    uid = payload.get('uid')
                    if uid:
                        logger.info("RFID detected from hardware: %s", uid)
                        self._dispatch_rfid_scan(payload)

                elif msg_type == 'weight':
                    try:
                        val = float(payload.get('value', 0.0))
                        with self._lock:
                            self.weight = round(val, 2)
                    except (ValueError, TypeError):
                        pass

                elif msg_type == 'ir':
                    state = payload.get('state', 'clear')
                    with self._lock:
                        self.ir_state = str(state)

                else:
                    logger.debug("Unknown serial packet type: %s", payload)

            except (serial.SerialException, OSError) as e:
                logger.warning("Serial connection interrupted: %s. Resetting connection.", e)
                self.connected = False
                if self.serial_conn:
                    try:
                        self.serial_conn.close()
                    except Exception:
                        pass
                    self.serial_conn = None
                time.sleep(1.0)
            except Exception as e:
                logger.error("Unexpected error in serial read loop: %s", e)
                time.sleep(0.5)

    def _dispatch_rfid_scan(self, payload):
        """
        Dispatches scanned RFID data to the Flask /api/scan endpoint.
        Uses in-process Flask test_client if app context is available;
        falls back to localhost HTTP POST.
        """
        delivered = False

        # Attempt 1: Direct in-process Flask test_client dispatch
        if self.app:
            try:
                with self.app.test_client() as client:
                    resp = client.post('/api/scan', json=payload)
                    logger.info("RFID scan posted to /api/scan via test_client (status %d)", resp.status_code)
                    delivered = True
            except Exception as e:
                logger.warning("In-process dispatch to /api/scan failed: %s", e)

        # Attempt 2: Localhost HTTP POST fallback
        if not delivered:
            try:
                req_data = json.dumps(payload).encode('utf-8')
                req = urllib.request.Request(
                    f'http://127.0.0.1:{Config.PORT}/api/scan',
                    data=req_data,
                    headers={'Content-Type': 'application/json'},
                    method='POST'
                )
                with urllib.request.urlopen(req, timeout=2.0) as resp:
                    logger.info("RFID scan posted to /api/scan via HTTP (status %d)", resp.status)
            except Exception as e:
                logger.warning("HTTP fallback dispatch to /api/scan failed: %s", e)

    def send_command(self, command):
        """
        Sends a JSON command to Arduino (e.g., servo unlock, buzzer beeps, LED triggers).

        :param command: dict or JSON-serializable object
        :return: True if command was written or handled in DEMO_MODE, False otherwise
        """
        if isinstance(command, dict):
            cmd_text = json.dumps(command) + "\n"
        else:
            cmd_text = str(command)
            if not cmd_text.endswith("\n"):
                cmd_text += "\n"

        if self.is_connected() and self.serial_conn:
            try:
                self.serial_conn.write(cmd_text.encode('utf-8'))
                self.serial_conn.flush()
                logger.info("Serial command transmitted: %s", cmd_text.strip())
                return True
            except Exception as e:
                logger.error("Failed to transmit serial command: %s", e)
                return False
        else:
            if Config.DEMO_MODE:
                logger.info("[DEMO_MODE] Simulated serial command output: %s", cmd_text.strip())
                return True
            logger.warning("Cannot send command '%s': Serial port not connected.", cmd_text.strip())
            return False

    def get_weight(self):
        """Returns the latest measured weight from load cell."""
        with self._lock:
            return self.weight

    def get_ir_state(self):
        """Returns the latest recorded IR obstacle sensor state."""
        with self._lock:
            return self.ir_state

    def is_connected(self):
        """Returns boolean indicating whether the serial port is currently active."""
        return bool(self.connected and self.serial_conn and self.serial_conn.is_open)

    def get_trolley_status(self):
        """Returns human-readable status: 'connected' or 'disconnected'."""
        return 'connected' if self.is_connected() else 'disconnected'


# Export singleton instance for easy import across modules
serial_communicator = SerialCommunicator()
