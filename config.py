import os


class Config:
    PORT = int(os.environ.get('PORT', 5001))
    SECRET_KEY = os.environ.get('SECRET_KEY', 'smart-trolley-secret-key-2024')
    DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'smart_trolley.db')

    # Admin credentials (hardcoded for college project)
    ADMIN_USERNAME = 'admin'
    ADMIN_PASSWORD = 'admin123'
    ADMIN_EMAIL = 'admin@smarttrolley.com'

    # Serial communication settings
    SERIAL_PORT = '/dev/ttyACM0'  # Default for Arduino on Raspberry Pi
    SERIAL_BAUD = 9600
    SERIAL_TIMEOUT = 1

    # Demo mode (set True when no hardware connected)
    DEMO_MODE = True

    # Email settings (Gmail SMTP)
    SMTP_SERVER = 'smtp.gmail.com'
    SMTP_PORT = 587
    SMTP_USERNAME = os.environ.get('SMTP_USERNAME', '')
    SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', '')  # App password for Gmail
    SMTP_FROM_EMAIL = os.environ.get('SMTP_FROM_EMAIL', 'smarttrolley@gmail.com')

    # Duplicate scan prevention (seconds)
    SCAN_COOLDOWN = 3

    # Weight tolerance (grams)
    WEIGHT_TOLERANCE = 20
