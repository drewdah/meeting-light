/*
 * audio.cpp — ES8311 codec + I2S tone playback
 *
 * Pre-generates complete waveforms and writes them in a single i2s.write()
 * call to avoid DMA buffer underruns that cause crackling. Matches the
 * Waveshare 15_ES8311.ino pattern of one bulk write per sound.
 */

#include <Arduino.h>
#include <Wire.h>
#include <math.h>
#include <ESP_I2S.h>
#include "audio.h"
#include "config.h"
#include "display.h"
#include "es8311.h"
#include "chime_pcm.h"
#include "alert_pcm.h"

#define SAMPLE_RATE      16000
#define MCLK_FREQ        (SAMPLE_RATE * 256)
#define VOICE_VOLUME     85
#define VOLUME           0.25f

static I2SClass i2s;
static es8311_handle_t es_handle = nullptr;
static bool audio_ok = false;
static bool audio_muted = false;

bool audio_is_ok() { return audio_ok; }
bool audio_is_muted() { return audio_muted; }
void audio_set_mute(bool mute) { audio_muted = mute; }

static bool codec_setup() {
    es_handle = es8311_create(0, ES8311_ADDRRES_0);
    if (!es_handle) {
        Serial.println("Audio: es8311_create failed");
        return false;
    }

    const es8311_clock_config_t es_clk = {
        .mclk_inverted      = false,
        .sclk_inverted      = false,
        .mclk_from_mclk_pin = true,
        .mclk_frequency     = MCLK_FREQ,
        .sample_frequency   = SAMPLE_RATE,
    };

    if (es8311_init(es_handle, &es_clk, ES8311_RESOLUTION_16, ES8311_RESOLUTION_16) != ESP_OK) {
        Serial.println("Audio: es8311_init failed");
        return false;
    }
    if (es8311_sample_frequency_config(es_handle, MCLK_FREQ, SAMPLE_RATE) != ESP_OK) {
        Serial.println("Audio: es8311_sample_frequency_config failed");
        return false;
    }
    if (es8311_microphone_config(es_handle, false) != ESP_OK) {
        Serial.println("Audio: es8311_microphone_config failed");
        return false;
    }
    if (es8311_voice_volume_set(es_handle, VOICE_VOLUME, nullptr) != ESP_OK) {
        Serial.println("Audio: es8311_voice_volume_set failed");
        return false;
    }
    if (es8311_microphone_gain_set(es_handle, ES8311_MIC_GAIN_6DB) != ESP_OK) {
        Serial.println("Audio: es8311_microphone_gain_set failed");
        return false;
    }
    return true;
}

// Generate a tone segment into a pre-allocated buffer, returns number of stereo frames written
static uint32_t generate_tone(int16_t *buf, uint32_t freq_hz, uint32_t duration_ms,
                               float amplitude, uint32_t max_frames) {
    uint32_t total = (uint32_t)((uint64_t)SAMPLE_RATE * duration_ms / 1000);
    if (total > max_frames) total = max_frames;

    uint32_t attack = SAMPLE_RATE / 100;  // 10 ms
    uint32_t rel    = SAMPLE_RATE / 50;   // 20 ms

    for (uint32_t i = 0; i < total; i++) {
        float env = 1.0f;
        if (i < attack)           env = (float)i / (float)attack;
        else if (i > total - rel) env = (float)(total - i) / (float)rel;

        float t = (float)i / (float)SAMPLE_RATE;
        int16_t s = (int16_t)(32767.0f * amplitude * env
                              * sinf(2.0f * (float)M_PI * (float)freq_hz * t));
        buf[i * 2]     = s;  // L
        buf[i * 2 + 1] = s;  // R
    }
    return total;
}

// Generate silence into buffer, returns number of stereo frames written
static uint32_t generate_silence(int16_t *buf, uint32_t duration_ms, uint32_t max_frames) {
    uint32_t total = (uint32_t)((uint64_t)SAMPLE_RATE * duration_ms / 1000);
    if (total > max_frames) total = max_frames;
    memset(buf, 0, total * 4);
    return total;
}

// Write a pre-built PCM buffer to I2S in one call
static void play_buffer(int16_t *buf, uint32_t frames) {
    if (!audio_ok || frames == 0) return;
    i2s.write((uint8_t *)buf, (size_t)frames * 4);
}

void audio_init() {
    // I2S setup first — matches Waveshare example order
    i2s.setPins(I2S_BCLK, I2S_WS, I2S_DOUT, I2S_DIN, I2S_MCLK);
    if (!i2s.begin(I2S_MODE_STD, SAMPLE_RATE, I2S_DATA_BIT_WIDTH_16BIT,
                   I2S_SLOT_MODE_STEREO, I2S_STD_SLOT_BOTH)) {
        Serial.println("Audio: I2S begin failed");
        return;
    }

    if (!codec_setup()) {
        i2s.end();
        return;
    }

    // Enable PA after I2S + codec are ready to avoid amplifying init noise
    display_pa_enable(true);
    delay(50);

    audio_ok = true;
    Serial.println("Audio: ready");
}

// Flush DMA with silence to prevent click when audio stops
static void flush_silence(uint32_t duration_ms) {
    const uint32_t frames = (uint32_t)((uint64_t)SAMPLE_RATE * duration_ms / 1000);
    const size_t bytes = frames * 4;
    uint8_t *silence = (uint8_t *)calloc(1, bytes);
    if (!silence) return;
    i2s.write(silence, bytes);
    free(silence);
}

void audio_play_boot_chime() {
    if (!audio_ok || audio_muted) return;
    i2s.write((uint8_t *)chime_pcm, CHIME_PCM_LEN);
    flush_silence(50);
}

void audio_play_state_chime() {
    if (!audio_ok || audio_muted) return;
    i2s.write((uint8_t *)alert_pcm, ALERT_PCM_LEN);
    flush_silence(50);
}
