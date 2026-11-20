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
// DESCRIPTION:
//	Put all global tate variables here.
//

#include <stdio.h>

#include "doomstat.h"


// Game Mode - identify IWAD as shareware, retail etc.
static GameMode_t const gamemode_init = indetermined;
GameMode_t gamemode;
static GameMission_t const gamemission_init = doom;
GameMission_t gamemission;
static GameVersion_t const gameversion_init = exe_final2;
GameVersion_t gameversion;
char *gamedescription;

// Set if homebrew PWAD stuff has been added.
boolean	modifiedgame;





/* dataless.py: initialised data copied into BSS at module load */
#include <string.h>
void doom_init_data_doomstat(void) {
    memcpy(&gamemode, &gamemode_init, sizeof(gamemode));
    memcpy(&gamemission, &gamemission_init, sizeof(gamemission));
    memcpy(&gameversion, &gameversion_init, sizeof(gameversion));
}
