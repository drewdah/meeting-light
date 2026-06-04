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

    // Disable display and audio rails
    pmu.disableBLDO1();
    pmu.disableBLDO2();
    pmu.disableALDO1();
    pmu.disableALDO2();
    pmu.disableALDO3();
    pmu.disableALDO4();

    // Configure BOOT button (GPIO 9) as wakeup source
    esp_sleep_enable_ext1_wakeup(1ULL << BTN_BOOT, ESP_EXT1_WAKEUP_ANY_LOW);

    // Safety timer: wake after 8 hours regardless
    esp_sleep_enable_timer_wakeup(8ULL * 3600 * 1000000);

    Serial.println("Entering deep sleep");
    Serial.flush();

    esp_deep_sleep_start();
}
