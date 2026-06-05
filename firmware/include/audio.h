#pragma once

void audio_init();
void audio_play_boot_chime();
void audio_play_state_chime();
bool audio_is_ok();
void audio_set_mute(bool mute);
bool audio_is_muted();
