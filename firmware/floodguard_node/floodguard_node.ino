/*
 * FloodGuard sensor node - ESP32
 *
 * Hardware (suggested):
 *   - JSN-SR04T waterproof ultrasonic sensor  (TRIG=GPIO5, ECHO=GPIO18; ECHO needs a 5V->3.3V divider)
 *   - Tipping-bucket rain gauge, reed switch  (GPIO27 -> GND, internal pull-up)
 *   - Battery divider (2 x 100k) on GPIO34
 *
 * Every REPORT_INTERVAL_S seconds the node POSTs JSON to  <API_URL>/iot/readings
 * with the X-API-Key header. Water level = SENSOR_HEIGHT_M - measured distance,
 * where SENSOR_HEIGHT_M is the sensor's height above the gauge datum (surveyed on site).
 *
 * Replace the placeholders below before flashing. For solar/battery sites use
 * deep sleep between readings instead of delay().
 */
#include <WiFi.h>
#include <HTTPClient.h>

// ---- configuration (placeholders) ----
const char* WIFI_SSID     = "YOUR_WIFI";
const char* WIFI_PASS     = "YOUR_PASSWORD";
const char* API_URL       = "http://192.168.1.10:8000";   // FloodGuard backend
const char* API_KEY       = "dev-key-change-me";           // = FLOODGUARD_API_KEY on the server
const char* STATION_ID    = "YMN-01";
const float SENSOR_HEIGHT_M = 210.00;   // sensor height above datum (m)
const float MM_PER_TIP      = 0.2794;   // check your rain gauge's datasheet
const uint32_t REPORT_INTERVAL_S = 60;

const int PIN_TRIG = 5, PIN_ECHO = 18, PIN_RAIN = 27, PIN_BAT = 34;

volatile uint32_t tipCount = 0;
volatile uint32_t lastTipMs = 0;
uint16_t tipsPerMinute[10] = {0};   // rolling 10-minute rainfall window
uint8_t  slot = 0;

void IRAM_ATTR onTip() {            // debounce: ignore tips < 200 ms apart
  uint32_t now = millis();
  if (now - lastTipMs > 200) { tipCount++; lastTipMs = now; }
}

float readDistanceM() {             // median of 5 samples rejects spikes
  float s[5];
  for (int i = 0; i < 5; i++) {
    digitalWrite(PIN_TRIG, LOW);  delayMicroseconds(2);
    digitalWrite(PIN_TRIG, HIGH); delayMicroseconds(10);
    digitalWrite(PIN_TRIG, LOW);
    long us = pulseIn(PIN_ECHO, HIGH, 40000);
    s[i] = us * 0.000343f / 2.0f;  // speed of sound ~343 m/s
    delay(60);
  }
  for (int i = 0; i < 4; i++)
    for (int j = i + 1; j < 5; j++)
      if (s[j] < s[i]) { float t = s[i]; s[i] = s[j]; s[j] = t; }
  return s[2];
}

float batteryPct() {
  float v = analogRead(PIN_BAT) / 4095.0f * 3.3f * 2.0f;
  return constrain((v - 3.3f) / (4.2f - 3.3f) * 100.0f, 0, 100);
}

void connectWifi() {
  if (WiFi.status() == WL_CONNECTED) return;
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  for (int i = 0; i < 40 && WiFi.status() != WL_CONNECTED; i++) delay(500);
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_TRIG, OUTPUT); pinMode(PIN_ECHO, INPUT);
  pinMode(PIN_RAIN, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(PIN_RAIN), onTip, FALLING);
}

void loop() {
  connectWifi();

  noInterrupts(); uint32_t tips = tipCount; tipCount = 0; interrupts();
  tipsPerMinute[slot] = tips;
  slot = (slot + 1) % 10;
  uint32_t window = 0; for (int i = 0; i < 10; i++) window += tipsPerMinute[i];
  float rainMmHr = window * MM_PER_TIP * 6.0f;   // 10-min total -> per hour

  float dist = readDistanceM();
  if (dist > 0.2f && WiFi.status() == WL_CONNECTED) {   // 0 => no echo / out of range
    char body[200];
    snprintf(body, sizeof(body),
      "{\"station_id\":\"%s\",\"water_level_m\":%.3f,\"rain_mm_hr\":%.1f,\"battery_pct\":%.0f}",
      STATION_ID, SENSOR_HEIGHT_M - dist, rainMmHr, batteryPct());

    HTTPClient http;
    http.begin(String(API_URL) + "/iot/readings");
    http.addHeader("Content-Type", "application/json");
    http.addHeader("X-API-Key", API_KEY);
    int code = http.POST(body);
    Serial.printf("POST %s -> %d\n", body, code);
    http.end();
  }
  delay(REPORT_INTERVAL_S * 1000UL);
}
