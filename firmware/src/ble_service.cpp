#include "ble_service.h"
#include "config.h"
#include "display.h"
#include "power.h"
#include "state.h"
#include <NimBLEDevice.h>

static NimBLEServer* pServer = nullptr;
static NimBLECharacteristic* pStatusChar = nullptr;
static NimBLECharacteristic* pInfoChar = nullptr;
static bool connected = false;

// Image receive buffer
static uint8_t* img_buffer = nullptr;
static size_t img_total_size = 0;
static size_t img_received = 0;
static uint16_t img_width = 0;
static uint16_t img_height = 0;
static uint8_t img_format = 0;

static void send_status_notify() {
    if (!pStatusChar) return;

    DisplayState st = state_get_current();
    uint8_t batt_pct = power_get_battery_percent();
    bool charging = power_is_charging();
    uint16_t batt_mv = power_get_battery_mv();

    uint8_t data[5];
    data[0] = (uint8_t)st;
    data[1] = batt_pct;
    data[2] = charging ? 1 : 0;
    data[3] = batt_mv & 0xFF;
    data[4] = (batt_mv >> 8) & 0xFF;

    pStatusChar->setValue(data, sizeof(data));
    if (connected) {
        pStatusChar->notify();
    }
}

class StateCommandCallback : public NimBLECharacteristicCallbacks {
    void onWrite(NimBLECharacteristic* pChar, NimBLEConnInfo& connInfo) override {
        NimBLEAttValue val = pChar->getValue();
        const uint8_t* data = val.data();
        size_t len = val.size();
        if (len < 1) return;

        uint8_t opcode = data[0];

        switch (opcode) {
            case OP_SET_PRESET: {
                if (len < 2) break;
                uint8_t state_id = data[1];
                if (state_id > STATE_OOF) break;
                DisplayState new_state = (DisplayState)state_id;
                state_set(new_state);
                if (new_state == STATE_OFF) {
                    display_off();
                } else {
                    display_on();
                    display_show_preset(new_state);
                }
                state_save_to_nvs();
                send_status_notify();
                Serial.printf("BLE: preset %d\n", state_id);
                break;
            }

            case OP_SET_CUSTOM_TEXT: {
                if (len < 5) break; // opcode + r + g + b + at least 1 char
                uint8_t r = data[1];
                uint8_t g = data[2];
                uint8_t b = data[3];
                // Extract text (rest of payload)
                size_t text_len = len - 4;
                char text[201];
                size_t copy_len = (text_len < 200) ? text_len : 200;
                memcpy(text, &data[4], copy_len);
                text[copy_len] = '\0';

                state_set(STATE_CUSTOM_TEXT);
                display_on();
                display_show_custom_text(text, r, g, b);
                state_save_to_nvs();
                send_status_notify();
                Serial.printf("BLE: custom text '%s'\n", text);
                break;
            }

            case OP_SLEEP: {
                state_set(STATE_OFF);
                display_off();
                state_save_to_nvs();
                send_status_notify();
                Serial.println("BLE: sleep command");
                // Deep sleep is handled in main loop after BLE disconnect
                power_enter_deep_sleep();
                break;
            }

            case OP_IMAGE_START: {
                if (len < 10) break;
                img_total_size = data[1] | (data[2] << 8) | (data[3] << 16) | (data[4] << 24);
                img_width = data[5] | (data[6] << 8);
                img_height = data[7] | (data[8] << 8);
                img_format = data[9];

                if (img_buffer) { free(img_buffer); img_buffer = nullptr; }

                if (img_total_size > 200000) {
                    Serial.println("BLE: image too large");
                    break;
                }
                img_buffer = (uint8_t*)malloc(img_total_size);
                img_received = 0;
                if (!img_buffer) {
                    Serial.println("BLE: malloc failed for image");
                }
                Serial.printf("BLE: image start %zu bytes, %dx%d\n",
                              img_total_size, img_width, img_height);
                break;
            }

            case OP_IMAGE_CHUNK: {
                if (!img_buffer || len < 3) break;
                uint16_t chunk_idx = data[1] | (data[2] << 8);
                size_t payload_len = len - 3;
                size_t offset = chunk_idx * 509; // MTU(512) - 3 byte header
                if (offset + payload_len > img_total_size) break;
                memcpy(img_buffer + offset, &data[3], payload_len);
                img_received += payload_len;
                break;
            }

            case OP_IMAGE_END: {
                if (!img_buffer || len < 5) break;
                uint32_t expected_crc = data[1] | (data[2] << 8) |
                                        (data[3] << 16) | (data[4] << 24);
                // TODO: verify CRC32
                (void)expected_crc;

                state_set(STATE_CUSTOM_IMAGE);
                display_on();
                display_show_image(img_buffer, img_total_size);
                state_save_to_nvs();
                send_status_notify();

                free(img_buffer);
                img_buffer = nullptr;
                img_received = 0;
                Serial.println("BLE: image complete");
                break;
            }

            case OP_SET_BRIGHTNESS: {
                if (len < 2) break;
                display_set_brightness(data[1]);
                Serial.printf("BLE: brightness %d\n", data[1]);
                break;
            }

            case OP_PING: {
                send_status_notify();
                Serial.println("BLE: ping");
                break;
            }
        }
    }
};

class ServerCallbacks : public NimBLEServerCallbacks {
    void onConnect(NimBLEServer* pServer, NimBLEConnInfo& connInfo) override {
        connected = true;
        // Request higher MTU for image transfers
        // NimBLE handles MTU negotiation automatically
        Serial.println("BLE: connected");
    }

    void onDisconnect(NimBLEServer* pServer, NimBLEConnInfo& connInfo, int reason) override {
        connected = false;
        Serial.printf("BLE: disconnected (reason %d)\n", reason);
        NimBLEDevice::startAdvertising();
    }
};

void ble_init() {
    NimBLEDevice::init(BLE_DEVICE_NAME);
    NimBLEDevice::setMTU(512);
    NimBLEDevice::setPower(ESP_PWR_LVL_P3); // +3 dBm

    pServer = NimBLEDevice::createServer();
    pServer->setCallbacks(new ServerCallbacks());

    NimBLEService* pService = pServer->createService(BLE_SERVICE_UUID);

    // State Command — write only
    NimBLECharacteristic* pCmdChar = pService->createCharacteristic(
        BLE_CHAR_STATE_CMD_UUID,
        NIMBLE_PROPERTY::WRITE | NIMBLE_PROPERTY::WRITE_NR
    );
    pCmdChar->setCallbacks(new StateCommandCallback());

    // Device Status — read + notify
    pStatusChar = pService->createCharacteristic(
        BLE_CHAR_DEV_STATUS_UUID,
        NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::NOTIFY
    );

    // Device Info — read only
    pInfoChar = pService->createCharacteristic(
        BLE_CHAR_DEV_INFO_UUID,
        NIMBLE_PROPERTY::READ
    );
    pInfoChar->setValue("{\"fw\":\"0.1.0\",\"hw\":\"waveshare-c6-amoled-1.8\"}");

    // Note: pService->start() is deprecated in NimBLE-Arduino 2.x — server start handles it

    NimBLEAdvertising* pAdvertising = NimBLEDevice::getAdvertising();
    pAdvertising->addServiceUUID(BLE_SERVICE_UUID);
    pAdvertising->setMinInterval(160);  // 100ms (* 0.625ms)
    pAdvertising->setMaxInterval(800);  // 500ms
    pAdvertising->start();

    Serial.println("BLE: advertising started");
}

void ble_notify_status(DisplayState state, uint8_t battery_pct, bool charging, uint16_t battery_mv) {
    if (!pStatusChar) return;

    uint8_t data[5];
    data[0] = (uint8_t)state;
    data[1] = battery_pct;
    data[2] = charging ? 1 : 0;
    data[3] = battery_mv & 0xFF;
    data[4] = (battery_mv >> 8) & 0xFF;

    pStatusChar->setValue(data, sizeof(data));
    if (connected) {
        pStatusChar->notify();
    }
}

bool ble_is_connected() {
    return connected;
}
