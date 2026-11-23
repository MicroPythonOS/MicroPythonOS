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
//	A WAD that lives in memory. A host that keeps the game data in RAM
//	(MicroPythonOS inflates the bundled WAD at launch instead of writing it
//	to storage) hands the bytes over with W_SetMemoryFile() and then names
//	that file on the command line. No stdio is involved for the WAD.
//

#include <string.h>

#include "doomtype.h"
#include "w_file.h"
#include "z_zone.h"

extern wad_file_class_t memory_wad_file;

static const byte *memory_data;
static size_t memory_length;
static int memory_ready;

void W_SetMemoryFile(const void *data, size_t length)
{
    memory_data = (const byte *) data;
    memory_length = length;
    memory_ready = (data != NULL && length > 0);
}

void W_ClearMemoryFile(void)
{
    memory_data = NULL;
    memory_length = 0;
    memory_ready = 0;
}

int W_HasMemoryFile(const char *path)
{
    return memory_ready && strcmp(path, W_MEMORY_WAD_NAME) == 0;
}

static wad_file_t *W_Memory_OpenFile(char *path)
{
    wad_file_t *result;

    if (!W_HasMemoryFile(path))
    {
        return NULL;
    }

    result = Z_Malloc(sizeof(wad_file_t), PU_STATIC, 0);
    result->file_class = &memory_wad_file;
    // Setting mapped lets W_CacheLumpNum hand out the bytes directly.
    result->mapped = (byte *) memory_data;
    result->length = memory_length;

    return result;
}

static void W_Memory_CloseFile(wad_file_t *wad)
{
    // The bytes belong to the host; only the handle is ours.
    Z_Free(wad);
}

static size_t W_Memory_Read(wad_file_t *wad, unsigned int offset,
                            void *buffer, size_t buffer_len)
{
    if ((size_t) offset >= wad->length)
    {
        return 0;
    }

    if (offset + buffer_len > wad->length)
    {
        buffer_len = wad->length - offset;
    }

    memcpy(buffer, wad->mapped + offset, buffer_len);

    return buffer_len;
}

wad_file_class_t memory_wad_file =
{
    W_Memory_OpenFile,
    W_Memory_CloseFile,
    W_Memory_Read,
};
