# IoT Smart Shopping Trolley

An automated, intelligent shopping cart system powered by **Raspberry Pi**, **Arduino**, **RFID**, and a **digital load cell**. The system enables frictionless shopping by allowing customers to scan items directly into their trolley, automatically verifies item weights to prevent theft and mismatches, provides a real-time web dashboard, and supports instant checkout with automated HTML receipt dispatch via email.

---

## 🌟 Key Features

- **Automated RFID Item Scanning:** Customers scan products using an onboard RC522 RFID reader. Items are instantly added to the cart and reflected on the customer interface.
- **Dynamic Weight Verification (Anti-Theft):** Integrates an HX711 load cell sensor that checks the measured weight against the expected product catalog weight in real-time. Discrepancies trigger an instant mismatch alert.
- **Duplicate Scan Prevention:** Configurable cooldown timer prevents accidental multi-scans of the same item.
- **Real-Time Customer Dashboard:** Live polling updates showing active cart items, current total bill, itemized weights, scale verification status, and trolley hardware connectivity.
- **Admin Management Portal:** Comprehensive store manager interface for adding, updating, and removing catalog products, tracking registered customer accounts, and auditing itemized transaction histories.
- **Digital Receipts via Gmail SMTP:** Automated sending of itemized HTML shopping receipts directly to the customer's registered email address upon checkout.
- **Hardware Simulation & Demo Mode:** Complete demo mode allows full functionality testing directly in the browser without physical hardware connected.
- **Responsive Mobile & Desktop UI:** Clean, modern interface designed with teal/blue accents, responsive CSS grid/flexbox layouts, collapsible sidebar, and toast notifications.

---

## 🛠️ Hardware Components

| Component | Specification / Model | Purpose |
| :--- | :--- | :--- |
| **Central Computer** | Raspberry Pi 4 Model B (or 3B+) | Hosts Flask web server, SQLite database, and handles serial dispatch |
| **Microcontroller** | Arduino Uno / Nano (ATmega328P) | Direct interface for sensors, ADC, and actuators |
| **RFID Reader** | MFRC522 (13.56 MHz SPI) | Reads 13.56 MHz RFID tags / cards attached to products |
| **RFID Tags / Cards** | Mifare Classic 1K Cards / Keyfobs | Attached to store inventory items with unique UIDs |
| **Weight Sensor** | 5kg / 10kg Strain Gauge Load Cell | Measures cumulative weight of products placed inside the trolley |
| **ADC Amplifier** | HX711 24-Bit ADC Module | Amplifies small millivolt signals from load cell for Arduino |
| **Serial Link** | USB Type-A to Type-B Cable | High-speed 9600 baud serial connection between Arduino and Raspberry Pi |
| **Power Supply** | 5V / 3A USB-C Power Supply | Powers Raspberry Pi, Arduino, and peripheral sensors |
| **Prototyping** | Half-size Breadboard & Jumpers | Interconnections between Arduino, RFID reader, and HX711 |

---

## 📁 Project Structure

```text
smart-trolley/
├── app.py                     # Main Flask web application, route handlers, and API endpoints
├── config.py                  # System configuration (Database, Serial, Admin credentials, SMTP)
├── email_service.py           # SMTP mailer utility generating styled HTML purchase receipts
├── models.py                  # SQLite database layer, schema migration, and seed catalog items
├── requirements.txt           # Python dependencies (Flask, pyserial, Werkzeug)
├── serial_comm.py             # Background daemon thread handling Arduino serial communication
├── README.md                  # Comprehensive project documentation
├── static/
│   ├── css/
│   │   └── style.css          # Master responsive stylesheet (CSS variables, components, themes)
│   └── js/
│       └── main.js            # Frontend JavaScript controller (polling, cart, modals, toasts)
└── templates/
    ├── admin_customers.html   # Admin portal: view all registered customer accounts
    ├── admin_dashboard.html   # Admin portal: store metrics, revenue, and quick action cards
    ├── admin_products.html    # Admin portal: CRUD catalog product manager with edit modal
    ├── admin_transactions.html# Admin portal: transaction audit history with receipt item modal
    ├── base.html              # Master layout template with sidebar navigation and flash messages
    ├── cart.html              # Customer cart view, quantity management, and checkout modal
    ├── customer_dashboard.html# Customer real-time shopping dashboard and hardware simulator
    ├── login.html             # Customer and Admin authentication portal
    └── register.html          # New customer registration page
```

---

## 🚀 Raspberry Pi Installation & Setup

Follow these step-by-step instructions to set up and run the Smart Trolley system on a Raspberry Pi:

### 1. Clone or Copy Project Files
```bash
git clone https://github.com/your-username/smart-trolley.git
# Or navigate to existing directory
cd /Users/bansi/Academics/IOT/project/smart-trolley
```

### 2. Enter Project Directory
```bash
cd smart-trolley
```

### 3. Create a Python Virtual Environment
```bash
python3 -m venv venv
```

### 4. Activate the Virtual Environment
```bash
source venv/bin/activate
```

### 5. Install Dependencies
```bash
pip install -r requirements.txt
```

### 6. Configure Email Settings
Open `config.py` in your text editor and enter your Gmail credentials (or export environment variables):
```python
# In config.py:
SMTP_SERVER = 'smtp.gmail.com'
SMTP_PORT = 587
SMTP_USERNAME = 'your-email@gmail.com'
SMTP_PASSWORD = 'your-16-char-app-password'
SMTP_FROM_EMAIL = 'your-email@gmail.com'
```

### 7. Run the Flask Application
```bash
python app.py
```

### 8. Access the Web Dashboard
Open any browser on the same local network:
```text
http://<raspberry-pi-ip>:5000
# Example: http://192.168.1.15:5000
```
On the Raspberry Pi itself:
```text
http://localhost:5000
```

---

## 🎮 Demo Mode (Hardware-Free Testing)

When physical Arduino hardware is not connected, the system can run entirely in **Demo Mode**:

1. Ensure `DEMO_MODE = True` in `config.py`.
2. Login to the customer portal and open `/dashboard`.
3. The **Demo Mode Banner & Controls** will appear at the top of the dashboard:
   - **Simulate Product Scan:** Select any catalog item from the dropdown and click **Scan Product**. The item is added to the cart, the expected weight increases, and recent scans update instantly.
   - **Simulate Load Cell Weight:** Enter a measured weight in grams and click **Send Weight**.
   - If the weight matches the expected cart weight (within `±20g` tolerance), the status badge shows <span style="color: #4CAF50; font-weight: bold;">Verified ✓</span>.
   - If the weight differs, a red <span style="color: #f44336; font-weight: bold;">Mismatch Warning</span> is displayed.

---

## 🔐 Admin Portal & Default Credentials

The admin portal provides store managers with tools to manage catalog items, audit shoppers, and inspect transactions.

- **Admin Login URL:** `http://<ip>:5000/login`
  - Check the **"Login as Administrator"** checkbox on the login page.
- **Default Username:** `admin`
- **Default Password:** `admin123`
- **Admin Dashboard:** `http://<ip>:5000/admin`

---

## 📧 Email Configuration Guide (Gmail App Password)

To send receipts automatically after customer checkout, configure a **Gmail App Password**:

1. Log into your Google Account and go to **Security Settings** (`https://myaccount.google.com/security`).
2. Ensure **2-Step Verification** is turned **ON**.
3. Under *2-Step Verification*, scroll down to **App passwords** (or search "App passwords").
4. Enter an application name (e.g., `Smart Trolley IoT`) and click **Create**.
5. Google will generate a **16-character password** (e.g., `abcd efgh ijkl mnop`).
6. Copy this password into `config.py`:
   ```python
   SMTP_USERNAME = 'yourstore@gmail.com'
   SMTP_PASSWORD = 'abcdefghijklmnop'  # 16-character password without spaces
   SMTP_FROM_EMAIL = 'yourstore@gmail.com'
   ```
7. Or configure via shell environment variables before starting `app.py`:
   ```bash
   export SMTP_USERNAME="yourstore@gmail.com"
   export SMTP_PASSWORD="abcdefghijklmnop"
   export SMTP_FROM_EMAIL="yourstore@gmail.com"
   python app.py
   ```

---

## 🔌 Hardware Wiring & Pin Connections

### 1. Arduino Uno to RC522 RFID Module (SPI)

> [!CAUTION]
> The RC522 RFID module requires **3.3V power**. Connecting VCC to 5V will permanently damage the RFID board.

```text
+-------------------+--------------------+
|  RC522 Pin Name   |  Arduino Uno Pin   |
+-------------------+--------------------+
|  VCC (3.3V)       |  3.3V (NOT 5V!)    |
|  RST (Reset)      |  Pin D9            |
|  GND (Ground)     |  GND               |
|  IRQ              |  Not Connected     |
|  MISO             |  Pin D12           |
|  MOSI             |  Pin D11           |
|  SCK (Clock)      |  Pin D13           |
|  SDA / SS         |  Pin D10           |
+-------------------+--------------------+
```

### 2. Arduino Uno to HX711 Load Cell Amplifier

```text
+-------------------+--------------------+
|    HX711 Pin      |  Arduino Uno Pin   |
+-------------------+--------------------+
|  VCC              |  5V                |
|  GND              |  GND               |
|  DT (Data Out)    |  Pin D3            |
|  SCK (Clock)      |  Pin D2            |
+-------------------+--------------------+

Load Cell 4-Wire Color Code to HX711 Terminal Block:
  - RED   -> E+ (Excitation +)
  - BLACK -> E- (Excitation -)
  - WHITE -> A- (Signal -)
  - GREEN -> A+ (Signal +)
```

### 3. Raspberry Pi to Arduino Connection

```text
+----------------------+        USB Serial Cable        +----------------------+
|    Raspberry Pi 4    | =============================> |     Arduino Uno      |
|  Port: /dev/ttyACM0  |        (9600 Baud Rate)        |  Standard USB Port   |
+----------------------+                                +----------------------+
```

---

## 📡 Arduino JSON Serial Protocol

Communication between the Arduino and Raspberry Pi uses single-line JSON objects terminated by a newline character (`\n`) over standard USB serial at **9600 baud**.

### Inbound Messages (Arduino → Raspberry Pi)

#### 1. RFID Card Scanned
Sent immediately when an RFID tag is placed within range of the RC522 reader:
```json
{"type": "rfid", "uid": "A1:B2:C3:D4"}
```

#### 2. Periodic Load Cell Weight Reading
Sent periodically (e.g., every 500ms) with the calibrated net weight in grams:
```json
{"type": "weight", "value": 530.0}
```

#### 3. IR Obstacle Sensor Detection
Sent when an item passes through the trolley basket entry perimeter:
```json
{"type": "ir", "state": "blocked"}
{"type": "ir", "state": "clear"}
```

### Outbound Commands (Raspberry Pi → Arduino)

#### 1. Trigger Buzzer Tone
```json
{"command": "beep", "duration_ms": 200}
```

#### 2. Status LED Indication
```json
{"command": "led", "color": "green", "state": "on"}
{"command": "led", "color": "red", "state": "on"}
```

#### 3. Solenoid / Servo Lock Control
```json
{"command": "unlock", "duration_sec": 5}
```

---

## 💻 Technology Stack

- **Backend:** Python 3, Flask 3.0, SQLite3, PySerial 3.5, Werkzeug, Smtplib
- **Frontend:** Vanilla HTML5, CSS3 (CSS Variables, Flexbox, Responsive Grid), ES6+ JavaScript (Fetch API)
- **Hardware & Firmware:** Raspberry Pi OS (Linux), Arduino C / C++ (MFRC522, HX711 libraries)
- **Email Delivery:** SMTP (TLS Encryption on port 587) with HTML receipt formatting

---

## 📜 Academic Project Notice & License

This project was developed as an IoT Academic Capstone Project for demonstration and educational purposes. Distributed under the MIT Open Source License.
