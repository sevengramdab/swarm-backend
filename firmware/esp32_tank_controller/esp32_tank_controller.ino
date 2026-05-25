/*
  ORBSTUDIO SWARM — ESP32 TANK CONTROLLER FIRMWARE
  AGENTS: 08 (Aqua-Biologist), 12 (Telemetry), 04 (Power Grid)
  
  HARDWARE: ESP32-DevKitC-32E
  SENSORS:  DS18B20 (1-Wire), DHT22 (digital), Atlas EZO-pH (I2C), Atlas EZO-DO (I2C)
  ACTUATORS: 8-channel relay module (SONGLE SRD-05VDC-SL-C)
  
  CIRCUIT: Reads all tank sensors every 5 seconds, controls relays based on
           setpoints from the SimplePod Swarm API, reports telemetry back.
           
  WIRING:
    - DS18B20 VCC → 3.3V, GND → GND, DATA → GPIO4 (with 4.7kΩ pull-up to 3.3V)
    - DHT22 VCC → 3.3V, GND → GND, DATA → GPIO5 (with 10kΩ pull-up)
    - Atlas EZO-pH: VCC → 3.3V, GND → GND, SDA → GPIO21, SCL → GPIO22
    - Atlas EZO-DO: VCC → 3.3V, GND → GND, SDA → GPIO21, SCL → GPIO22 (shared bus)
    - Relay Module: VCC → 5V, GND → GND, IN1-IN8 → GPIO12-19 (via 1kΩ resistors)
    
  INSTALL LIBRARIES (Arduino IDE → Sketch → Include Library → Manage Libraries):
    - OneWire by Paul Stoffregen
    - DallasTemperature by Miles Burton
    - DHT sensor library by Adafruit
    - ArduinoJson by Benoit Blanchon
    - WiFiManager by tzapu (optional, for config portal)
    
  TIMESTAMP: 2026-05-22_1425_PST
*/

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <DHT.h>
#include <Wire.h>

// ═══════════════════════════════════════════════════════════════════════════
// CONFIGURATION — CHANGE THESE FOR YOUR NETWORK
// ═══════════════════════════════════════════════════════════════════════════

const char* WIFI_SSID     = "YOUR_WIFI_SSID";       // <--- CHANGE THIS
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";   // <--- CHANGE THIS
const char* API_BASE_URL  = "http://192.168.1.100:8000"; // <--- CHANGE TO YOUR PI's IP
const char* CONTROLLER_ID = "tank_controller_01";   // Unique ID for this ESP32

// How often to read sensors and report (milliseconds)
const unsigned long REPORT_INTERVAL_MS = 5000;

// ═══════════════════════════════════════════════════════════════════════════
// PIN DEFINITIONS — MATCH YOUR WIRING SCHEMATIC
// ═══════════════════════════════════════════════════════════════════════════

// DS18B20 1-Wire bus
#define ONE_WIRE_BUS 4

// DHT22 air temp/humidity
#define DHT_PIN 5
#define DHT_TYPE DHT22

// I2C pins (shared with Atlas EZO circuits)
#define I2C_SDA 21
#define I2C_SCL 22

// Atlas EZO I2C addresses
#define EZO_PH_ADDRESS  0x63   // pH circuit default
#define EZO_DO_ADDRESS  0x61   // Dissolved Oxygen circuit default

// Relay module GPIOs (8 channels, active LOW)
#define RELAY_CIRCULATION_PUMP  12   // IN1 — Main water circulation
#define RELAY_AERATION_PUMP     13   // IN2 — Air stone pump
#define RELAY_HEATER_BACKUP     14   // IN3 — Electric immersion heater
#define RELAY_SOLENOID_VALVE    15   // IN4 — Auto-fill / drain valve
#define RELAY_SPARE_5           16   // IN5
#define RELAY_SPARE_6           17   // IN6
#define RELAY_SPARE_7           18   // IN7
#define RELAY_SPARE_8           19   // IN8

// ═══════════════════════════════════════════════════════════════════════════
// GLOBAL OBJECTS
// ═══════════════════════════════════════════════════════════════════════════

OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature ds18b20(&oneWire);
DHT dht(DHT_PIN, DHT_TYPE);

// Device addresses for DS18B20 sensors (discovered at runtime)
DeviceAddress ds18b20Addresses[10];
int ds18b20Count = 0;

// Relay state tracking
bool relayStates[8] = {false, false, false, false, false, false, false, false};

// Timing
unsigned long lastReportTime = 0;

// ═══════════════════════════════════════════════════════════════════════════
// SETUP
// ═══════════════════════════════════════════════════════════════════════════

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n╔═══════════════════════════════════════════════════════════════╗");
  Serial.println("║  ORBSTUDIO ESP32 TANK CONTROLLER — BOOT SEQUENCE            ║");
  Serial.println("╚═══════════════════════════════════════════════════════════════╝");

  // Initialize I2C
  Wire.begin(I2C_SDA, I2C_SCL);
  Serial.println("[OK] I2C bus initialized (SDA=GPIO21, SCL=GPIO22)");

  // Initialize DS18B20
  ds18b20.begin();
  ds18b20Count = ds18b20.getDeviceCount();
  Serial.print("[OK] DS18B20 sensors found: ");
  Serial.println(ds18b20Count);
  
  for (int i = 0; i < ds18b20Count && i < 10; i++) {
    if (ds18b20.getAddress(ds18b20Addresses[i], i)) {
      Serial.print("  Sensor "); Serial.print(i);
      Serial.print(" address: ");
      printAddress(ds18b20Addresses[i]);
      Serial.println();
    }
  }

  // Initialize DHT22
  dht.begin();
  Serial.println("[OK] DHT22 initialized (GPIO5)");

  // Initialize relay pins
  pinMode(RELAY_CIRCULATION_PUMP, OUTPUT);
  pinMode(RELAY_AERATION_PUMP, OUTPUT);
  pinMode(RELAY_HEATER_BACKUP, OUTPUT);
  pinMode(RELAY_SOLENOID_VALVE, OUTPUT);
  pinMode(RELAY_SPARE_5, OUTPUT);
  pinMode(RELAY_SPARE_6, OUTPUT);
  pinMode(RELAY_SPARE_7, OUTPUT);
  pinMode(RELAY_SPARE_8, OUTPUT);
  
  // Ensure all relays are OFF (HIGH for active-LOW modules)
  setRelay(0, false);
  setRelay(1, false);
  setRelay(2, false);
  setRelay(3, false);
  setRelay(4, false);
  setRelay(5, false);
  setRelay(6, false);
  setRelay(7, false);
  Serial.println("[OK] All relays initialized OFF");

  // Connect to WiFi
  Serial.print("[...] Connecting to WiFi: ");
  Serial.println(WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  
  int wifiAttempts = 0;
  while (WiFi.status() != WL_CONNECTED && wifiAttempts < 30) {
    delay(500);
    Serial.print(".");
    wifiAttempts++;
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[OK] WiFi connected!");
    Serial.print("[OK] IP address: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("\n[ERR] WiFi connection failed — running in standalone mode");
  }

  Serial.println("\n[OK] Boot complete. Entering main loop...\n");
}

// ═══════════════════════════════════════════════════════════════════════════
// MAIN LOOP
// ═══════════════════════════════════════════════════════════════════════════

void loop() {
  unsigned long now = millis();

  if (now - lastReportTime >= REPORT_INTERVAL_MS) {
    lastReportTime = now;

    // ── READ ALL SENSORS ──
    SensorData data = readAllSensors();
    
    // ── FETCH COMMANDS FROM API ──
    RelayCommands commands = fetchRelayCommands();
    
    // ── APPLY RELAY COMMANDS ──
    applyRelayCommands(commands);
    
    // ── REPORT TELEMETRY TO API ──
    reportTelemetry(data);
    
    // ── PRINT TO SERIAL FOR DEBUG ──
    printSensorData(data);
  }

  yield();
}

// ═══════════════════════════════════════════════════════════════════════════
// SENSOR READING FUNCTIONS
// ═══════════════════════════════════════════════════════════════════════════

struct SensorData {
  float waterTempC;
  float airTempC;
  float humidityPct;
  float ph;
  float dissolvedO2;
  bool waterTempValid;
  bool airTempValid;
  bool phValid;
  bool doValid;
  unsigned long timestamp;
};

SensorData readAllSensors() {
  SensorData data = {};
  data.timestamp = millis();

  // DS18B20 water temperature (read first sensor found)
  ds18b20.requestTemperatures();
  if (ds18b20Count > 0) {
    data.waterTempC = ds18b20.getTempC(ds18b20Addresses[0]);
    data.waterTempValid = (data.waterTempC != DEVICE_DISCONNECTED_C);
  } else {
    data.waterTempValid = false;
  }

  // DHT22 air temp & humidity
  data.airTempC = dht.readTemperature();
  data.humidityPct = dht.readHumidity();
  data.airTempValid = !isnan(data.airTempC) && !isnan(data.humidityPct);

  // Atlas EZO pH
  float phReading = readAtlasEZO(EZO_PH_ADDRESS);
  if (phReading >= 0.0 && phReading <= 14.0) {
    data.ph = phReading;
    data.phValid = true;
  } else {
    data.phValid = false;
  }

  // Atlas EZO Dissolved Oxygen
  float doReading = readAtlasEZO(EZO_DO_ADDRESS);
  if (doReading >= 0.0 && doReading <= 20.0) {
    data.dissolvedO2 = doReading;
    data.doValid = true;
  } else {
    data.doValid = false;
  }

  return data;
}

// Read any Atlas EZO circuit via I2C
float readAtlasEZO(uint8_t address) {
  Wire.beginTransmission(address);
  Wire.write("R");           // Send 'R' command (read)
  Wire.endTransmission();
  
  delay(1000);               // Atlas EZO needs ~1 second per reading
  
  Wire.requestFrom(address, 20, (uint8_t)1);
  
  char response[20];
  int i = 0;
  while (Wire.available() && i < 19) {
    response[i++] = Wire.read();
  }
  response[i] = '\0';
  
  // Response format: "1,7.23" (status, value)
  if (response[0] == '1') {
    char* comma = strchr(response, ',');
    if (comma != NULL) {
      return atof(comma + 1);
    }
  }
  return -1.0;  // Invalid reading
}

// ═══════════════════════════════════════════════════════════════════════════
// RELAY CONTROL
// ═══════════════════════════════════════════════════════════════════════════

struct RelayCommands {
  bool circulationPump;
  bool aerationPump;
  bool heaterBackup;
  bool solenoidValve;
};

void setRelay(int channel, bool state) {
  int pin;
  switch (channel) {
    case 0: pin = RELAY_CIRCULATION_PUMP; break;
    case 1: pin = RELAY_AERATION_PUMP;    break;
    case 2: pin = RELAY_HEATER_BACKUP;    break;
    case 3: pin = RELAY_SOLENOID_VALVE;   break;
    case 4: pin = RELAY_SPARE_5;          break;
    case 5: pin = RELAY_SPARE_6;          break;
    case 6: pin = RELAY_SPARE_7;          break;
    case 7: pin = RELAY_SPARE_8;          break;
    default: return;
  }
  // Active-LOW relay module: LOW = relay ON, HIGH = relay OFF
  digitalWrite(pin, state ? LOW : HIGH);
  relayStates[channel] = state;
}

void applyRelayCommands(RelayCommands cmd) {
  setRelay(0, cmd.circulationPump);
  setRelay(1, cmd.aerationPump);
  setRelay(2, cmd.heaterBackup);
  setRelay(3, cmd.solenoidValve);
}

// ═══════════════════════════════════════════════════════════════════════════
// API COMMUNICATION
// ═══════════════════════════════════════════════════════════════════════════

RelayCommands fetchRelayCommands() {
  RelayCommands cmd = {true, true, false, false};  // Defaults: pumps ON, others OFF
  
  if (WiFi.status() != WL_CONNECTED) {
    return cmd;  // Default safe state if no WiFi
  }

  HTTPClient http;
  String url = String(API_BASE_URL) + "/orbstudio/status";
  http.begin(url);
  http.setTimeout(3000);
  
  int httpCode = http.GET();
  if (httpCode == 200) {
    String payload = http.getString();
    StaticJsonDocument<512> doc;
    DeserializationError error = deserializeJson(doc, payload);
    
    if (!error) {
      bool running = doc["running"] | false;
      // If Main Breaker is OPEN, shut down non-essential loads
      if (!running) {
        cmd.circulationPump = true;   // Keep circulation (fish need flow)
        cmd.aerationPump = true;      // Keep aeration (fish need oxygen)
        cmd.heaterBackup = false;
        cmd.solenoidValve = false;
      }
    }
  }
  http.end();
  return cmd;
}

void reportTelemetry(SensorData data) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[WARN] No WiFi — skipping telemetry report");
    return;
  }

  StaticJsonDocument<512> doc;
  doc["controller_id"] = CONTROLLER_ID;
  doc["timestamp"] = data.timestamp;
  
  JsonObject sensors = doc.createNestedObject("sensors");
  if (data.waterTempValid) sensors["water_temp_c"] = data.waterTempC;
  if (data.airTempValid) {
    sensors["air_temp_c"] = data.airTempC;
    sensors["humidity_pct"] = data.humidityPct;
  }
  if (data.phValid) sensors["ph"] = data.ph;
  if (data.doValid) sensors["dissolved_o2_mg_l"] = data.dissolvedO2;
  
  JsonObject relays = doc.createNestedObject("relays");
  relays["circulation_pump"] = relayStates[0];
  relays["aeration_pump"] = relayStates[1];
  relays["heater_backup"] = relayStates[2];
  relays["solenoid_valve"] = relayStates[3];

  String jsonPayload;
  serializeJson(doc, jsonPayload);

  HTTPClient http;
  String url = String(API_BASE_URL) + "/hardware/telemetry";  // Endpoint to be added
  http.begin(url);
  http.addHeader("Content-Type", "application/json");
  http.setTimeout(3000);
  
  int httpCode = http.POST(jsonPayload);
  if (httpCode == 200) {
    Serial.println("[OK] Telemetry reported to API");
  } else {
    Serial.print("[WARN] Telemetry report failed: HTTP ");
    Serial.println(httpCode);
  }
  http.end();
}

// ═══════════════════════════════════════════════════════════════════════════
// DEBUG OUTPUT
// ═══════════════════════════════════════════════════════════════════════════

void printSensorData(SensorData data) {
  Serial.println("┌─────────────────────────────────────────────────────────────┐");
  Serial.println("│  SENSOR READING — Timestamp: " + String(data.timestamp));
  Serial.println("├─────────────────────────────────────────────────────────────┤");
  
  if (data.waterTempValid) {
    Serial.print("│  Water Temp:    "); Serial.print(data.waterTempC, 1); Serial.println(" °C");
  } else {
    Serial.println("│  Water Temp:    [OFFLINE]");
  }
  
  if (data.airTempValid) {
    Serial.print("│  Air Temp:      "); Serial.print(data.airTempC, 1); Serial.println(" °C");
    Serial.print("│  Humidity:      "); Serial.print(data.humidityPct, 1); Serial.println(" %");
  } else {
    Serial.println("│  Air Temp/Hum:  [OFFLINE]");
  }
  
  if (data.phValid) {
    Serial.print("│  pH:            "); Serial.println(data.ph, 2);
  } else {
    Serial.println("│  pH:            [OFFLINE]");
  }
  
  if (data.doValid) {
    Serial.print("│  Dissolved O2:  "); Serial.print(data.dissolvedO2, 2); Serial.println(" mg/L");
  } else {
    Serial.println("│  Dissolved O2:  [OFFLINE]");
  }
  
  Serial.println("│  Relays:  Circ=" + String(relayStates[0] ? "ON" : "OFF") +
                 "  Air=" + String(relayStates[1] ? "ON" : "OFF") +
                 "  Heat=" + String(relayStates[2] ? "ON" : "OFF") +
                 "  Valve=" + String(relayStates[3] ? "ON" : "OFF"));
  Serial.println("└─────────────────────────────────────────────────────────────┘");
}

void printAddress(DeviceAddress addr) {
  for (uint8_t i = 0; i < 8; i++) {
    if (addr[i] < 16) Serial.print("0");
    Serial.print(addr[i], HEX);
  }
}
