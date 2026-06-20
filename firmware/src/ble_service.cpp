#include "ble_service.h"
#include "config.h"
#include "display.h"
#include "power.h"
#include "state.h"
#include "audio.h"
#include "pir.h"
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
    bool vbus = power_is_vbus_in();

    uint8_t data[7];
    data[0] = (uint8_t)st;
    data[1] = batt_pct;
    data[2] = charging ? 1 : 0;
    data[3] = batt_mv & 0xFF;
    data[4] = (batt_mv >> 8) & 0xFF;
    data[5] = vbus ? 1 : 0;
    data[6] = pir_motion_detected() ? 1 : 0;

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

        // All display/power work is deferred to main loop via pending command.
        // BLE callbacks run in NimBLE's task with limited stack — never call
        // display or power functions directly from here.
        PendingCommand cmd;

        switch (opcode) {
            case OP_SET_PRESET: {
                if (len < 2) break;
                uint8_t state_id = data[1];
                // Only allow firmware preset states; STATE_CUSTOM_TEXT/IMAGE/SLEEPING are not presets
                if (state_id != STATE_OFF && state_id != STATE_IN_MEETING &&
                    state_id != STATE_WFH  && state_id != STATE_OOF &&
                    state_id != STATE_AVAILABLE) break;
                cmd.valid = true;
                cmd.set_state = true;
                cmd.state = (DisplayState)state_id;
                pending_set(cmd);
                send_status_notify();
                Serial.printf("BLE: queued preset %d\n", state_id);
                break;
            }

            case OP_SET_CUSTOM_TEXT: {
                // [opcode][bg_r][bg_g][bg_b][fg_r][fg_g][fg_b][text...]
                if (len < 8) break;
                cmd.valid = true;
                cmd.set_state = true;
                cmd.state = STATE_CUSTOM_TEXT;
                cmd.r = data[1]; cmd.g = data[2]; cmd.b = data[3];
                cmd.fg_r = data[4]; cmd.fg_g = data[5]; cmd.fg_b = data[6];
                size_t copy_len = min(len - 7, (size_t)200);
                memcpy(cmd.text, &data[7], copy_len);
                cmd.text[copy_len] = '\0';
                pending_set(cmd);
                send_status_notify();
                Serial.printf("BLE: queued custom text\n");
                break;
            }

            case OP_SLEEP: {
                cmd.valid = true;
                cmd.set_state = true;
                cmd.state = STATE_OFF;
                cmd.sleep = true;
                pending_set(cmd);
                send_status_notify();
                Serial.println("BLE: queued sleep");
                break;
            }

            case OP_IMAGE_START: {
                if (len < 10) break;
                img_total_size = data[1] | (data[2] << 8) | (data[3] << 16) | (data[4] << 24);
                img_width = data[5] | (data[6] << 8);
                img_height = data[7] | (data[8] << 8);
                img_format = data[9];
                if (img_buffer) { free(img_buffer); img_buffer = nullptr; }
                if (img_total_size > 200000) { Serial.println("BLE: image too large"); break; }
                img_buffer = (uint8_t*)malloc(img_total_size);
                img_received = 0;
                if (!img_buffer) Serial.println("BLE: malloc failed");
                break;
            }

            case OP_IMAGE_CHUNK: {
                if (!img_buffer || len < 3) break;
                // Append sequentially — works for any chunk size
                size_t payload_len = len - 3;
                if (img_received + payload_len <= img_total_size) {
                    memcpy(img_buffer + img_received, &data[3], payload_len);
                    img_received += payload_len;
                }
                break;
            }

            case OP_IMAGE_END: {
                if (!img_buffer || len < 5) break;
                if (img_received < img_total_size) {
                    Serial.printf("BLE: image incomplete %zu/%zu\n", img_received, img_total_size);
                    break;
                }
                cmd.valid = true;
                cmd.set_state = true;
                cmd.state = STATE_CUSTOM_IMAGE;
                pending_set(cmd);
                send_status_notify();
                Serial.printf("BLE: queued image %zu bytes\n", img_total_size);
                break;
            }

            case OP_SET_BRIGHTNESS: {
                if (len < 2) break;
                cmd.valid = true;
                // set_state intentionally left false — brightness only, no display redraw
                cmd.brightness = data[1];
                pending_set(cmd);
                break;
            }

            case OP_PING: {
                send_status_notify();
                break;
            }

            case OP_SET_MUTE: {
                if (len < 2) break;
                audio_set_mute(data[1] != 0);
                Serial.printf("BLE: mute %s\n", data[1] ? "on" : "off");
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

    // Append last 2 MAC bytes so each unit is distinguishable: "MeetingLight-XXXX"
    {
        NimBLEAddress addr = NimBLEDevice::getAddress();
        const uint8_t* raw = addr.getVal();  // 6 bytes, index 5 = most significant
        char suffix[16];
        snprintf(suffix, sizeof(suffix), "%s-%02X%02X", BLE_DEVICE_NAME, raw[1], raw[0]);
        NimBLEDevice::setDeviceName(suffix);
        Serial.printf("BLE: device name set to %s\n", suffix);
    }

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
    pAdvertising->setMinInterval(160);  // 100ms (units of 0.625ms)
    pAdvertising->setMaxInterval(320);  // 200ms — tighter window for faster initial connection
    pAdvertising->start();

    Serial.println("BLE: advertising started");
}

void ble_notify_status(DisplayState state, uint8_t battery_pct, bool charging, uint16_t battery_mv, bool vbus, bool pir_motion) {
    if (!pStatusChar) return;

    uint8_t data[7];
    data[0] = (uint8_t)state;
    data[1] = battery_pct;
    data[2] = charging ? 1 : 0;
    data[3] = battery_mv & 0xFF;
    data[4] = (battery_mv >> 8) & 0xFF;
    data[5] = vbus ? 1 : 0;
    data[6] = pir_motion ? 1 : 0;

    pStatusChar->setValue(data, sizeof(data));
    if (connected) {
        pStatusChar->notify();
    }
}

bool ble_is_connected() {
    return connected;
}

String ble_get_mac_address() {
    // Returns uppercase MAC, e.g. "AA:BB:CC:DD:EE:FF"
    std::string addr = NimBLEDevice::getAddress().toString();
    String s = String(addr.c_str());
    s.toUpperCase();
    return s;
}

const uint8_t* ble_get_image_data() { return img_buffer; }
size_t ble_get_image_len() { return img_total_size; }
void ble_free_image() {
    if (img_buffer) { free(img_buffer); img_buffer = nullptr; }
    img_total_size = 0; img_received = 0;
}
