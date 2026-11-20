#ifndef MPOS_ENGINE_H
#define MPOS_ENGINE_H

/* Set by I_Quit() when the player picks "quit" in Doom's menu. The engine does
   not end the process or tear itself down: there is no process, and the app
   owns the panel and the audio device. The host closes the activity (native
   module) or the engine returns to its title screen (core, until the ABI can
   ask the host), and clears the flag. */
extern int mpos_quit_requested;

#endif  /* MPOS_ENGINE_H */
