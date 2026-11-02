# IoT Smart Shopping Trolley

An automated shopping cart system built with Raspberry Pi, Arduino, RFID, and a digital load cell. Customers scan items directly into the trolley, the system verifies item weights to prevent theft, updates a real-time web interface, and sends an itemized email receipt upon checkout.

---

## Features

- **RFID Item Scanning:** Products are scanned using an RC522 RFID reader and added to the cart instantly.
- **Weight Verification (Anti-Theft):** An HX711 load cell measures cart weight and compares it against expected catalog weight. A mismatch alert is shown if the weights do not match.
- **Customer Dashboard:** Real-time web view of cart items, current bill, total weight, and scale status.
- **Admin Portal:** Manage products, view registered customers, and audit transaction records with itemized details.
- **Email Receipts:** Automatically sends an HTML receipt to the customer's email address upon checkout using SMTP.

---

## Installation and Setup

### 1. Clone the Repository
```bash
git clone https://github.com/your-username/smart-trolley.git
cd smart-trolley
```

### 2. Set Up Python Environment
```bash
pip install -r requirements.txt
```

### 3. Configure Settings
Open `config.py` to adjust settings if needed:
- Set `DEMO_MODE = True` to test without physical hardware.
- Enter your Gmail SMTP credentials to enable email receipts.

### 4. Run the Application
```bash
python app.py
```

### 5. Access the Web Interface
- On the host machine: `http://localhost:5000`
- From another device on the same network: `http://<ip-address>:5000`

---

## Admin Portal

- **URL:** `http://localhost:5000/login`
- **Option:** Check "Login as Administrator"
- **Default Username:** `admin`
- **Default Password:** `admin123`

---

## Technology Stack

- **Backend:** Python 3, Flask, SQLite3, PySerial
- **Frontend:** HTML5, CSS3, JavaScript (Fetch API)
- **Hardware:** Raspberry Pi, Arduino Uno, MFRC522 RFID, HX711 Load Cell
- **Communication:** USB Serial (JSON at 9600 baud), SMTP (TLS)
