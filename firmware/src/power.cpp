#include "power.h"
#include "config.h"
#include <XPowersLib.h>
#include <Wire.h>
#include <esp_sleep.h>

static XPowersAXP2101 pmu;
static bool pmu_ok = false;

void power_init() {
    pmu_ok = pmu.begin(Wire, ADDR_AXP2101, I2C_SDA, I2C_SCL);
    if (!pmu_ok) {
        Serial.println("AXP2101 init failed");
        return;
    }

    // Explicitly enable BLDO1 at 3.3V — this powers the AMOLED display
    // Must be done before display init, pmu.begin() may reset this rail
    pmu.setBLDO1Voltage(3300);
    pmu.enableBLDO1();

    // Disable unused peripherals for power saving
    pmu.disableIRQ(XPOWERS_AXP2101_ALL_IRQ);
    pmu.enableIRQ(XPOWERS_AXP2101_BAT_INSERT_IRQ |
                  XPOWERS_AXP2101_BAT_REMOVE_IRQ |
                  XPOWERS_AXP2101_VBUS_INSERT_IRQ |
                  XPOWERS_AXP2101_VBUS_REMOVE_IRQ |
                  XPOWERS_AXP2101_PKEY_SHORT_IRQ |
                  XPOWERS_AXP2101_PKEY_LONG_IRQ);

    pmu.clearIrqStatus();

    // Set charge target to 4.2V, current to 300mA (safe default)
    pmu.setChargeTargetVoltage(XPOWERS_AXP2101_CHG_VOL_4V2);
    pmu.setChargerConstantCurr(XPOWERS_AXP2101_CHG_CUR_300MA);
    pmu.enableBattDetection();
    pmu.enableVbusVoltageMeasure();
    pmu.enableBattVoltageMeasure();

    Serial.printf("Battery: %dmV, %d%%\n",
                  pmu.getBattVoltage(), pmu.getBatteryPercent());
}

uint8_t power_get_battery_percent() {
    if (!pmu_ok) return 0;
    int pct = pmu.getBatteryPercent();
    if (pct < 0 || pct > 100) return 0;  // -1 or 255 = no valid reading yet
    return (uint8_t)pct;
}

uint16_t power_get_battery_mv() {
    if (!pmu_ok) return 0;
    return pmu.getBattVoltage();
}

bool power_is_charging() {
    if (!pmu_ok) return false;
    return pmu.isCharging();
}

bool power_is_vbus_in() {
    if (!pmu_ok) return false;
    return pmu.isVbusIn();
}

void power_disable_display_rail() {
    if (!pmu_ok) return;
    pmu.disableBLDO1();
}

void power_enable_display_rail() {
    if (!pmu_ok) return;
    pmu.enableBLDO1();
}

void power_enter_deep_sleep() {
    if (!pmu_ok) return;

    // Stay awake when powered via USB — supports development and prevents sleeping
    // while charging. Deep sleep only engages on battery power.
    if (pmu.isVbusIn()) {
        Serial.println("USB power detected — skipping deep sleep");
        return;
    }

    // Disable display and audio rails
    pmu.disableBLDO1();
    pmu.disableBLDO2();
    pmu.disableALDO1();
    pmu.disableALDO2();
    pmu.disableALDO3();
    pmu.disableALDO4();

    // ESP32-C6: deep-sleep GPIO wakeup requires LP GPIOs (0-7 only).
    // GPIO 9 (BTN_BOOT) and GPIO 15 (TOUCH_INT) are HP GPIOs — they cannot
    // trigger wakeup via ext0/ext1/esp_deep_sleep_enable_gpio_wakeup.
    // All LP GPIOs are consumed by the QSPI display bus (0-5) and I2C (7-8).
    //
    // Strategy: periodic timer wake. The device wakes every N minutes, shows the
    // "Waiting to Connect" screen, advertises BLE for 30s, then sleeps again.
    // Press the hardware RESET (EN) button for an immediate wake at any time.
    //
    // Wake every 2 minutes to advertise and check for a BLE connection
    esp_sleep_enable_timer_wakeup(2UL * 60 * 1000000);

    Serial.println("Entering deep sleep (timer wake in 2 min)");
    Serial.flush();

    esp_deep_sleep_start();
}
