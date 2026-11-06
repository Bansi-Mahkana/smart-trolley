
# IoT Smart Shopping Trolley

An IoT-based shopping system using **Raspberry Pi, Arduino Mega 2560, RFID, and a digital load cell**. It supports product scanning, weight verification, cart updates, servo gate control, OLED display, and email receipt generation.

## Features

- **RFID Scanning:** Identifies products and adds them to the shopping cart.
- **Weight Verification:** Compares actual and expected product weight to detect mismatches.
- **Customer Dashboard:** Displays cart items, total weight, and bill amount.
- **Admin Portal:** Manages products, customers, and transactions.
- **Servo Control:** Opens the rear gate after a valid RFID lookup and cart insertion.
- **OLED Display:** Shows product name, weight, and price.
- **Email Receipt:** Sends an itemized receipt after checkout.

## Technology Stack

- **Backend:** Python, Flask, SQLite3, PySerial
- **Frontend:** HTML, CSS, JavaScript
- **Hardware:** Arduino Mega 2560, Raspberry Pi
- **Communication:** USB Serial, JSON at 9600 baud
- **Email:** SMTP with TLS


## Installation and Setup

### 1. Clone the Repository

```bash
git clone https://github.com/Bansi-Mahkana/smart-trolley.git
cd smart-trolley
```

### 2. Set Up Python Environment

**Windows (PowerShell):**
```powershell
py -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

If script activation is blocked:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1
```

**macOS / Raspberry Pi:**
```bash
python3 -m venv venv
source venv/bin/activate
python3 -m pip install -r requirements.txt
```

### 3. Configure the Application

Update `config.py`:

- Set `DEMO_MODE = True` to test without physical hardware.
- Configure Gmail SMTP credentials for email receipts.
- Use a Google App Password instead of your regular Gmail password.
- Keep credentials private.

### 4. Install Arduino Libraries

Install the following libraries using Arduino IDE Library Manager:

- MFRC522
- HX711
- Servo
- Adafruit GFX Library
- Adafruit SH110X

### 5. Upload Arduino Firmware

**Windows (Arduino CLI):**
```powershell
arduino-cli compile --fqbn arduino:avr:mega:cpu=atmega2560 .
arduino-cli upload -p COM3 --fqbn arduino:avr:mega:cpu=atmega2560 .
```
Replace `COM3` with your actual Arduino COM port.

**macOS (Arduino CLI):**
```bash
arduino-cli compile --fqbn arduino:avr:mega:cpu=atmega2560 .
arduino-cli upload -p /dev/cu.usbmodemXXXX --fqbn arduino:avr:mega:cpu=atmega2560 .
```
Replace the port with your actual Arduino port.

To list available ports:
```bash
arduino-cli board list
```

**Raspberry Pi (Arduino CLI):**
```bash
cd ~/Arduino/SmartTrolley
~/local/bin/arduino-cli compile --fqbn arduino:avr:mega:cpu=atmega2560 .
~/local/bin/arduino-cli upload -p /dev/ttyACM0 --fqbn arduino:avr:mega:cpu=atmega2560 .
```

### 6. Run the Flask Application

Run from the project directory with the virtual environment activated.

**Windows:**
```powershell
python app.py
```

**macOS / Raspberry Pi:**
```bash
python3 app.py
```

### 7. Access the Website

Open the browser and visit:

```text
http://localhost:5001
```

## Hardware Notes

- OLED: SH1106, 128×64, I2C address `0x3C`. SSD1306 requires a different display driver.
- Servo: Use a separate regulated 5V supply. Connect its ground to Arduino GND. Do not power it from the Mega 5V pin.
- Calibrate the load cell before weight verification.
- On Raspberry Pi, `serial_comm.py` uses `/dev/ttyACM0` and provides `send_command(dict)`. Keep the existing file unchanged if it matches the included version.
- Unknown RFID tags do not display product details.

## System Workflow

1. RFID reader scans a product tag.
2. Arduino sends the RFID UID to Raspberry Pi through USB serial communication.
3. Flask checks the UID against the SQLite product database.
4. After a valid lookup and cart insertion, the application sends commands to open the servo gate and display product name, weight, and price on the OLED.
5. The website updates the shopping cart, weight status, and bill.
6. After checkout, an itemized email receipt is sent to the customer.
