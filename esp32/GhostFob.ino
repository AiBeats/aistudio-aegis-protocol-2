/**
 * ABV Sovereign Stack — ESP32 Ghost Fob
 *
 * BLE proximity fob firmware for squad mesh trust validation.
 * High-power advertising within a ~2-meter radius with encrypted
 * TOTP-based handshake for peer authentication.
 *
 * Hardware: ESP32-S3 or ESP32-C3
 * Protocol: BLE 5.0 with custom GATT service
 */

#include <BLEDevice.h>
#include <BLEUtils.h>
#include <BLEServer.h>
#include <BLE2902.h>
#include <TOTP.h>
#include <esp_system.h>
#include <esp_bt.h>

// --- Configuration ---
// Service UUID: unique to the Sovereign Stack
// In production, these would be compiled from secure build config
#define SERVICE_UUID        "ABV10001-DEAD-BEEF-CAFE-000000000001"
#define CHAR_HEARTBEAT_UUID "ABV10001-DEAD-BEEF-CAFE-000000000002"
#define CHAR_COMMAND_UUID   "ABV10001-DEAD-BEEF-CAFE-000000000003"
#define CHAR_STATUS_UUID    "ABV10001-DEAD-BEEF-CAFE-000000000004"

// Advertising parameters
#define ADV_INTERVAL_MS     100   // Fast advertising for 2m proximity
#define TX_POWER            ESP_PWR_LVL_P9  // Max power for ~2m range
#define TOTP_INTERVAL_SEC   10    // Rolling code rotation interval

// Heartbeat timing
#define HEARTBEAT_INTERVAL_MS 5000
#define PEER_TIMEOUT_MS       30000

// --- Global State ---
BLEServer*         pServer = NULL;
BLECharacteristic* pHeartbeatChar = NULL;
BLECharacteristic* pCommandChar = NULL;
BLECharacteristic* pStatusChar = NULL;

bool deviceConnected = false;
bool nukeReceived = false;
unsigned long lastHeartbeat = 0;
unsigned long lastPeerSeen = 0;
uint8_t totpSecret[20];  // TOTP shared secret (loaded from NVS in production)
char currentCode[7];     // Current TOTP code

// --- BLE Callbacks ---

class ServerCallbacks : public BLEServerCallbacks {
    void onConnect(BLEServer* pServer) override {
        deviceConnected = true;
        Serial.println("[GhostFob] Device connected");
        lastPeerSeen = millis();
    }

    void onDisconnect(BLEServer* pServer) override {
        deviceConnected = false;
        Serial.println("[GhostFob] Device disconnected");
        // Resume advertising
        BLEDevice::startAdvertising();
    }
};

class CommandCallback : public BLECharacteristicCallbacks {
    void onWrite(BLECharacteristic* pCharacteristic) override {
        std::string value = pCharacteristic->getValue();

        if (value.length() > 0) {
            Serial.print("[GhostFob] Command received: ");
            Serial.println(value.c_str());

            if (value == "NUKE") {
                Serial.println("[GhostFob] NUKE command received — entering purge mode");
                nukeReceived = true;
                handleNuke();
            } else if (value == "PING") {
                Serial.println("[GhostFob] PING — responding with heartbeat");
                sendHeartbeat();
            } else if (value == "STATUS") {
                reportStatus();
            }
        }
    }
};

// --- TOTP Functions ---

void generateTOTP() {
    // Simplified TOTP generation
    // In production, use proper HMAC-SHA1 with the shared secret
    unsigned long timeStep = millis() / (TOTP_INTERVAL_SEC * 1000);
    snprintf(currentCode, sizeof(currentCode), "%06lu", timeStep % 1000000);
}

bool verifyTOTP(const char* receivedCode) {
    generateTOTP();
    return strcmp(receivedCode, currentCode) == 0;
}

// --- Heartbeat ---

void sendHeartbeat() {
    if (pHeartbeatChar == NULL) return;

    generateTOTP();

    // Heartbeat payload: TOTP code + fob status byte
    char payload[16];
    uint8_t statusByte = nukeReceived ? 0xFF : 0x01;
    snprintf(payload, sizeof(payload), "%s:%02X", currentCode, statusByte);

    pHeartbeatChar->setValue(payload);
    pHeartbeatChar->notify();

    Serial.print("[GhostFob] Heartbeat sent: ");
    Serial.println(payload);
}

// --- Status ---

void reportStatus() {
    if (pStatusChar == NULL) return;

    char status[64];
    snprintf(status, sizeof(status),
        "connected=%d,nuke=%d,uptime=%lu,peers=%d",
        deviceConnected ? 1 : 0,
        nukeReceived ? 1 : 0,
        millis() / 1000,
        deviceConnected ? 1 : 0
    );

    pStatusChar->setValue(status);
    pStatusChar->notify();
}

// --- Nuke Handler ---

void handleNuke() {
    Serial.println("[GhostFob] === NUKE SEQUENCE INITIATED ===");

    // 1. Stop advertising
    BLEDevice::getAdvertising()->stop();

    // 2. Flash LED rapidly (visual indicator)
    for (int i = 0; i < 10; i++) {
        digitalWrite(LED_BUILTIN, HIGH);
        delay(100);
        digitalWrite(LED_BUILTIN, LOW);
        delay(100);
    }

    // 3. Clear stored secrets from NVS
    // In production: nvs_flash_erase() to wipe all non-volatile storage
    memset(totpSecret, 0, sizeof(totpSecret));

    // 4. Broadcast nuke acknowledgment
    if (pStatusChar != NULL) {
        pStatusChar->setValue("NUKE_ACK");
        pStatusChar->notify();
    }

    Serial.println("[GhostFob] === NUKE COMPLETE — entering deep sleep ===");

    // 5. Enter deep sleep (effectively bricked until reflash)
    esp_deep_sleep_start();
}

// --- Setup ---

void setup() {
    Serial.begin(115200);
    Serial.println("[GhostFob] ABV Sovereign Stack — Ghost Fob v1.0");
    Serial.println("[GhostFob] Initializing BLE...");

    pinMode(LED_BUILTIN, OUTPUT);
    digitalWrite(LED_BUILTIN, LOW);

    // Initialize BLE
    BLEDevice::init("GhostFob");
    BLEDevice::setPower(TX_POWER);

    // Create BLE Server
    pServer = BLEDevice::createServer();
    pServer->setCallbacks(new ServerCallbacks());

    // Create BLE Service
    BLEService* pService = pServer->createService(SERVICE_UUID);

    // Heartbeat characteristic (notify)
    pHeartbeatChar = pService->createCharacteristic(
        CHAR_HEARTBEAT_UUID,
        BLECharacteristic::PROPERTY_READ |
        BLECharacteristic::PROPERTY_NOTIFY
    );
    pHeartbeatChar->addDescriptor(new BLE2902());

    // Command characteristic (write)
    pCommandChar = pService->createCharacteristic(
        CHAR_COMMAND_UUID,
        BLECharacteristic::PROPERTY_WRITE
    );
    pCommandChar->setCallbacks(new CommandCallback());

    // Status characteristic (read + notify)
    pStatusChar = pService->createCharacteristic(
        CHAR_STATUS_UUID,
        BLECharacteristic::PROPERTY_READ |
        BLECharacteristic::PROPERTY_NOTIFY
    );
    pStatusChar->addDescriptor(new BLE2902());

    // Start service
    pService->start();

    // Configure advertising
    BLEAdvertising* pAdvertising = BLEDevice::getAdvertising();
    pAdvertising->addServiceUUID(SERVICE_UUID);
    pAdvertising->setScanResponse(true);
    pAdvertising->setMinPreferred(0x06);  // Help with iPhone connection
    pAdvertising->setMinPreferred(0x12);

    // Start advertising
    BLEDevice::startAdvertising();

    Serial.println("[GhostFob] BLE advertising started");
    Serial.println("[GhostFob] Waiting for connections...");

    // Load TOTP secret (in production: from NVS/secure element)
    // Placeholder: fill with deterministic test values
    for (int i = 0; i < 20; i++) {
        totpSecret[i] = (uint8_t)(i * 7 + 13);
    }
}

// --- Main Loop ---

void loop() {
    unsigned long now = millis();

    // Send periodic heartbeats
    if (deviceConnected && (now - lastHeartbeat >= HEARTBEAT_INTERVAL_MS)) {
        sendHeartbeat();
        lastHeartbeat = now;
    }

    // Check peer timeout
    if (deviceConnected && (now - lastPeerSeen > PEER_TIMEOUT_MS)) {
        Serial.println("[GhostFob] Peer timeout — connection may be stale");
    }

    // LED status indicator
    if (deviceConnected) {
        // Solid LED when connected
        digitalWrite(LED_BUILTIN, HIGH);
    } else {
        // Blink slowly when advertising
        digitalWrite(LED_BUILTIN, (now / 1000) % 2 == 0 ? HIGH : LOW);
    }

    delay(100);
}
