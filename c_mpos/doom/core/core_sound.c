/*
 * Sound effects for a fixed-address core, in chocolate-doom's own terms.
 *
 * The mixer is deliberately plain: a handful of voices, each walking an 8-bit
 * unsigned WAD lump at a fixed-point step, summed into mono signed 16-bit. That
 * is all Doom's sound effects are - the engine's SFX are 8-bit DMX samples with
 * no compression - and it costs a few milliseconds a second of audio.
 *
 * The core does not own a clock or a device. The host pulls mixed samples with
 * entry->audio_mix() whenever its DAC is short of data, so a slow frame delays
 * audio in the host's buffer instead of blocking the engine, and a core built
 * without sound simply leaves the pointer NULL.
 */
#include <stdint.h>
#include <string.h>

#include "doomtype.h"
#include "i_sound.h"
#include "sounds.h"
#include "w_wad.h"
#include "z_zone.h"
#include "deh_str.h"
#include "../../core_abi.h"
#include <stdio.h>

/* The host's output rate. Doom's sound effects are 11025 Hz, so mixing at that
 * rate costs half the samples of 22050 for exactly the same audio. */
#define MPOS_SOUND_RATE 11025
#define MPOS_SOUND_VOICES 8

typedef struct {
    const uint8_t *data;   /* 8-bit unsigned samples, or NULL when idle */
    int length;            /* samples */
    uint32_t pos;          /* 16.16 fixed point */
    uint32_t step;         /* source samples advanced per output sample */
    int gain;              /* 0..256, applied as gain/256 */
} mpos_voice_t;

static mpos_voice_t s_voices[MPOS_SOUND_VOICES];
static int s_volume = 15;  /* s_sfx_volume, 0..15 */
static int s_ready;
static const mpos_core_abi_t *s_abi;
static int s_starts;

void mpos_sound_set_abi(const mpos_core_abi_t *abi) {
    s_abi = abi;
}

int mpos_sound_starts(void) {
    return s_starts;
}

/* One line at start-up: which device the engine chose and whether the module
 * was linked, which is what tells "no sound" apart from "no sound module". */
void mpos_sound_report(void) {
    extern int snd_sfxdevice;
    extern sound_module_t *sound_module__i_sound;
    if (s_abi == NULL) {
        return;
    }
    char line[72];
    snprintf(line, sizeof(line), "sound: %d Hz, device %d, %s",
             MPOS_SOUND_RATE, snd_sfxdevice,
             sound_module__i_sound != NULL ? "active" : "inactive");
    s_abi->log(s_abi->host, line);
}

/* Lump lookup cache: W_CacheLumpNum hands out zone memory, so ask once. */
#define MPOS_SFX_CACHE 96
typedef struct {
    int lump;
    const uint8_t *data;
    int length;
    int rate;
} mpos_sfx_cache_t;

static mpos_sfx_cache_t s_cache[MPOS_SFX_CACHE];
static int s_cache_count;

/* A DMX lump is 8 header bytes and 32 samples of tail padding; both are
 * dropped, as chocolate-doom's SDL module does: the first two bytes are the
 * sample rate (0 = 11025) and the next four the sample count. */
static mpos_sfx_cache_t *cache_lump(int lump) {
    for (int i = 0; i < s_cache_count; i++) {
        if (s_cache[i].lump == lump) {
            return &s_cache[i];
        }
    }
    if (s_cache_count >= MPOS_SFX_CACHE) {
        return NULL;
    }
    const uint8_t *raw = (const uint8_t *)W_CacheLumpNum(lump, PU_STATIC);
    int lumplen = W_LumpLength(lump);
    if (raw == NULL || lumplen < 64) {
        return NULL;
    }
    int rate = raw[2] | (raw[3] << 8);
    if (rate < 4000 || rate > 48000) {
        rate = 11025;
    }
    uint32_t length = (uint32_t)raw[4] | ((uint32_t)raw[5] << 8)
                      | ((uint32_t)raw[6] << 16) | ((uint32_t)raw[7] << 24);
    if (length > (uint32_t)(lumplen - 8)) {
        length = lumplen - 8;
    }
    length -= 32;

    mpos_sfx_cache_t *entry = &s_cache[s_cache_count++];
    entry->lump = lump;
    entry->data = raw + 8;
    entry->length = (int)length;
    entry->rate = rate;
    return entry;
}

/* -- the mixer -------------------------------------------------------------- */

void mpos_sound_mix(int16_t *dst, int frames) {
    memset(dst, 0, (size_t)frames * sizeof(int16_t));
    if (!s_ready) {
        return;
    }

    for (int v = 0; v < MPOS_SOUND_VOICES; v++) {
        mpos_voice_t *voice = &s_voices[v];
        if (voice->data == NULL) {
            continue;
        }
        uint32_t pos = voice->pos;
        const int gain = voice->gain;
        for (int i = 0; i < frames; i++) {
            int index = (int)(pos >> 16);
            if (index >= voice->length) {
                voice->data = NULL;
                break;
            }
            /* 8-bit unsigned -> signed, then scaled: gain is 0..256, so a
             * full-volume sample reaches the full 16-bit range. */
            int sample = ((int)voice->data[index] - 128) * gain;
            dst[i] = (int16_t)(dst[i] + sample);
            pos += voice->step;
        }
        voice->pos = pos;
    }

    for (int i = 0; i < frames; i++) {
        int value = dst[i];
        if (value > 32767) {
            dst[i] = 32767;
        } else if (value < -32768) {
            dst[i] = -32768;
        }
    }
}

/* -- the sound module chocolate-doom expects -------------------------------- */

static const snddevice_t snd_devices[] = {
    SNDDEVICE_SB, SNDDEVICE_PAS, SNDDEVICE_GUS, SNDDEVICE_WAVEBLASTER,
    SNDDEVICE_SOUNDCANVAS, SNDDEVICE_GENMIDI,
};

static boolean snd_init(boolean use_sfx_prefix) {
    (void)use_sfx_prefix;
    memset(s_voices, 0, sizeof(s_voices));
    s_cache_count = 0;
    s_ready = 1;
    return true;
}

static void snd_shutdown(void) {
    memset(s_voices, 0, sizeof(s_voices));
    s_ready = 0;
}

/* Doom stores sound effects under a "ds" prefix on the sfx name ("ds" +
 * "pistol" = "dspistol"); the engine asks for the number before it can play
 * anything, and a -1 here is silence. */
static int snd_lump_num(sfxinfo_t *sfxinfo) {
    char namebuf[9];
    if (sfxinfo->link != NULL) {
        sfxinfo = sfxinfo->link;
    }
    snprintf(namebuf, sizeof(namebuf), "ds%s", DEH_String(sfxinfo->name));
    return W_CheckNumForName(namebuf);
}

/* Doom calls this once per tic; the host pulls the actual samples. */
static void snd_update(void) {
}

static void snd_update_params(int channel, int vol, int sep) {
    (void)sep;
    if (channel < 0 || channel >= MPOS_SOUND_VOICES) {
        return;
    }
    mpos_voice_t *voice = &s_voices[channel];
    if (voice->data != NULL) {
        voice->gain = (vol * s_volume * 256) / (127 * 15);
    }
}

static int snd_start(sfxinfo_t *sfxinfo, int channel, int vol, int sep) {
    (void)sep;
    s_starts++;
    if (!s_ready || channel < 0 || channel >= MPOS_SOUND_VOICES) {
        return -1;
    }
    mpos_sfx_cache_t *sfx = cache_lump(sfxinfo->lumpnum);
    if (sfx == NULL || sfx->length <= 0) {
        return -1;
    }
    mpos_voice_t *voice = &s_voices[channel];
    voice->data = sfx->data;
    voice->length = sfx->length;
    voice->pos = 0;
    voice->step = (uint32_t)(((uint64_t)sfx->rate << 16) / MPOS_SOUND_RATE);
    voice->gain = (vol * s_volume * 256) / (127 * 15);
    return channel;
}

static void snd_stop(int channel) {
    if (channel >= 0 && channel < MPOS_SOUND_VOICES) {
        s_voices[channel].data = NULL;
    }
}

static boolean snd_playing(int channel) {
    if (channel < 0 || channel >= MPOS_SOUND_VOICES) {
        return false;
    }
    return s_voices[channel].data != NULL;
}

static void snd_cache(sfxinfo_t *sounds, int num_sounds) {
    (void)sounds;
    (void)num_sounds;
}

/* Filled at start-up: a writable global with an initialiser would land in
 * .data, and a core's engine tree is built dataless. */
sound_module_t DG_sound_module;

/* Referenced by i_sound.c's config binding; the SDL module normally owns them. */
int use_libsamplerate;
float libsamplerate_scale;

void mpos_sound_module_init(void) {
    DG_sound_module.sound_devices = (snddevice_t *)snd_devices;
    DG_sound_module.num_sound_devices =
        (int)(sizeof(snd_devices) / sizeof(snd_devices[0]));
    DG_sound_module.Init = snd_init;
    DG_sound_module.Shutdown = snd_shutdown;
    DG_sound_module.GetSfxLumpNum = snd_lump_num;
    DG_sound_module.Update = snd_update;
    DG_sound_module.UpdateSoundParams = snd_update_params;
    DG_sound_module.StartSound = snd_start;
    DG_sound_module.StopSound = snd_stop;
    DG_sound_module.SoundIsPlaying = snd_playing;
    DG_sound_module.CacheSounds = snd_cache;
}

/* Doom's music is OPL/MIDI; there is no emulator here, so the module is a set
 * of no-ops. FEATURE_SOUND makes i_sound.c reference it. */
static boolean music_init(void) {
    return false;
}

static boolean music_is_playing(void) {
    return false;
}

static void music_noop_void(void) {
}

static void music_noop_int(int value) {
    (void)value;
}

static void music_noop_handle(void *handle) {
    (void)handle;
}

static void *music_noop_song(void *data, int len) {
    (void)data;
    (void)len;
    return NULL;
}

static void music_play(void *handle, boolean looping) {
    (void)handle;
    (void)looping;
}

music_module_t DG_music_module;

void mpos_music_module_init(void) {
    DG_music_module.sound_devices = (snddevice_t *)snd_devices;
    DG_music_module.num_sound_devices = 1;
    DG_music_module.Init = music_init;
    DG_music_module.Shutdown = music_noop_void;
    DG_music_module.SetMusicVolume = music_noop_int;
    DG_music_module.PauseMusic = music_noop_void;
    DG_music_module.ResumeMusic = music_noop_void;
    DG_music_module.RegisterSong = music_noop_song;
    DG_music_module.UnRegisterSong = music_noop_handle;
    DG_music_module.PlaySong = music_play;
    DG_music_module.StopSong = music_noop_void;
    DG_music_module.MusicIsPlaying = music_is_playing;
    DG_music_module.Poll = music_noop_void;
}
