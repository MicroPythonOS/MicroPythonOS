//
// Copyright(C) 1993-1996 Id Software, Inc.
// Copyright(C) 2005-2014 Simon Howard
//
// This program is free software; you can redistribute it and/or
// modify it under the terms of the GNU General Public License
// as published by the Free Software Foundation; either version 2
// of the License, or (at your option) any later version.
//
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.
//
// DESCRIPTION:  none
//

#include <stdio.h>
#include <stdlib.h>

#if defined(FEATURE_SOUND) && !defined(__DJGPP__)
#include <SDL_mixer.h>
#endif

#include "config.h"
#include "doomfeatures.h"
#include "doomtype.h"

#ifdef ORIGCODE
#include "gusconf.h"
#endif
#include "i_sound.h"
#include "i_video.h"
#include "m_argv.h"
#include "m_config.h"

// Sound sample rate to use for digital output (Hz)

static int const snd_samplerate_init = 44100;
int snd_samplerate;

// Maximum number of bytes to dedicate to allocated sound effects.
// (Default: 64MB)

static int const snd_cachesize_init = 64 * 1024 * 1024;
int snd_cachesize;

// Config variable that controls the sound buffer size.
// We default to 28ms (1000 / 35fps = 1 buffer per tic).

static int const snd_maxslicetime_ms_init = 28;
int snd_maxslicetime_ms;

// External command to invoke to play back music.

static char * const snd_musiccmd_init = "";
char * snd_musiccmd;

// Low-level sound and music modules we are using

static sound_module_t * const sound_module_init = NULL;
sound_module_t * sound_module;
static music_module_t * const music_module_init = NULL;
music_module_t * music_module;

static int const snd_musicdevice_init = SNDDEVICE_SB;
int snd_musicdevice;
static int const snd_sfxdevice_init = SNDDEVICE_SB;
int snd_sfxdevice;

// DOS-specific options: These are unused but should be maintained
// so that the config file can be shared between chocolate
// doom and doom.exe

static int const snd_sbport_init = 0;
int snd_sbport;
static int const snd_sbirq_init = 0;
int snd_sbirq;
static int const snd_sbdma_init = 0;
int snd_sbdma;
static int const snd_mport_init = 0;
int snd_mport;

// Compiled-in sound modules:

static sound_module_t * const sound_modules_init[3] = {
    #ifdef FEATURE_SOUND
    &DG_sound_module,
    #endif
    NULL,
};
sound_module_t * sound_modules[3];

// Check if a sound device is in the given list of devices

static boolean SndDeviceInList(snddevice_t device, snddevice_t *list,
                               int len)
{
    int i;

    for (i=0; i<len; ++i)
    {
        if (device == list[i])
        {
            return true;
        }
    }

    return false;
}

// Find and initialize a sound_module_t appropriate for the setting
// in snd_sfxdevice.

static void InitSfxModule(boolean use_sfx_prefix)
{
    int i;

    sound_module = NULL;

    for (i=0; sound_modules[i] != NULL; ++i)
    {
        // Is the sfx device in the list of devices supported by
        // this module?

        if (SndDeviceInList(snd_sfxdevice, 
                            sound_modules[i]->sound_devices,
                            sound_modules[i]->num_sound_devices))
        {
            // Initialize the module

            if (sound_modules[i]->Init(use_sfx_prefix))
            {
                sound_module = sound_modules[i];
                return;
            }
        }
    }
}

// Initialize music according to snd_musicdevice.

static void InitMusicModule(void)
{
#ifdef FEATURE_SOUND
    music_module = &DG_music_module;
#endif /* FEATURE_SOUND */
}

//
// Initializes sound stuff, including volume
// Sets channels, SFX and music volume,
//  allocates channel buffer, sets S_sfx lookup.
//

void I_InitSound(boolean use_sfx_prefix)
{  
    boolean nosound, nosfx, nomusic;

    //!
    // @vanilla
    //
    // Disable all sound output.
    //

    nosound = M_CheckParm("-nosound") > 0;

    //!
    // @vanilla
    //
    // Disable sound effects. 
    //

    nosfx = M_CheckParm("-nosfx") > 0;

    //!
    // @vanilla
    //
    // Disable music.
    //

    nomusic = M_CheckParm("-nomusic") > 0;

    // Initialize the sound and music subsystems.

    if (!nosound && !screensaver_mode)
    {
        // This is kind of a hack. If native MIDI is enabled, set up
        // the TIMIDITY_CFG environment variable here before SDL_mixer
        // is opened.

        if (!nomusic
         && (snd_musicdevice == SNDDEVICE_GENMIDI
          || snd_musicdevice == SNDDEVICE_GUS))
        {
            //I_InitTimidityConfig();
        }

        if (!nosfx)
        {
            InitSfxModule(use_sfx_prefix);
        }

        if (!nomusic)
        {
            InitMusicModule();
        }
    }

}

void I_ShutdownSound(void)
{
    if (sound_module != NULL)
    {
        sound_module->Shutdown();
    }

    if (music_module != NULL)
    {
        music_module->Shutdown();
    }
}

int I_GetSfxLumpNum(sfxinfo_t *sfxinfo)
{
    if (sound_module != NULL) 
    {
        return sound_module->GetSfxLumpNum(sfxinfo);
    }
    else
    {
        return 0;
    }
}

void I_UpdateSound(void)
{
    if (sound_module != NULL)
    {
        sound_module->Update();
    }

    if (music_module != NULL && music_module->Poll != NULL)
    {
        music_module->Poll();
    }
}

static void CheckVolumeSeparation(int *vol, int *sep)
{
    if (*sep < 0)
    {
        *sep = 0;
    }
    else if (*sep > 254)
    {
        *sep = 254;
    }

    if (*vol < 0)
    {
        *vol = 0;
    }
    else if (*vol > 127)
    {
        *vol = 127;
    }
}

void I_UpdateSoundParams(int channel, int vol, int sep)
{
    if (sound_module != NULL)
    {
        CheckVolumeSeparation(&vol, &sep);
        sound_module->UpdateSoundParams(channel, vol, sep);
    }
}

int I_StartSound(sfxinfo_t *sfxinfo, int channel, int vol, int sep)
{
    if (sound_module != NULL)
    {
        CheckVolumeSeparation(&vol, &sep);
        return sound_module->StartSound(sfxinfo, channel, vol, sep);
    }
    else
    {
        return 0;
    }
}

void I_StopSound(int channel)
{
    if (sound_module != NULL)
    {
        sound_module->StopSound(channel);
    }
}

boolean I_SoundIsPlaying(int channel)
{
    if (sound_module != NULL)
    {
        return sound_module->SoundIsPlaying(channel);
    }
    else
    {
        return false;
    }
}

void I_PrecacheSounds(sfxinfo_t *sounds, int num_sounds)
{
    if (sound_module != NULL && sound_module->CacheSounds != NULL)
    {
	sound_module->CacheSounds(sounds, num_sounds);
    }
}

void I_InitMusic(void)
{
    if(music_module != NULL)
    {
        music_module->Init();
    }
}

void I_ShutdownMusic(void)
{

}

void I_SetMusicVolume(int volume)
{
    if (music_module != NULL)
    {
        music_module->SetMusicVolume(volume);
    }
}

void I_PauseSong(void)
{
    if (music_module != NULL)
    {
        music_module->PauseMusic();
    }
}

void I_ResumeSong(void)
{
    if (music_module != NULL)
    {
        music_module->ResumeMusic();
    }
}

void *I_RegisterSong(void *data, int len)
{
    if (music_module != NULL)
    {
        return music_module->RegisterSong(data, len);
    }
    else
    {
        return NULL;
    }
}

void I_UnRegisterSong(void *handle)
{
    if (music_module != NULL)
    {
        music_module->UnRegisterSong(handle);
    }
}

void I_PlaySong(void *handle, boolean looping)
{
    if (music_module != NULL)
    {
        music_module->PlaySong(handle, looping);
    }
}

void I_StopSong(void)
{
    if (music_module != NULL)
    {
        music_module->StopSong();
    }
}

boolean I_MusicIsPlaying(void)
{
    if (music_module != NULL)
    {
        return music_module->MusicIsPlaying();
    }
    else
    {
        return false;
    }
    
}

void I_BindSoundVariables(void)
{
    extern int use_libsamplerate;
    extern float libsamplerate_scale;

    M_BindVariable("snd_musicdevice",   &snd_musicdevice);
    M_BindVariable("snd_sfxdevice",     &snd_sfxdevice);
    M_BindVariable("snd_sbport",        &snd_sbport);
    M_BindVariable("snd_sbirq",         &snd_sbirq);
    M_BindVariable("snd_sbdma",         &snd_sbdma);
    M_BindVariable("snd_mport",         &snd_mport);
    M_BindVariable("snd_maxslicetime_ms", &snd_maxslicetime_ms);
    M_BindVariable("snd_musiccmd",      &snd_musiccmd);
    M_BindVariable("snd_samplerate",    &snd_samplerate);
    M_BindVariable("snd_cachesize",     &snd_cachesize);

#ifdef FEATURE_SOUND
    M_BindVariable("use_libsamplerate",   &use_libsamplerate);
    M_BindVariable("libsamplerate_scale", &libsamplerate_scale);
#endif

    // Before SDL_mixer version 1.2.11, MIDI music caused the game
    // to crash when it looped.  If this is an old SDL_mixer version,
    // disable MIDI.
}


/* dataless.py: initialised data copied into BSS at module load */
#include <string.h>
void doom_init_data_i_sound(void) {
    memcpy(&snd_samplerate, &snd_samplerate_init, sizeof(snd_samplerate));
    memcpy(&snd_cachesize, &snd_cachesize_init, sizeof(snd_cachesize));
    memcpy(&snd_maxslicetime_ms, &snd_maxslicetime_ms_init, sizeof(snd_maxslicetime_ms));
    memcpy(&snd_musiccmd, &snd_musiccmd_init, sizeof(snd_musiccmd));
    memcpy(&sound_module, &sound_module_init, sizeof(sound_module));
    memcpy(&music_module, &music_module_init, sizeof(music_module));
    memcpy(&snd_musicdevice, &snd_musicdevice_init, sizeof(snd_musicdevice));
    memcpy(&snd_sfxdevice, &snd_sfxdevice_init, sizeof(snd_sfxdevice));
    memcpy(&snd_sbport, &snd_sbport_init, sizeof(snd_sbport));
    memcpy(&snd_sbirq, &snd_sbirq_init, sizeof(snd_sbirq));
    memcpy(&snd_sbdma, &snd_sbdma_init, sizeof(snd_sbdma));
    memcpy(&snd_mport, &snd_mport_init, sizeof(snd_mport));
    memcpy(&sound_modules, &sound_modules_init, sizeof(sound_modules));
}
