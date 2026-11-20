#include <stdio.h>

#include "m_argv.h"

#include "doomgeneric.h"

static pixel_t * const DG_ScreenBuffer_init = NULL;
pixel_t * DG_ScreenBuffer;

void M_FindResponseFile(void);
void D_DoomMain (void);


void doomgeneric_Create(int argc, char **argv)
{
	// save arguments
    myargc = argc;
    myargv = argv;

	M_FindResponseFile();

	DG_ScreenBuffer = malloc(DOOMGENERIC_RESX * DOOMGENERIC_RESY * 4);

	DG_Init();

	D_DoomMain ();
}


/* dataless.py: initialised data copied into BSS at module load */
#include <string.h>
void doom_init_data_doomgeneric(void) {
    memcpy(&DG_ScreenBuffer, &DG_ScreenBuffer_init, sizeof(DG_ScreenBuffer));
}
