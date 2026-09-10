//
// ######################################################################
//
//    usb_disp_prot_t6_jpeg - T6 プロトコル用ソフトウェアJPEGエンコーダ
//
//    Copyright (C) 2026
//      Hideto Kikuchi / PJラボ (@pcjpnet) - https://pc-jp.net/
//
// ######################################################################
//
#ifndef USB_DISP_PROT_T6_JPEG_H_
#define USB_DISP_PROT_T6_JPEG_H_

#include <stdint.h>
#include <string.h>
#include <math.h>

enum { USB_DISP_PROT_T6_JPEG_444 = 0, USB_DISP_PROT_T6_JPEG_420 = 1 };

// ---- 標準テーブル (ITU-T T.81 Annex K) ----
static const uint8_t jz_zigzag[64] = {
    0,  1,  8,  16, 9,  2,  3,  10, 17, 24, 32, 25, 18, 11, 4,  5,
    12, 19, 26, 33, 40, 48, 41, 34, 27, 20, 13, 6,  7,  14, 21, 28,
    35, 42, 49, 56, 57, 50, 43, 36, 29, 22, 15, 23, 30, 37, 44, 51,
    58, 59, 52, 45, 38, 31, 39, 46, 53, 60, 61, 54, 47, 55, 62, 63};

static const uint8_t jz_qlum[64] = {
    16, 11, 10, 16, 24,  40,  51,  61,  12, 12, 14, 19, 26,  58,  60,  55,
    14, 13, 16, 24, 40,  57,  69,  56,  14, 17, 22, 29, 51,  87,  80,  62,
    18, 22, 37, 56, 68,  109, 103, 77,  24, 35, 55, 64, 81,  104, 113, 92,
    49, 64, 78, 87, 103, 121, 120, 101, 72, 92, 95, 98, 112, 100, 103, 99};
static const uint8_t jz_qchr[64] = {
    17, 18, 24, 47, 99, 99, 99, 99, 18, 21, 26, 66, 99, 99, 99, 99,
    24, 26, 56, 99, 99, 99, 99, 99, 47, 66, 99, 99, 99, 99, 99, 99,
    99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99,
    99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99};

static const uint8_t jz_dc_lum_bits[17] = {0, 0, 1, 5, 1, 1, 1, 1, 1,
                                           1, 0, 0, 0, 0, 0, 0, 0};
static const uint8_t jz_dc_lum_vals[12] = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11};
static const uint8_t jz_dc_chr_bits[17] = {0, 0, 3, 1, 1, 1, 1, 1, 1,
                                           1, 1, 1, 0, 0, 0, 0, 0};
static const uint8_t jz_dc_chr_vals[12] = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11};

static const uint8_t jz_ac_lum_bits[17] = {0, 0, 2, 1, 3, 3, 2, 4, 3,
                                           5, 5, 4, 4, 0, 0, 1, 0x7d};
static const uint8_t jz_ac_lum_vals[162] = {
    0x01, 0x02, 0x03, 0x00, 0x04, 0x11, 0x05, 0x12, 0x21, 0x31, 0x41, 0x06,
    0x13, 0x51, 0x61, 0x07, 0x22, 0x71, 0x14, 0x32, 0x81, 0x91, 0xa1, 0x08,
    0x23, 0x42, 0xb1, 0xc1, 0x15, 0x52, 0xd1, 0xf0, 0x24, 0x33, 0x62, 0x72,
    0x82, 0x09, 0x0a, 0x16, 0x17, 0x18, 0x19, 0x1a, 0x25, 0x26, 0x27, 0x28,
    0x29, 0x2a, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39, 0x3a, 0x43, 0x44, 0x45,
    0x46, 0x47, 0x48, 0x49, 0x4a, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59,
    0x5a, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69, 0x6a, 0x73, 0x74, 0x75,
    0x76, 0x77, 0x78, 0x79, 0x7a, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89,
    0x8a, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9a, 0xa2, 0xa3,
    0xa4, 0xa5, 0xa6, 0xa7, 0xa8, 0xa9, 0xaa, 0xb2, 0xb3, 0xb4, 0xb5, 0xb6,
    0xb7, 0xb8, 0xb9, 0xba, 0xc2, 0xc3, 0xc4, 0xc5, 0xc6, 0xc7, 0xc8, 0xc9,
    0xca, 0xd2, 0xd3, 0xd4, 0xd5, 0xd6, 0xd7, 0xd8, 0xd9, 0xda, 0xe1, 0xe2,
    0xe3, 0xe4, 0xe5, 0xe6, 0xe7, 0xe8, 0xe9, 0xea, 0xf1, 0xf2, 0xf3, 0xf4,
    0xf5, 0xf6, 0xf7, 0xf8, 0xf9, 0xfa};
static const uint8_t jz_ac_chr_bits[17] = {0, 0, 2, 1, 2, 4, 4, 3, 4,
                                           7, 5, 4, 4, 0, 1, 2, 0x77};
static const uint8_t jz_ac_chr_vals[162] = {
    0x00, 0x01, 0x02, 0x03, 0x11, 0x04, 0x05, 0x21, 0x31, 0x06, 0x12, 0x41,
    0x51, 0x07, 0x61, 0x71, 0x13, 0x22, 0x32, 0x81, 0x08, 0x14, 0x42, 0x91,
    0xa1, 0xb1, 0xc1, 0x09, 0x23, 0x33, 0x52, 0xf0, 0x15, 0x62, 0x72, 0xd1,
    0x0a, 0x16, 0x24, 0x34, 0xe1, 0x25, 0xf1, 0x17, 0x18, 0x19, 0x1a, 0x26,
    0x27, 0x28, 0x29, 0x2a, 0x35, 0x36, 0x37, 0x38, 0x39, 0x3a, 0x43, 0x44,
    0x45, 0x46, 0x47, 0x48, 0x49, 0x4a, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58,
    0x59, 0x5a, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69, 0x6a, 0x73, 0x74,
    0x75, 0x76, 0x77, 0x78, 0x79, 0x7a, 0x82, 0x83, 0x84, 0x85, 0x86, 0x87,
    0x88, 0x89, 0x8a, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9a,
    0xa2, 0xa3, 0xa4, 0xa5, 0xa6, 0xa7, 0xa8, 0xa9, 0xaa, 0xb2, 0xb3, 0xb4,
    0xb5, 0xb6, 0xb7, 0xb8, 0xb9, 0xba, 0xc2, 0xc3, 0xc4, 0xc5, 0xc6, 0xc7,
    0xc8, 0xc9, 0xca, 0xd2, 0xd3, 0xd4, 0xd5, 0xd6, 0xd7, 0xd8, 0xd9, 0xda,
    0xe2, 0xe3, 0xe4, 0xe5, 0xe6, 0xe7, 0xe8, 0xe9, 0xea, 0xf2, 0xf3, 0xf4,
    0xf5, 0xf6, 0xf7, 0xf8, 0xf9, 0xfa};

// ---- 内部状態 ----
typedef struct {
    uint8_t *out;
    size_t cap, len;
    uint32_t bitbuf;
    uint8_t bitcnt;       // ビットバッファ内の未出力ビット数 (0..31)
    bool overflow;
    uint16_t dc_lum_code[12], dc_chr_code[12];
    uint8_t dc_lum_size[12], dc_chr_size[12];
    uint16_t ac_lum_code[256], ac_chr_code[256];
    uint8_t ac_lum_size[256], ac_chr_size[256];
    uint8_t qtab[2][64];   // zigzag順
    float qinv[2][64];     // 自然順の 1/q (DCTスケール込み)
    int dc_pred[3];
} jz_t;

static void jz_byte(jz_t *j, uint8_t b) {
    if (j->len >= j->cap) { j->overflow = true; return; }
    j->out[j->len++] = b;
}
static void jz_word(jz_t *j, uint16_t w) { jz_byte(j, w >> 8); jz_byte(j, w & 0xFF); }

static void jz_bits(jz_t *j, uint16_t code, int size) {
    j->bitbuf |= (uint32_t)(code & ((1u << size) - 1)) << (24 - j->bitcnt - size);
    j->bitcnt += size;
    while (j->bitcnt >= 8) {
        uint8_t b = (j->bitbuf >> 16) & 0xFF;
        jz_byte(j, b);
        if (b == 0xFF) jz_byte(j, 0x00);
        j->bitbuf <<= 8;
        j->bitcnt -= 8;
    }
}
static void jz_flushbits(jz_t *j) {
    if (j->bitcnt > 0) jz_bits(j, 0xFF, 8 - j->bitcnt); // 1埋めでバイト境界へ
    j->bitbuf = 0; j->bitcnt = 0;
}

static void jz_build_huff(const uint8_t bits[17], const uint8_t *vals,
                          uint16_t *code, uint8_t *size, int maxsym) {
    memset(size, 0, maxsym);
    int k = 0;
    uint16_t c = 0;
    for (int l = 1; l <= 16; l++) {
        for (int i = 0; i < bits[l]; i++) {
            code[vals[k]] = c++;
            size[vals[k]] = l;
            k++;
        }
        c <<= 1;
    }
}

// 素直な 2D DCT-II (float) in: レベルシフト済み -128..127
static void jz_dct8x8(const float in[64], float out[64]) {
    static float cs[8][8];
    static int init = 0;
    if (!init) {
        for (int u = 0; u < 8; u++)
            for (int x = 0; x < 8; x++)
                cs[u][x] = (float)cos((2 * x + 1) * u * 3.14159265358979 / 16.0);
        init = 1;
    }
    float tmp[64];
    for (int y = 0; y < 8; y++)          // 行方向
        for (int u = 0; u < 8; u++) {
            float s = 0;
            for (int x = 0; x < 8; x++) s += in[y * 8 + x] * cs[u][x];
            tmp[y * 8 + u] = s;
        }
    for (int u = 0; u < 8; u++)          // 列方向
        for (int v = 0; v < 8; v++) {
            float s = 0;
            for (int y = 0; y < 8; y++) s += tmp[y * 8 + u] * cs[v][y];
            float cu = (u == 0) ? 0.70710678f : 1.0f;
            float cv = (v == 0) ? 0.70710678f : 1.0f;
            out[v * 8 + u] = s * cu * cv * 0.25f;
        }
}

static int jz_bitsize(int v) {
    int a = v < 0 ? -v : v, n = 0;
    while (a) { a >>= 1; n++; }
    return n;
}

// 1ブロック符号化 comp: 0=Y, 1=C
static void jz_block(jz_t *j, const float px[64], int comp, int dcidx) {
    float dct[64];
    jz_dct8x8(px, dct);
    int q[64];
    for (int i = 0; i < 64; i++) {
        float v = dct[jz_zigzag[i]] * j->qinv[comp][i];
        q[i] = (int)(v < 0 ? v - 0.5f : v + 0.5f);
    }
    const uint16_t *dcc = comp ? j->dc_chr_code : j->dc_lum_code;
    const uint8_t *dcs = comp ? j->dc_chr_size : j->dc_lum_size;
    const uint16_t *acc = comp ? j->ac_chr_code : j->ac_lum_code;
    const uint8_t *acs = comp ? j->ac_chr_size : j->ac_lum_size;

    int diff = q[0] - j->dc_pred[dcidx];
    j->dc_pred[dcidx] = q[0];
    int n = jz_bitsize(diff);
    jz_bits(j, dcc[n], dcs[n]);
    if (n) jz_bits(j, diff < 0 ? diff - 1 : diff, n);

    int run = 0;
    for (int i = 1; i < 64; i++) {
        if (q[i] == 0) { run++; continue; }
        while (run > 15) { jz_bits(j, acc[0xF0], acs[0xF0]); run -= 16; }
        n = jz_bitsize(q[i]);
        int sym = (run << 4) | n;
        jz_bits(j, acc[sym], acs[sym]);
        jz_bits(j, q[i] < 0 ? q[i] - 1 : q[i], n);
        run = 0;
    }
    if (run) jz_bits(j, acc[0x00], acs[0x00]);
}

// RGB -> YCbCr (BT.601 full range, JFIF)
static void jz_ycc(uint8_t r, uint8_t g, uint8_t b, float *y, float *cb, float *cr) {
    *y = 0.299f * r + 0.587f * g + 0.114f * b - 128.0f;
    *cb = -0.168736f * r - 0.331264f * g + 0.5f * b;
    *cr = 0.5f * r - 0.418688f * g - 0.081312f * b;
}

// 画素取得 (端はクランプ)
static void jz_fetch(const uint8_t *rgb, int w, int h, int x, int y,
                     uint8_t *r, uint8_t *g, uint8_t *b) {
    if (x >= w) x = w - 1;
    if (y >= h) y = h - 1;
    const uint8_t *p = rgb + (size_t)(y * w + x) * 3;
    *r = p[0]; *g = p[1]; *b = p[2];
}

// メイン 戻り値: JPEGバイト数、負=バッファ不足
static int32_t usb_disp_prot_t6_jpeg_encode(uint8_t *out, size_t outcap, const uint8_t *rgb,
                           uint16_t w, uint16_t h, uint8_t quality, uint8_t subsamp) {
    jz_t jj, *j = &jj;
    memset(j, 0, sizeof(*j));
    j->out = out; j->cap = outcap;

    // 量子化テーブル (libjpeg 流スケーリング)
    int scale = quality < 50 ? 5000 / (quality < 1 ? 1 : quality)
                             : 200 - 2 * (quality > 100 ? 100 : quality);
    for (int c = 0; c < 2; c++) {
        const uint8_t *base = c ? jz_qchr : jz_qlum;
        for (int i = 0; i < 64; i++) {
            int v = (base[jz_zigzag[i]] * scale + 50) / 100; // 自然順→zigzag格納
            if (v < 1) v = 1;
            if (v > 255) v = 255;
            j->qtab[c][i] = (uint8_t)v;
            j->qinv[c][i] = 1.0f / v;
        }
    }
    jz_build_huff(jz_dc_lum_bits, jz_dc_lum_vals, j->dc_lum_code, j->dc_lum_size, 12);
    jz_build_huff(jz_dc_chr_bits, jz_dc_chr_vals, j->dc_chr_code, j->dc_chr_size, 12);
    jz_build_huff(jz_ac_lum_bits, jz_ac_lum_vals, j->ac_lum_code, j->ac_lum_size, 256);
    jz_build_huff(jz_ac_chr_bits, jz_ac_chr_vals, j->ac_chr_code, j->ac_chr_size, 256);

    // ---- ヘッダ ----
    jz_word(j, 0xFFD8); // SOI
    // APP0 JFIF
    jz_word(j, 0xFFE0); jz_word(j, 16);
    jz_byte(j, 'J'); jz_byte(j, 'F'); jz_byte(j, 'I'); jz_byte(j, 'F'); jz_byte(j, 0);
    jz_word(j, 0x0101); jz_byte(j, 0); jz_word(j, 1); jz_word(j, 1);
    jz_byte(j, 0); jz_byte(j, 0);
    // DQT x2
    for (int c = 0; c < 2; c++) {
        jz_word(j, 0xFFDB); jz_word(j, 67); jz_byte(j, c);
        for (int i = 0; i < 64; i++) jz_byte(j, j->qtab[c][i]);
    }
    // SOF0
    jz_word(j, 0xFFC0); jz_word(j, 17); jz_byte(j, 8);
    jz_word(j, h); jz_word(j, w); jz_byte(j, 3);
    uint8_t hv = (subsamp == USB_DISP_PROT_T6_JPEG_420) ? 0x22 : 0x11;
    jz_byte(j, 1); jz_byte(j, hv);   jz_byte(j, 0); // Y
    jz_byte(j, 2); jz_byte(j, 0x11); jz_byte(j, 1); // Cb
    jz_byte(j, 3); jz_byte(j, 0x11); jz_byte(j, 1); // Cr
    // DHT x4
    static const struct { const uint8_t *bits, *vals; int nv; uint8_t id; } hts[4] = {
        {jz_dc_lum_bits, jz_dc_lum_vals, 12, 0x00},
        {jz_ac_lum_bits, jz_ac_lum_vals, 162, 0x10},
        {jz_dc_chr_bits, jz_dc_chr_vals, 12, 0x01},
        {jz_ac_chr_bits, jz_ac_chr_vals, 162, 0x11},
    };
    for (int t = 0; t < 4; t++) {
        jz_word(j, 0xFFC4); jz_word(j, (uint16_t)(19 + hts[t].nv));
        jz_byte(j, hts[t].id);
        for (int i = 1; i <= 16; i++) jz_byte(j, hts[t].bits[i]);
        for (int i = 0; i < hts[t].nv; i++) jz_byte(j, hts[t].vals[i]);
    }
    // SOS
    jz_word(j, 0xFFDA); jz_word(j, 12); jz_byte(j, 3);
    jz_byte(j, 1); jz_byte(j, 0x00);
    jz_byte(j, 2); jz_byte(j, 0x11);
    jz_byte(j, 3); jz_byte(j, 0x11);
    jz_byte(j, 0); jz_byte(j, 63); jz_byte(j, 0);

    // ---- スキャン ----
    j->dc_pred[0] = j->dc_pred[1] = j->dc_pred[2] = 0;
    if (subsamp == USB_DISP_PROT_T6_JPEG_420) {
        for (int my = 0; my < h; my += 16) {
            for (int mx = 0; mx < w; mx += 16) {
                float Y[4][64], CB[64], CR[64];
                float cbs[64], crs[64]; // 16x16→8x8 平均用 (2x2和を先に集める)
                memset(cbs, 0, sizeof(cbs));
                memset(crs, 0, sizeof(crs));
                for (int by = 0; by < 16; by++) {
                    for (int bx = 0; bx < 16; bx++) {
                        uint8_t r, g, b;
                        float y, cb, cr;
                        jz_fetch(rgb, w, h, mx + bx, my + by, &r, &g, &b);
                        jz_ycc(r, g, b, &y, &cb, &cr);
                        Y[(by / 8) * 2 + (bx / 8)][(by % 8) * 8 + (bx % 8)] = y;
                        cbs[(by / 2) * 8 + (bx / 2)] += cb * 0.25f;
                        crs[(by / 2) * 8 + (bx / 2)] += cr * 0.25f;
                    }
                }
                memcpy(CB, cbs, sizeof(CB));
                memcpy(CR, crs, sizeof(CR));
                for (int i = 0; i < 4; i++) jz_block(j, Y[i], 0, 0);
                jz_block(j, CB, 1, 1);
                jz_block(j, CR, 1, 2);
            }
        }
    } else {
        for (int my = 0; my < h; my += 8) {
            for (int mx = 0; mx < w; mx += 8) {
                float Y[64], CB[64], CR[64];
                for (int by = 0; by < 8; by++)
                    for (int bx = 0; bx < 8; bx++) {
                        uint8_t r, g, b;
                        jz_fetch(rgb, w, h, mx + bx, my + by, &r, &g, &b);
                        jz_ycc(r, g, b, &Y[by * 8 + bx], &CB[by * 8 + bx],
                               &CR[by * 8 + bx]);
                    }
                jz_block(j, Y, 0, 0);
                jz_block(j, CB, 1, 1);
                jz_block(j, CR, 1, 2);
            }
        }
    }
    jz_flushbits(j);
    jz_word(j, 0xFFD9); // EOI
    return j->overflow ? -1 : (int32_t)j->len;
}

#endif  // USB_DISP_PROT_T6_JPEG_H_

