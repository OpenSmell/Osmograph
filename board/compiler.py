from pathlib import Path

SKETCH_TEMPLATE = '''// Osmograph Universal Firmware
// Works over USB Serial AND WiFi at the same time.
// Connects to any Osmograph app automatically.
//
// TO CUSTOMIZE SENSOR PINS:
//   Just edit the SENSOR_PINS array below with your GPIO pin numbers.
//   The board will read them in order and send readings every ~100ms.
//
//   Default pins: 32,33,34,35,25,26  (covers most MQ sensor boards)
//   All ESP32 ADC-safe pins: 32,33,34,35,36,37,38,39,25,26,27,14,12,13
//
// HOW TO USE:
//   1. USB: plug in, open Osmograph, select Serial port
//   2. WiFi: ESP32 creates "OSMOGRAPH-XXXX" network. Connect your computer
//      to that WiFi, then in Osmograph switch to WiFi mode and Discover.
//      Or connect directly to 192.168.4.1:8080

#include <WiFi.h>
#include <ESPmDNS.h>

// ── EDIT YOUR SENSOR PINS HERE ──────────────────────────────────────
// List the GPIO pins your sensors are connected to, in order.
// The Osmograph app reads them left to right.
const int SENSOR_PINS[] = { 32, 33, 34, 35, 25, 26 };
const int SENSOR_COUNT = sizeof(SENSOR_PINS) / sizeof(SENSOR_PINS[0]);
// ────────────────────────────────────────────────────────────────────

const int TCP_PORT = 8080;
const unsigned long PRINT_INTERVAL = 100;

unsigned long lastPrint = 0;
WiFiServer server(TCP_PORT);
WiFiClient clients[8];

void setup() {
    Serial.begin(115200);
    analogReadResolution(12);
    for (int i = 0; i < SENSOR_COUNT; i++) {
        pinMode(SENSOR_PINS[i], INPUT);
    }

    // Start WiFi AP
    uint8_t mac[6];
    WiFi.macAddress(mac);
    char ssid[32];
    snprintf(ssid, sizeof(ssid), "OSMOGRAPH-%02X%02X%02X", mac[3], mac[4], mac[5]);
    WiFi.mode(WIFI_AP);
    WiFi.softAP(ssid, NULL);
    Serial.print("WiFi AP: ");
    Serial.print(ssid);
    Serial.print(" IP: ");
    Serial.println(WiFi.softAPIP());

    server.begin();

    if (MDNS.begin("osmograph")) {
        MDNS.addService("_osmograph", "_tcp", TCP_PORT);
        Serial.println("mDNS: osmograph.local");
    }

    Serial.print("Sensor pins: ");
    for (int i = 0; i < SENSOR_COUNT; i++) {
        Serial.print(SENSOR_PINS[i]);
        if (i < SENSOR_COUNT - 1) Serial.print(", ");
    }
    Serial.println();
    Serial.println("Osmograph firmware ready");
}

void handleClients() {
    WiFiClient newClient = server.available();
    if (newClient) {
        for (int i = 0; i < 8; i++) {
            if (!clients[i]) {
                clients[i] = newClient;
                break;
            }
        }
    }
    for (int i = 0; i < 8; i++) {
        if (clients[i] && !clients[i].connected()) {
            clients[i].stop();
        }
    }
}

void readAndSend() {
    String data = "OSM";
    for (int i = 0; i < SENSOR_COUNT; i++) {
        data += ",";
        data += String(analogRead(SENSOR_PINS[i]));
    }
    data += "\\n";

    // USB Serial
    Serial.print(data);

    // WiFi TCP
    for (int i = 0; i < 8; i++) {
        if (clients[i] && clients[i].connected()) {
            clients[i].print(data);
        }
    }
}

void loop() {
    handleClients();
    unsigned long now = millis();
    if (now - lastPrint >= PRINT_INTERVAL) {
        lastPrint = now;
        readAndSend();
    }
}
'''

PLATFORMIO_INI = '''[env:esp32]
platform = espressif32
board = esp32
framework = arduino
monitor_speed = 115200
board_build.flash_mode = dio
board_build.f_cpu = 240000000L
'''


class FirmwareCompiler:

    @staticmethod
    def generate_sketch(
        pins: list[int] | None = None,
        interval_ms: int = 100,
    ) -> str:
        if pins:
            pin_list = ", ".join(str(p) for p in pins)
            sensor_count = len(pins)
            template_filled = SKETCH_TEMPLATE.replace(
                "{ 32, 33, 34, 35, 25, 26 }",
                "{ " + pin_list + " }"
            )
            # Also update the comment listing to match
            return template_filled
        return SKETCH_TEMPLATE  # default pins

    @staticmethod
    def generate_platformio_ini() -> str:
        return PLATFORMIO_INI

    @staticmethod
    def export_sketch(
        output_dir: str | Path,
        pins: list[int] | None = None,
    ) -> Path:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        src_dir = out / "src"
        src_dir.mkdir(parents=True, exist_ok=True)
        (src_dir / "main.cpp").write_text(FirmwareCompiler.generate_sketch(pins))
        (out / "platformio.ini").write_text(FirmwareCompiler.generate_platformio_ini())
        return out
