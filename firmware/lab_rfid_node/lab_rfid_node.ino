/*
 * IoT Lab Equipment System - RFID Scan Node
 * Board : ESP8266 NodeMCU (ESP-12E)
 * Parts : MFRC522 (SPI), SSD1306 OLED (I2C), Wi-Fi
 *
 * What it does
 *  1. Connects to Wi-Fi and shows status on the OLED.
 *  2. Reads the UID of a card presented to the MFRC522.
 *  3. POSTs {device_id, uid, scan_id} to the backend (/api/rfid/scan).
 *  4. Shows the backend's reply on the OLED.
 *  5. Every ~3 s asks the backend for new screens (items ISSUED / RETURNED, with student
 *     name, item and quantity) and shows them one after another.
 *
 * The device never decides anything itself: it only reports the UID and
 * displays whatever the backend answers. If the network is down it says
 * so and never claims a scan succeeded.
 *
 * Libraries (Arduino Library Manager):
 *   - MFRC522            by GithubCommunity (miguelbalboa)
 *   - Adafruit SSD1306
 *   - Adafruit GFX Library
 *   - ArduinoJson        by Benoit Blanchon (6.x or 7.x)
 * Board package: "esp8266" by ESP8266 Community  ->  board "NodeMCU 1.0 (ESP-12E Module)"
 */

#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <WiFiClient.h>
#include <WiFiClientSecure.h>   // for https:// addresses (live server)
#include <SPI.h>
#include <Wire.h>
#include <MFRC522.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <ArduinoJson.h>

// ======================= USER CONFIGURATION ===========================
const char* WIFI_SSID   = "YOUR_WIFI_NAME";
const char* WIFI_PASS   = "YOUR_WIFI_PASSWORD";

// Address of the server. Keep the ending "/api/rfid/scan".
//   Live server : "https://your-app-name.onrender.com/api/rfid/scan"
//   Own PC      : "http://192.168.1.100:8000/api/rfid/scan"  (same Wi-Fi; run uvicorn with --host 0.0.0.0)
const char* SERVER_URL  = "https://your-app-name.onrender.com/api/rfid/scan";

// Each reader has its own ID and key. In the web app open "Labs and readers", add this reader to its
// laboratory, and copy the ID and the key (shown only once) here.
const char* DEVICE_ID   = "LAB-RFID-01";
const char* DEVICE_KEY  = "change-this-secret";

#define SCREEN_WIDTH   128
#define SCREEN_HEIGHT  64        // use 32 if you have a 128x32 OLED
#define OLED_ADDRESS   0x3C      // most modules: 0x3C (some use 0x3D)
// =====================================================================

// ---- MFRC522 pins (SPI) ----  your wiring
#define RC522_SS   D8   // SDA / SS
#define RC522_RST  D3   // RST
// SCK  = D5, MISO = D6, MOSI = D7  (hardware SPI, fixed pins)

// ---- OLED pins (I2C) ----
#define OLED_SDA   D2
#define OLED_SCL   D1

// ---- Timing ----
const unsigned long WIFI_TIMEOUT_MS   = 15000;
const unsigned long HTTP_TIMEOUT_MS   = 25000;  // a free server that was asleep needs up to ~60 s to wake
const unsigned long RESULT_SHOW_MS    = 3000;
const unsigned long SAME_CARD_GAP_MS  = 2000;   // ignore same card re-read

MFRC522 rfid(RC522_SS, RC522_RST);
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);

const unsigned long DISPLAY_POLL_MS = 3000;     // how often to ask for new issue/return screens

struct Msg { String title, l1, l2, l3; unsigned int ms; };
const int QMAX = 8;
Msg queueBuf[QMAX];
int qHead = 0, qCount = 0;
long lastMsgId = 0;
unsigned long lastPoll = 0, showUntil = 0;
bool showingMsg = false;
String displayUrl;

WiFiClient plainClient;
WiFiClientSecure secureClient;
HTTPClient http;        // one shared client, so an HTTPS connection can be kept open between requests

bool beginRequest(const String& url) {
  if (url.startsWith("https://")) return http.begin(secureClient, url);
  return http.begin(plainClient, url);
}

String lastUid = "";
unsigned long lastUidTime = 0;
bool lastWifiOk = false;
unsigned long scanCounter = 0;

// ---------------------------------------------------------------------
// Display helpers
// ---------------------------------------------------------------------
void showScreen(const String& title, const String& l1 = "",
                const String& l2 = "", const String& l3 = "") {
  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);
  display.setTextWrap(true);

  display.setTextSize(1);
  display.setCursor(0, 0);
  display.print(title);
  display.drawLine(0, 10, SCREEN_WIDTH - 1, 10, SSD1306_WHITE);

  int y = 14;
  const int step = 12;
  const String lines[3] = {l1, l2, l3};
  for (int i = 0; i < 3; i++) {
    if (lines[i].length() == 0) continue;
    if (y + 8 > SCREEN_HEIGHT) break;
    display.setCursor(0, y);
    display.print(lines[i]);
    y += step;
  }
  display.display();
}

void showIdle() {
  bool ok = (WiFi.status() == WL_CONNECTED);
  showScreen("Electronics Dept.",
             "Scan your ID card",
             ok ? "WiFi: connected" : "WiFi: OFFLINE",
             ok ? WiFi.localIP().toString() : "Reconnecting...");
}

// ---------------------------------------------------------------------
// Wi-Fi
// ---------------------------------------------------------------------
bool connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.persistent(false);
  WiFi.begin(WIFI_SSID, WIFI_PASS);

  showScreen("WiFi", "Connecting to:", WIFI_SSID);
  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < WIFI_TIMEOUT_MS) {
    delay(250);
    Serial.print('.');
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("WiFi OK, IP: ");
    Serial.println(WiFi.localIP());
    showScreen("WiFi", "Connected", WiFi.localIP().toString());
    delay(1200);
    return true;
  }
  Serial.println("WiFi failed (will keep retrying in background)");
  showScreen("WiFi", "Connection failed", "Will keep retrying");
  delay(1500);
  return false;
}

// ---------------------------------------------------------------------
// RFID helpers
// ---------------------------------------------------------------------
String uidToString(const MFRC522::Uid& uid) {
  String s;
  for (byte i = 0; i < uid.size; i++) {
    if (uid.uidByte[i] < 0x10) s += '0';
    s += String(uid.uidByte[i], HEX);
  }
  s.toUpperCase();
  return s;
}

bool rfidReaderHealthy() {
  byte v = rfid.PCD_ReadRegister(MFRC522::VersionReg);
  Serial.print("MFRC522 version register: 0x");
  Serial.println(v, HEX);
  return !(v == 0x00 || v == 0xFF);   // 0x00/0xFF => wiring problem
}

// ---------------------------------------------------------------------
// Send the scan to the backend and show the response
// ---------------------------------------------------------------------
void sendScan(const String& uid) {
  if (WiFi.status() != WL_CONNECTED) {
    showScreen("OFFLINE", "Scan NOT sent", "Check WiFi", "UID: " + uid);
    Serial.println("Scan not sent: WiFi down");
    return;
  }

  showScreen("Card read", "UID: " + uid, "Contacting server...");

  scanCounter++;
  String scanId = String(ESP.getChipId(), HEX) + "-" + String(millis()) + "-" + String(scanCounter);

  String body = "{\"device_id\":\"" + String(DEVICE_ID) +
                "\",\"uid\":\"" + uid +
                "\",\"scan_id\":\"" + scanId + "\"}";

  http.setTimeout(HTTP_TIMEOUT_MS);

  if (!beginRequest(SERVER_URL)) {
    showScreen("ERROR", "Bad server URL");
    return;
  }
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Device-Key", DEVICE_KEY);

  int code = http.POST(body);
  String payload = (code > 0) ? http.getString() : "";
  http.end();

  Serial.printf("POST %s -> %d\n", SERVER_URL, code);
  Serial.println(payload);

  // Connection-level failure (no HTTP response at all)
  if (code <= 0) {
    showScreen("SERVER ERROR", "Not reachable", "Scan NOT saved", "UID: " + uid);
    return;
  }

  // Try to read the backend's message
  String message = "";
  String name = "";
  StaticJsonDocument<384> doc;
  if (deserializeJson(doc, payload) == DeserializationError::Ok) {
    message = doc["message"] | "";
    name    = doc["display_name"] | "";
  }

  if (code == 200 || code == 201) {
    showScreen("OK", name.length() ? name : "Card accepted",
               message, "UID: " + uid);
  } else if (code == 404) {
    showScreen("UNKNOWN CARD", message.length() ? message : "Not registered",
               "UID: " + uid);
  } else if (code == 409) {
    showScreen("CARD IN USE", message.length() ? message : "Already assigned",
               "UID: " + uid);
  } else if (code == 401 || code == 403) {
    showScreen("DEVICE DENIED", "Check device key", "HTTP " + String(code));
  } else if (code >= 400 && code < 500) {
    showScreen("NOTICE", message.length() ? message : "Request refused", "HTTP " + String(code), "UID: " + uid);
  } else {
    showScreen("SERVER ERROR", "HTTP " + String(code), message);
  }
}

// ---------------------------------------------------------------------
// Issue / return screens pushed from the web app
// ---------------------------------------------------------------------
void pushMsg(const String& t, const String& a, const String& b, const String& c, unsigned int ms) {
  if (qCount >= QMAX) return;
  int idx = (qHead + qCount) % QMAX;
  queueBuf[idx] = {t, a, b, c, ms};
  qCount++;
}

void pollDisplay() {
  if (millis() - lastPoll < DISPLAY_POLL_MS) return;
  lastPoll = millis();
  if (WiFi.status() != WL_CONNECTED || qCount > QMAX - 6) return;

  http.setTimeout(8000);
  if (!beginRequest(displayUrl + "?device_id=" + String(DEVICE_ID) + "&after_id=" + String(lastMsgId))) return;
  http.addHeader("X-Device-Key", DEVICE_KEY);
  int code = http.GET();
  if (code == 200) {
    String payload = http.getString();
    DynamicJsonDocument doc(2048);
    if (deserializeJson(doc, payload) == DeserializationError::Ok) {
      long latest = doc["latest_id"] | 0;
      if (latest < lastMsgId) lastMsgId = latest;          // server database was reset
      for (JsonObject m : doc["messages"].as<JsonArray>()) {
        pushMsg(m["title"] | "", m["l1"] | "", m["l2"] | "", m["l3"] | "", m["ms"] | 4000);
        lastMsgId = m["id"] | lastMsgId;
      }
    }
  } else if (code <= 0) {
    lastPoll = millis() + 8000;                            // server unreachable or waking up: back off
  }
  http.end();
}

void runDisplayQueue() {
  if (showingMsg && (long)(millis() - showUntil) < 0) return;   // current screen still on
  if (qCount > 0) {
    Msg m = queueBuf[qHead];
    qHead = (qHead + 1) % QMAX;
    qCount--;
    showScreen(m.title, m.l1, m.l2, m.l3);
    showingMsg = true;
    showUntil = millis() + m.ms;
  } else if (showingMsg) {
    showingMsg = false;
    showIdle();
  }
}

// ---------------------------------------------------------------------
// Arduino entry points
// ---------------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  delay(100);
  Serial.println("\n\nLab RFID node starting...");

  Wire.begin(OLED_SDA, OLED_SCL);
  if (!display.begin(SSD1306_SWITCHCAPVCC, OLED_ADDRESS)) {
    Serial.println("OLED not found - check SDA/SCL wiring and address");
    // keep running; serial output still works
  }
  display.clearDisplay();
  display.display();
  showScreen("Starting...", "Lab RFID node");

  SPI.begin();
  rfid.PCD_Init();
  delay(50);
  if (!rfidReaderHealthy()) {
    showScreen("RFID ERROR", "MFRC522 not found", "Check wiring/3.3V");
    while (true) { delay(1000); }     // halt: nothing useful can happen
  }
  rfid.PCD_SetAntennaGain(rfid.RxGain_max);

  secureClient.setInsecure();   // encrypts the link; for a pilot this is enough (see README, "Reader security")
  http.setReuse(true);
  Serial.printf("Free heap at start: %u bytes\n", ESP.getFreeHeap());
  displayUrl = String(SERVER_URL);
  displayUrl.replace("/rfid/scan", "/rfid/display");

  connectWiFi();
  lastWifiOk = (WiFi.status() == WL_CONNECTED);
  showIdle();
}

void loop() {
  // Refresh the idle screen when Wi-Fi state changes
  bool wifiOk = (WiFi.status() == WL_CONNECTED);
  if (wifiOk != lastWifiOk) {
    lastWifiOk = wifiOk;
    showIdle();
  }

  runDisplayQueue();
  pollDisplay();

  // Wait for a new card
  if (!rfid.PICC_IsNewCardPresent()) return;
  if (!rfid.PICC_ReadCardSerial())   return;

  String uid = uidToString(rfid.uid);
  rfid.PICC_HaltA();
  rfid.PCD_StopCrypto1();

  // Ignore the same card being read repeatedly while it sits on the reader
  if (uid == lastUid && millis() - lastUidTime < SAME_CARD_GAP_MS) return;
  lastUid = uid;
  lastUidTime = millis();

  Serial.print("Card UID: ");
  Serial.println(uid);

  sendScan(uid);

  delay(RESULT_SHOW_MS);
  lastUidTime = millis();
  showingMsg = false;
  showIdle();
}
