/*
  SMART SHOPPING TROLLEY - Arduino Mega 2560
  Serial protocol (9600 baud, newline-terminated JSON):
    Arduino -> Pi: {"type":"rfid","uid":"0C:06:6B:32"}
                   {"type":"weight","value":125.50}
                   {"type":"ir","state":"blocked"}
    Pi -> Arduino: {"command":"servo","action":"open"}
                   {"command":"led","state":"yellow|red|green|off"}
                   {"command":"buzzer","action":"beep","count":3}

  IMPORTANT: HX711 calibration factor 7050 is a starting value only.
  Calibrate with a known mass before relying on weight verification.
*/

#include <SPI.h>
#include <MFRC522.h>
#include <HX711.h>
#include <Servo.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SH110X.h>

// RFID RC522 (Mega hardware SPI pins: 50 MISO, 51 MOSI, 52 SCK)
#define RFID_SS_PIN 53
#define RFID_RST_PIN 49

// Load cell HX711
#define HX711_DOUT_PIN 3
#define HX711_SCK_PIN 2

// Other sensors / actuators
#define IR_PIN 22
#define SERVO_PIN 25
#define BUZZER_PIN 26
#define GREEN_LED_PIN 27
#define YELLOW_LED_PIN 28
#define RED_LED_PIN 29

#define OLED_WIDTH 128
#define OLED_HEIGHT 64
#define OLED_RESET -1
#define OLED_ADDRESS 0x3C

// Tune these for the physical gate mechanism.
const int SERVO_CLOSED_ANGLE = 0;
const int SERVO_OPEN_ANGLE = 90;
const unsigned long SERVO_OPEN_TIME_MS = 1200;
const unsigned long WEIGHT_SEND_INTERVAL_MS = 500;
const unsigned long IR_SEND_INTERVAL_MS = 250;
const float CALIBRATION_FACTOR = 7050.0f; // verify with a known mass

MFRC522 rfid(RFID_SS_PIN, RFID_RST_PIN);
HX711 scale;
Servo gateServo;
Adafruit_SH1106G display(OLED_WIDTH, OLED_HEIGHT, &Wire, OLED_RESET);
bool oledReady = false;

unsigned long servoCloseAt = 0;
bool servoIsOpen = false;
unsigned long lastWeightSend = 0;
unsigned long lastIrSend = 0;
int lastIrState = -1;

// Non-blocking buzzer pattern
int beepsRemaining = 0;
bool buzzerOn = false;
unsigned long buzzerChangeAt = 0;
const unsigned long BEEP_ON_MS = 160;
const unsigned long BEEP_OFF_MS = 140;

String serialLine;

void setLeds(const String &state) {
  digitalWrite(RED_LED_PIN, state == "red" ? HIGH : LOW);
  digitalWrite(GREEN_LED_PIN, state == "green" ? HIGH : LOW);
  digitalWrite(YELLOW_LED_PIN, state == "yellow" ? HIGH : LOW);
  // 'off' and any unrecognized value turn all three LEDs off.
}

void startBuzzerPattern(int count) {
  beepsRemaining = constrain(count, 1, 8);
  buzzerOn = false;
  buzzerChangeAt = 0;
}

void updateBuzzer() {
  if (beepsRemaining <= 0) {
    if (buzzerOn) {
      noTone(BUZZER_PIN);
      buzzerOn = false;
    }
    return;
  }

  unsigned long now = millis();
  if (now < buzzerChangeAt) return;

  if (!buzzerOn) {
    tone(BUZZER_PIN, 2200);
    buzzerOn = true;
    buzzerChangeAt = now + BEEP_ON_MS;
  } else {
    noTone(BUZZER_PIN);
    buzzerOn = false;
    beepsRemaining--;
    buzzerChangeAt = now + BEEP_OFF_MS;
  }
}

void openGate() {
  gateServo.write(SERVO_OPEN_ANGLE);
  servoIsOpen = true;
  servoCloseAt = millis() + SERVO_OPEN_TIME_MS;
}

void updateServo() {
  if (servoIsOpen && (long)(millis() - servoCloseAt) >= 0) {
    gateServo.write(SERVO_CLOSED_ANGLE);
    servoIsOpen = false;
  }
}

void updateDisplay(const String &line1, const String &line2) {
  if (!oledReady) return;
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SH110X_WHITE);
  display.setTextWrap(true);
  display.setCursor(0, 4);
  display.println(line1);
  display.setCursor(0, 30);
  display.println(line2);
  display.display();
}

// Extract a simple JSON string value from a command packet.
String jsonStringValue(const String &json, const char *key) {
  String token = String("\"") + key + "\":\"";
  int start = json.indexOf(token);
  if (start < 0) return "";
  start += token.length();
  String value = "";
  bool escaped = false;
  for (int i = start; i < json.length(); i++) {
    char c = json[i];
    if (escaped) { value += c; escaped = false; }
    else if (c == '\\') escaped = true;
    else if (c == '\"') break;
    else value += c;
  }
  return value;
}

float jsonNumberValue(const String &json, const char *key, float fallback) {
  String token = String("\"") + key + "\":";
  int start = json.indexOf(token);
  if (start < 0) return fallback;
  start += token.length();
  while (start < json.length() && json[start] == ' ') start++;
  int end = start;
  while (end < json.length() && (isDigit(json[end]) || json[end] == '.' || json[end] == '-')) end++;
  if (end == start) return fallback;
  return json.substring(start, end).toFloat();
}

void showProductOnOLED(const String &name, float weight, float price) {
  if (!oledReady) return;
  display.clearDisplay();
  display.setTextColor(SH110X_WHITE);
  display.setTextWrap(true);
  display.setTextSize(1);
  display.setCursor(0, 0);
  display.println("PRODUCT DETECTED");
  display.drawLine(0, 12, 127, 12, SH110X_WHITE);
  String safeName = name.length() ? name : "Unknown product";
  display.setCursor(0, 17);
  if (safeName.length() > 20) {
    display.println(safeName.substring(0, 20));
    display.setCursor(0, 27);
    display.println(safeName.substring(20, 40));
  } else {
    display.println(safeName);
  }
  display.setCursor(0, 49);
  display.print("Wt:"); display.print(weight, 1); display.print("g Rs:"); display.println(price, 0);
  display.display();
}

void processCommand(const String &line) {
  if (line.indexOf("\"command\":\"display\"") >= 0) {
    String productName = jsonStringValue(line, "name");
    float productWeight = jsonNumberValue(line, "weight", 0.0f);
    float productPrice = jsonNumberValue(line, "price", 0.0f);
    showProductOnOLED(productName, productWeight, productPrice);
    return;
  }

  if (line.indexOf("\"command\":\"led\"") >= 0) {
    if (line.indexOf("\"red\"") >= 0) setLeds("red");
    else if (line.indexOf("\"green\"") >= 0) setLeds("green");
    else if (line.indexOf("\"yellow\"") >= 0) setLeds("yellow");
    else setLeds("off");
    return;
  }

  if (line.indexOf("\"command\":\"servo\"") >= 0) {
    if (line.indexOf("\"open\"") >= 0) openGate();
    else if (line.indexOf("\"close\"") >= 0) {
      gateServo.write(SERVO_CLOSED_ANGLE);
      servoIsOpen = false;
    }
    return;
  }

  if (line.indexOf("\"command\":\"buzzer\"") >= 0) {
    if (line.indexOf("\"beep\"") >= 0) {
      int count = 3;
      int key = line.indexOf("\"count\"");
      if (key >= 0) {
        int colon = line.indexOf(':', key);
        if (colon >= 0) count = line.substring(colon + 1).toInt();
      }
      startBuzzerPattern(count);
    } else {
      beepsRemaining = 0;
      noTone(BUZZER_PIN);
      buzzerOn = false;
    }
  }
}

void readPiCommands() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n') {
      serialLine.trim();
      if (serialLine.length() > 0) processCommand(serialLine);
      serialLine = "";
    } else if (c != '\r' && serialLine.length() < 300) {
      serialLine += c;
    } else if (serialLine.length() >= 300) {
      serialLine = ""; // discard malformed/oversized command
    }
  }
}

void sendRfidIfPresent() {
  if (!rfid.PICC_IsNewCardPresent() || !rfid.PICC_ReadCardSerial()) return;

  String uid;
  for (byte i = 0; i < rfid.uid.size; i++) {
    if (i > 0) uid += ':';
    if (rfid.uid.uidByte[i] < 0x10) uid += '0';
    uid += String(rfid.uid.uidByte[i], HEX);
  }
  uid.toUpperCase();

  Serial.print("{\"type\":\"rfid\",\"uid\":\"");
  Serial.print(uid);
  Serial.println("\"}");
  updateDisplay("RFID detected", uid);

  rfid.PICC_HaltA();
  rfid.PCD_StopCrypto1();
}

void sendWeightIfDue() {
  unsigned long now = millis();
  if (now - lastWeightSend < WEIGHT_SEND_INTERVAL_MS) return;
  lastWeightSend = now;

  if (scale.is_ready()) {
    float grams = scale.get_units(3);
    if (isfinite(grams)) {
      Serial.print("{\"type\":\"weight\",\"value\":");
      Serial.print(grams, 2);
      Serial.println("}");
    }
  }
}

void sendIrIfChangedOrDue() {
  unsigned long now = millis();
  if (now - lastIrSend < IR_SEND_INTERVAL_MS) return;
  lastIrSend = now;
  int state = digitalRead(IR_PIN);
  if (state != lastIrState) {
    lastIrState = state;
    Serial.print("{\"type\":\"ir\",\"state\":\"");
    Serial.print(state == LOW ? "blocked" : "clear");
    Serial.println("\"}");
  }
}

void setup() {
  Serial.begin(9600);
  serialLine.reserve(320);

  pinMode(IR_PIN, INPUT_PULLUP);
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(RED_LED_PIN, OUTPUT);
  pinMode(GREEN_LED_PIN, OUTPUT);
  pinMode(YELLOW_LED_PIN, OUTPUT);
  setLeds("off");
  noTone(BUZZER_PIN);

  gateServo.attach(SERVO_PIN);
  gateServo.write(SERVO_CLOSED_ANGLE);

  SPI.begin();
  rfid.PCD_Init();

  scale.begin(HX711_DOUT_PIN, HX711_SCK_PIN);
  scale.set_scale(CALIBRATION_FACTOR);
  // Tare only when the trolley is empty and stable during Arduino startup.
  delay(300);
  if (scale.is_ready()) scale.tare();

  oledReady = display.begin(OLED_ADDRESS, true);
  if (oledReady) updateDisplay("SMART TROLLEY", "System ready");
}

void loop() {
  readPiCommands();
  sendRfidIfPresent();
  sendWeightIfDue();
  sendIrIfChangedOrDue();
  updateServo();
  updateBuzzer();
}
