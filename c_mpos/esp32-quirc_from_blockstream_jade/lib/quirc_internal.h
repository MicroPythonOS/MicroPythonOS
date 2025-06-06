/* quirc -- QR-code recognition library
 * Copyright (C) 2010-2012 Daniel Beer <dlbeer@gmail.com>
 *
 * Permission to use, copy, modify, and/or distribute this software for any
 * purpose with or without fee is hereby granted, provided that the above
 * copyright notice and this permission notice appear in all copies.
 *
 * THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
 * WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
 * MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
 * ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
 * WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
 * ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
 * OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
 */

#ifndef QUIRC_INTERNAL_H_
#define QUIRC_INTERNAL_H_

#include "quirc.h"

#include <stdlib.h>

#define QUIRC_PIXEL_WHITE 0
#define QUIRC_PIXEL_BLACK 1
#define QUIRC_PIXEL_REGION 2

#ifndef QUIRC_MAX_REGIONS
#define QUIRC_MAX_REGIONS 254
#endif

#define QUIRC_MAX_CAPSTONES 32
#define QUIRC_MAX_GRIDS 8

#define QUIRC_PERSPECTIVE_PARAMS 8

#if QUIRC_MAX_REGIONS < UINT8_MAX
typedef uint8_t quirc_pixel_t;
#elif QUIRC_MAX_REGIONS < UINT16_MAX
typedef uint16_t quirc_pixel_t;
#else
#error "QUIRC_MAX_REGIONS > 65534 is not supported"
#endif

//#include <esp_heap_caps.h>
static inline void* ps_malloc(const size_t size)
{
  //return heap_caps_malloc_prefer(size, MALLOC_CAP_DEFAULT | MALLOC_CAP_SPIRAM, MALLOC_CAP_DEFAULT);
  return malloc(size);
}
static inline void* d_malloc(const size_t size)
{
  //return heap_caps_malloc(size, MALLOC_CAP_DEFAULT | MALLOC_CAP_INTERNAL);
  return malloc(size);
}

struct quirc_region
{
  struct quirc_point seed;
  int count;
  int capstone;
} __attribute__((aligned(8)));

struct quirc_capstone
{
  int ring;
  int stone;

  struct quirc_point corners[4];
  struct quirc_point center;
  float c[QUIRC_PERSPECTIVE_PARAMS];

  int qr_grid;
} __attribute__((aligned(8)));

struct quirc_grid
{
  /* Capstone indices */
  int caps[3];

  /* Alignment pattern region and corner */
  int align_region;
  struct quirc_point align;

  /* Timing pattern endpoints */
  struct quirc_point tpep[3];
  int hscan;
  int vscan;

  /* Grid size and perspective transform */
  int grid_size;
  float c[QUIRC_PERSPECTIVE_PARAMS];
} __attribute__((aligned(8)));

struct quirc
{
  uint8_t *image;
  quirc_pixel_t *pixels;
  int w;
  int h;

  int num_regions;
  struct quirc_region regions[QUIRC_MAX_REGIONS];

  int num_capstones;
  struct quirc_capstone capstones[QUIRC_MAX_CAPSTONES];

  int num_grids;
  struct quirc_grid grids[QUIRC_MAX_GRIDS];
} __attribute__((aligned(8)));

/************************************************************************
 * QR-code version information database
 */

#define QUIRC_MAX_VERSION 40
#define QUIRC_MAX_ALIGNMENT 7

struct quirc_rs_params
{
  uint8_t bs; /* Small block size */
  uint8_t dw; /* Small data words */
  uint8_t ns; /* Number of small blocks */
} __attribute__((aligned(8)));

struct quirc_version_info
{
  uint16_t data_bytes;
  uint8_t apat[QUIRC_MAX_ALIGNMENT];
  struct quirc_rs_params ecc[4];
} __attribute__((aligned(8)));

extern const struct quirc_version_info quirc_version_db[QUIRC_MAX_VERSION + 1];

#endif
