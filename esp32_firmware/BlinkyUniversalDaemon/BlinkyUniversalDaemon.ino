/*
  =============================================================================
  Blinky Universal Micro-Daemon Firmware (Zero-Flash ESP32 Controller)
  =============================================================================
  Flash this ONCE to your ESP32. 
  After flashing, you NEVER need to touch Arduino IDE again!
  Blinky controls any sensor, motor, servo, relay, buzzer, or light dynamically.

  Supported Dynamic APIs:
    - GET /rgb?r=255&g=0&b=0                 -> Controls RGB LEDs (default GPIO 25, 26, 27)
    - GET /digital?pin=19&val=1              -> Digital Write (Relays, LEDs, Transistors)
    - GET /digital?pin=4                     -> Digital Read (Buttons, PIR Motion)
    - GET /pwm?pin=18&val=128                -> Analog/PWM Dimmer (0-255)
    - GET /servo?pin=18&angle=90             -> Servo Motor Sweep (0 to 180 degrees)
    - GET /tone?pin=19&freq=1000&duration=300-> Beep / Alarm Tone (Passive/Active Buzzer)
    - GET /analog?pin=34                     -> ADC Read (Light, Moisture, Potentiometer)
    - GET /status                            -> Uptime, Signal, Free Heap, Connected Devices
  =============================================================================
*/

#include <WiFi.h>
#include <WebServer.h>
#include <ESPmDNS.h>

// Wi-Fi Credentials injected from .env via config.h (run scripts/generate_esp32_config.py)
#if __has_include("config.h")
  #include "config.h"
#else
  #define WIFI_SSID "YOUR_WIFI_SSID"
  #define WIFI_PASSWORD "YOUR_WIFI_PASSWORD"
#endif

const char* ssid = WIFI_SSID;
const char* password = WIFI_PASSWORD;


// Default RGB pins (configurable on-the-fly via query args &rp= &gp= &bp=)
int defaultRedPin = 25;
int defaultGreenPin = 26;
int defaultBluePin = 27;

const int pwmFreq = 5000;
const int pwmResolution = 8;

// Servo PWM specs (50Hz standard servo frequency, 16-bit resolution)
const int servoFreq = 50;
const int servoResolution = 16;

WebServer server(80);

// Helper: Ensure pin is attached for PWM
void ensurePwm(int pin, int freq = 5000, int res = 8) {
  ledcAttach(pin, freq, res);
}

// ---------------------------------------------------------------------------
// 1. RGB Light Controller (/rgb?r=255&g=0&b=0[&rp=25&gp=26&bp=27])
// ---------------------------------------------------------------------------
void handleRgb() {
  int r = server.hasArg("r") ? server.arg("r").toInt() : 0;
  int g = server.hasArg("g") ? server.arg("g").toInt() : 0;
  int b = server.hasArg("b") ? server.arg("b").toInt() : 0;

  int rp = server.hasArg("rp") ? server.arg("rp").toInt() : defaultRedPin;
  int gp = server.hasArg("gp") ? server.arg("gp").toInt() : defaultGreenPin;
  int bp = server.hasArg("bp") ? server.arg("bp").toInt() : defaultBluePin;

  ensurePwm(rp, pwmFreq, pwmResolution);
  ensurePwm(gp, pwmFreq, pwmResolution);
  ensurePwm(bp, pwmFreq, pwmResolution);

  ledcWrite(rp, constrain(r, 0, 255));
  ledcWrite(gp, constrain(g, 0, 255));
  ledcWrite(bp, constrain(b, 0, 255));

  server.send(200, "application/json", "{\"status\":\"ok\",\"action\":\"rgb\",\"r\":" + String(r) + ",\"g\":" + String(g) + ",\"b\":" + String(b) + "}");
}

// ---------------------------------------------------------------------------
// 2. Digital I/O (/digital?pin=X[&val=0|1])
// ---------------------------------------------------------------------------
void handleDigital() {
  if (!server.hasArg("pin")) {
    server.send(400, "application/json", "{\"error\":\"Missing pin parameter\"}");
    return;
  }
  int pin = server.arg("pin").toInt();

  if (server.hasArg("val")) {
    // Write Mode
    int val = server.arg("val").toInt();
    pinMode(pin, OUTPUT);
    digitalWrite(pin, val ? HIGH : LOW);
    server.send(200, "application/json", "{\"status\":\"ok\",\"action\":\"digital_write\",\"pin\":" + String(pin) + ",\"val\":" + String(val ? 1 : 0) + "}");
  } else {
    // Read Mode
    pinMode(pin, INPUT);
    int readVal = digitalRead(pin);
    server.send(200, "application/json", "{\"status\":\"ok\",\"action\":\"digital_read\",\"pin\":" + String(pin) + ",\"val\":" + String(readVal) + "}");
  }
}

// ---------------------------------------------------------------------------
// 3. PWM / Dimmer (/pwm?pin=X&val=0-255)
// ---------------------------------------------------------------------------
void handlePwm() {
  if (!server.hasArg("pin") || !server.hasArg("val")) {
    server.send(400, "application/json", "{\"error\":\"Missing pin or val parameter\"}");
    return;
  }
  int pin = server.arg("pin").toInt();
  int val = constrain(server.arg("val").toInt(), 0, 255);

  ensurePwm(pin, pwmFreq, pwmResolution);
  ledcWrite(pin, val);

  server.send(200, "application/json", "{\"status\":\"ok\",\"action\":\"pwm\",\"pin\":" + String(pin) + ",\"val\":" + String(val) + "}");
}

// ---------------------------------------------------------------------------
// 4. Servo Controller (/servo?pin=X&angle=0-180)
// ---------------------------------------------------------------------------
void handleServo() {
  if (!server.hasArg("pin") || !server.hasArg("angle")) {
    server.send(400, "application/json", "{\"error\":\"Missing pin or angle parameter\"}");
    return;
  }
  int pin = server.arg("pin").toInt();
  int angle = constrain(server.arg("angle").toInt(), 0, 180);

  // Standard servo 50Hz: 0.5ms (0 deg) to 2.5ms (180 deg) in a 20ms period (16-bit: 0-65535)
  // 0.5ms / 20ms * 65535 ~ 1638; 2.5ms / 20ms * 65535 ~ 8192
  uint32_t duty = 1638 + ((8192 - 1638) * angle) / 180;

  ensurePwm(pin, servoFreq, servoResolution);
  ledcWrite(pin, duty);

  server.send(200, "application/json", "{\"status\":\"ok\",\"action\":\"servo\",\"pin\":" + String(pin) + ",\"angle\":" + String(angle) + "}");
}

// ---------------------------------------------------------------------------
// 5. Buzzer / Tone (/tone?pin=X&freq=1000&duration=300)
// ---------------------------------------------------------------------------
void handleTone() {
  if (!server.hasArg("pin")) {
    server.send(400, "application/json", "{\"error\":\"Missing pin parameter\"}");
    return;
  }
  int pin = server.arg("pin").toInt();
  int freq = server.hasArg("freq") ? server.arg("freq").toInt() : 1000;
  int duration = server.hasArg("duration") ? server.arg("duration").toInt() : 250;

  ensurePwm(pin, freq, 8);
  ledcWrite(pin, 128); // 50% duty square wave
  delay(duration);
  ledcWrite(pin, 0);   // Stop tone

  server.send(200, "application/json", "{\"status\":\"ok\",\"action\":\"tone\",\"pin\":" + String(pin) + ",\"freq\":" + String(freq) + ",\"duration\":" + String(duration) + "}");
}

// ---------------------------------------------------------------------------
// 6. Analog Read (/analog?pin=X)
// ---------------------------------------------------------------------------
void handleAnalog() {
  if (!server.hasArg("pin")) {
    server.send(400, "application/json", "{\"error\":\"Missing pin parameter\"}");
    return;
  }
  int pin = server.arg("pin").toInt();
  int adcVal = analogRead(pin);
  float voltage = (adcVal / 4095.0) * 3.3;

  server.send(200, "application/json", "{\"status\":\"ok\",\"action\":\"analog_read\",\"pin\":" + String(pin) + ",\"adc\":" + String(adcVal) + ",\"voltage\":" + String(voltage, 2) + "}");
}

// ---------------------------------------------------------------------------
// 7. Status & Capabilities (/status or /)
// ---------------------------------------------------------------------------
void handleStatus() {
  String json = "{\n";
  json += "  \"device\": \"Blinky-ESP32-Universal-Daemon\",\n";
  json += "  \"version\": \"1.0.0\",\n";
  json += "  \"uptime_seconds\": " + String(millis() / 1000) + ",\n";
  json += "  \"free_heap\": " + String(ESP.getFreeHeap()) + ",\n";
  json += "  \"ip\": \"" + WiFi.localIP().toString() + "\",\n";
  json += "  \"rssi\": " + String(WiFi.RSSI()) + ",\n";
  json += "  \"capabilities\": [\"rgb\", \"digital_io\", \"pwm\", \"servo\", \"tone\", \"analog\"]\n";
  json += "}";
  server.send(200, "application/json", json);
}

// ---------------------------------------------------------------------------
// Setup & Loop
// ---------------------------------------------------------------------------
void setup() {
  Serial.begin(115200);

  // Initialize RGB default pins to off
  ensurePwm(defaultRedPin, pwmFreq, pwmResolution);
  ensurePwm(defaultGreenPin, pwmFreq, pwmResolution);
  ensurePwm(defaultBluePin, pwmFreq, pwmResolution);
  ledcWrite(defaultRedPin, 0);
  ledcWrite(defaultGreenPin, 0);
  ledcWrite(defaultBluePin, 0);

  Serial.println("\n--- Starting Blinky Universal Micro-Daemon ---");
  Serial.print("Connecting to Wi-Fi: ");
  Serial.println(ssid);

  WiFi.setAutoReconnect(true);
  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) {
    delay(400);
    Serial.print(".");
  }

  // CRITICAL: Disable Wi-Fi modem sleep so ESP32 is instantly responsive 24/7
  WiFi.setSleep(false);

  Serial.println("\nWi-Fi Connected successfully!");
  Serial.print("ESP32 IP Address: ");
  Serial.println(WiFi.localIP());

  // Start mDNS responder so Blinky can reach it at http://blinky-esp32.local/
  if (MDNS.begin("blinky-esp32")) {
    Serial.println("mDNS responder started: http://blinky-esp32.local");
  }

  // Register Web Routes
  server.on("/", handleStatus);
  server.on("/status", handleStatus);
  server.on("/rgb", handleRgb);
  server.on("/digital", handleDigital);
  server.on("/pwm", handlePwm);
  server.on("/servo", handleServo);
  server.on("/tone", handleTone);
  server.on("/analog", handleAnalog);

  server.begin();
  Serial.println("Universal Daemon Server running and ready for Blinky commands!");
}

void loop() {
  server.handleClient();
  delay(2); // Yield CPU time to background Wi-Fi and RTOS tasks
}
