// Link-time audio for a badge with no sound.
//
// Duke's sound engine (audiolib) is a 33k-line DOS library with its own mixer,
// DMA and OPL synth; none of it applies here, and the panels this runs on (the
// MaTouch, the Waveshares) have no audio output. The engine still references
// every FX_/MUSIC_ symbol from sounds.c and its menus, so they exist and do
// nothing: FXDevice is NumSoundCards (see CONFIG_SetDefaults), which makes the
// engine skip loading samples entirely.
//
// A board with an I2S codec can grow a real mixer later: the core ABI already
// has audio_mix(), and the engine's samples are 8-bit WAV/VOC in the GRP.

#include <stdint.h>

#include "fx_man.h"
#include "music.h"
#include "SDL_audio.h"

char *FX_ErrorString(int ErrorNumber) {
    (void)ErrorNumber;
    return (char *)"no audio output";
}

int FX_SetupCard(int SoundCard, fx_device *device) {
    (void)SoundCard;
    (void)device;
    return FX_Error;
}

int FX_GetBlasterSettings(fx_blaster_config *blaster) {
    (void)blaster;
    return FX_Error;
}

int FX_SetupSoundBlaster(fx_blaster_config blaster, int *MaxVoices,
                         int *MaxSampleBits, int *MaxChannels) {
    (void)blaster; (void)MaxVoices; (void)MaxSampleBits; (void)MaxChannels;
    return FX_Error;
}

int FX_Init(int SoundCard, int numvoices, int numchannels, int samplebits,
            unsigned mixrate) {
    (void)SoundCard; (void)numvoices; (void)numchannels; (void)samplebits;
    (void)mixrate;
    return FX_Ok;
}

int FX_Shutdown(void) { return FX_Ok; }
int FX_SetCallBack(void (*function)(int32_t)) { (void)function; return FX_Ok; }
void FX_SetVolume(int volume) { (void)volume; }
int FX_GetVolume(void) { return 0; }
void FX_SetReverseStereo(int setting) { (void)setting; }
int FX_GetReverseStereo(void) { return 0; }
void FX_SetReverb(int reverb) { (void)reverb; }
void FX_SetFastReverb(int reverb) { (void)reverb; }
int FX_GetMaxReverbDelay(void) { return 0; }
int FX_GetReverbDelay(void) { return 0; }
void FX_SetReverbDelay(int delay) { (void)delay; }

int FX_VoiceAvailable(int priority) { (void)priority; return 0; }
int FX_EndLooping(int handle) { (void)handle; return FX_Ok; }
int FX_SetPan(int handle, int vol, int left, int right) {
    (void)handle; (void)vol; (void)left; (void)right; return FX_Ok;
}
int FX_SetPitch(int handle, int pitchoffset) {
    (void)handle; (void)pitchoffset; return FX_Ok;
}
int FX_SetFrequency(int handle, int frequency) {
    (void)handle; (void)frequency; return FX_Ok;
}

int FX_PlayVOC(uint8_t *ptr, int pitchoffset, int vol, int left, int right,
               int priority, uint32_t callbackval) {
    (void)ptr; (void)pitchoffset; (void)vol; (void)left; (void)right;
    (void)priority; (void)callbackval;
    return FX_Warning;
}

int FX_PlayLoopedVOC(uint8_t *ptr, int loopstart, int loopend,
                     int pitchoffset, int vol, int left, int right,
                     int priority, uint32_t callbackval) {
    (void)ptr; (void)loopstart; (void)loopend; (void)pitchoffset; (void)vol;
    (void)left; (void)right; (void)priority; (void)callbackval;
    return FX_Warning;
}

int FX_PlayWAV(uint8_t *ptr, int pitchoffset, int vol, int left, int right,
               int priority, uint32_t callbackval) {
    (void)ptr; (void)pitchoffset; (void)vol; (void)left; (void)right;
    (void)priority; (void)callbackval;
    return FX_Warning;
}

int FX_PlayLoopedWAV(uint8_t *ptr, int loopstart, int loopend,
                     int pitchoffset, int vol, int left, int right,
                     int priority, uint32_t callbackval) {
    (void)ptr; (void)loopstart; (void)loopend; (void)pitchoffset; (void)vol;
    (void)left; (void)right; (void)priority; (void)callbackval;
    return FX_Warning;
}

int FX_PlayVOC3D(uint8_t *ptr, int pitchoffset, int angle, int distance,
                 int priority, uint32_t callbackval) {
    (void)ptr; (void)pitchoffset; (void)angle; (void)distance; (void)priority;
    (void)callbackval;
    return FX_Warning;
}

int FX_PlayWAV3D(uint8_t *ptr, int pitchoffset, int angle, int distance,
                 int priority, uint32_t callbackval) {
    (void)ptr; (void)pitchoffset; (void)angle; (void)distance; (void)priority;
    (void)callbackval;
    return FX_Warning;
}

int FX_PlayRaw(uint8_t *ptr, uint32_t length, uint32_t rate, int pitchoffset,
               int vol, int left, int right, int priority,
               uint32_t callbackval) {
    (void)ptr; (void)length; (void)rate; (void)pitchoffset; (void)vol;
    (void)left; (void)right; (void)priority; (void)callbackval;
    return FX_Warning;
}

int FX_PlayLoopedRaw(uint8_t *ptr, uint32_t length, char *loopstart,
                     char *loopend, uint32_t rate, int pitchoffset, int vol,
                     int left, int right, int priority, uint32_t callbackval) {
    (void)ptr; (void)length; (void)loopstart; (void)loopend; (void)rate;
    (void)pitchoffset; (void)vol; (void)left; (void)right; (void)priority;
    (void)callbackval;
    return FX_Warning;
}

int FX_Pan3D(int handle, int angle, int distance) {
    (void)handle; (void)angle; (void)distance; return FX_Ok;
}
int FX_SoundActive(int handle) { (void)handle; return 0; }
int FX_SoundsPlaying(void) { return 0; }
int FX_StopSound(int handle) { (void)handle; return FX_Ok; }
int FX_StopAllSounds(void) { return FX_Ok; }

int FX_StartDemandFeedPlayback(void (*function)(char **ptr, uint32_t *length),
                               int rate, int pitchoffset, int vol, int left,
                               int right, int priority, uint32_t callbackval) {
    (void)function; (void)rate; (void)pitchoffset; (void)vol; (void)left;
    (void)right; (void)priority; (void)callbackval;
    return FX_Warning;
}

int FX_StartRecording(int MixRate, void (*function)(char *ptr, int length)) {
    (void)MixRate; (void)function;
    return FX_Error;
}
void FX_StopRecord(void) {}

char *MUSIC_ErrorString(int ErrorNumber) {
    (void)ErrorNumber;
    return (char *)"no music device";
}
int MUSIC_Init(int SoundCard, int Address) {
    (void)SoundCard; (void)Address;
    return MUSIC_Ok;
}
int MUSIC_Shutdown(void) { return MUSIC_Ok; }
void MUSIC_SetMaxFMMidiChannel(int channel) { (void)channel; }
void MUSIC_SetVolume(int volume) { (void)volume; }
void MUSIC_SetMidiChannelVolume(int channel, int volume) {
    (void)channel; (void)volume;
}
void MUSIC_ResetMidiChannelVolumes(void) {}
int MUSIC_GetVolume(void) { return 0; }
void MUSIC_SetLoopFlag(int loopflag) { (void)loopflag; }
int MUSIC_SongPlaying(void) { return 0; }
void MUSIC_Continue(void) {}
void MUSIC_Pause(void) {}
int MUSIC_StopSong(void) { return MUSIC_Ok; }
int MUSIC_PlaySong(char *songData, int loopflag) {
    (void)songData; (void)loopflag;
    return MUSIC_Ok;
}
void MUSIC_SetContext(int context) { (void)context; }
int MUSIC_GetContext(void) { return 0; }
void MUSIC_SetSongTick(uint32_t PositionInTicks) { (void)PositionInTicks; }
void MUSIC_SetSongTime(uint32_t milliseconds) { (void)milliseconds; }
void MUSIC_SetSongPosition(int measure, int beat, int tick) {
    (void)measure; (void)beat; (void)tick;
}
void MUSIC_GetSongPosition(songposition *pos) { (void)pos; }
void MUSIC_GetSongLength(songposition *pos) { (void)pos; }
int MUSIC_FadeVolume(int tovolume, int milliseconds) {
    (void)tovolume; (void)milliseconds; return MUSIC_Ok;
}
int MUSIC_FadeActive(void) { return 0; }
void MUSIC_StopFade(void) {}
void MUSIC_RerouteMidiChannel(int channel,
                              int (*function)(int event, int c1, int c2)) {
    (void)channel; (void)function;
}
void MUSIC_RegisterTimbreBank(unsigned char *timbres) { (void)timbres; }
void PlayMusic(char *filename) { (void)filename; }

// The SDL shims the engine references (SDL_audio.h). They keep the old
// interface so sounds.c compiles; nothing is mixed.
int SDL_OpenAudio(SDL_AudioSpec *desired, SDL_AudioSpec *obtained) {
    (void)desired; (void)obtained;
    return -1;
}
void SDL_PauseAudio(int pause_on) { (void)pause_on; }
void SDL_CloseAudio(void) {}
void set_overclock_safe(int level) { (void)level; }
