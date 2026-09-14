//
// ######################################################################
//
//    usb_disp_prot_dl-1xx - DisplayLink DL-1x0 / 1x5 プロトコル実装
//
//    Copyright (C) 2026
//      Hideto Kikuchi / PJラボ (@pcjpnet) - https://pc-jp.net/
//
// ######################################################################
//

#include <string.h>

#include "usb_disp_prot.h"

#define USB_DISP_DL_LINE_MAX(w) \
    (7u * (((w) + 255u) / 256u) + 3u * (uint32_t)(w) + 16u)

// 共有スクラッチ (描画 API は単一スレッドから逐次呼び出し = 共有可)
static uint8_t s_desc_buf[64];
static uint8_t s_cmdbuf[USB_DISP_DL_LINE_MAX(USB_DISP_MAX_WIDTH)];

// ---------------------------------------------------------------
// レジスタ / エンコードヘルパ
// ---------------------------------------------------------------

static bool dl_ctrl(usb_disp_t *d, uint8_t bmRequestType, uint8_t bRequest,
                    uint16_t wValue, uint16_t wIndex, void *data,
                    uint16_t wLength, uint16_t *actual) {
    return usb_disp_prot_ctrl(d, bmRequestType, bRequest, wValue, wIndex,
                               data, wLength, actual);
}

static uint8_t *set_register(uint8_t *buf, uint8_t reg, uint8_t val) {
    *buf++ = 0xAF;
    *buf++ = 0x20;
    *buf++ = reg;
    *buf++ = val;
    return buf;
}
static uint8_t *set_register_16(uint8_t *buf, uint8_t reg, uint16_t val) {
    buf = set_register(buf, reg, (uint8_t)(val >> 8));
    return set_register(buf, (uint8_t)(reg + 1), (uint8_t)val);
}
static uint8_t *set_register_16be(uint8_t *buf, uint8_t reg, uint16_t val) {
    buf = set_register(buf, reg, (uint8_t)val);
    return set_register(buf, (uint8_t)(reg + 1), (uint8_t)(val >> 8));
}
static uint16_t lfsr16(uint16_t actual_count) {
    uint32_t lv = 0xFFFF;
    while (actual_count--) {
        lv = ((lv << 1) |
              (((lv >> 15) ^ (lv >> 4) ^ (lv >> 2) ^ (lv >> 1)) & 1)) &
             0xFFFF;
    }
    return (uint16_t)lv;
}
static uint8_t *set_register_lfsr16(uint8_t *buf, uint8_t reg, uint16_t val) {
    return set_register_16(buf, reg, lfsr16(val));
}

// udlfb: dlfb_compress_hline() と同じ RLE エンコード (0xAF 0x6B)
static size_t dl_compress_span(uint32_t dev_addr, const uint16_t *pixels,
                               uint32_t count, uint8_t *out) {
    const uint16_t *pixel = pixels;
    const uint16_t *const pixel_end = pixels + count;
    uint8_t *cmd = out;

    while (pixel < pixel_end) {
        uint8_t *raw_pixels_count_byte;
        uint8_t *cmd_pixels_count_byte;
        const uint16_t *raw_pixel_start;
        const uint16_t *cmd_pixel_start;
        const uint16_t *cmd_pixel_end;

        *cmd++ = 0xAF;
        *cmd++ = 0x6B;
        *cmd++ = (uint8_t)(dev_addr >> 16);
        *cmd++ = (uint8_t)(dev_addr >> 8);
        *cmd++ = (uint8_t)dev_addr;

        cmd_pixels_count_byte = cmd++;
        cmd_pixel_start = pixel;
        raw_pixels_count_byte = cmd++;
        raw_pixel_start = pixel;

        {
            uint32_t remain = (uint32_t)(pixel_end - pixel);
            cmd_pixel_end = pixel + (remain > 256 ? 256 : remain);
        }

        while (pixel < cmd_pixel_end) {
            const uint16_t *const repeating_pixel = pixel;
            uint16_t v = *pixel;
            *cmd++ = (uint8_t)(v >> 8);
            *cmd++ = (uint8_t)v;
            pixel++;

            if ((pixel < cmd_pixel_end) && (*pixel == *repeating_pixel)) {
                *raw_pixels_count_byte =
                    (uint8_t)((repeating_pixel - raw_pixel_start) + 1);
                while ((pixel < cmd_pixel_end) && (*pixel == *repeating_pixel))
                    pixel++;
                *cmd++ = (uint8_t)((pixel - repeating_pixel) - 1);
                raw_pixel_start = pixel;
                raw_pixels_count_byte = cmd++;
            }
        }

        if (pixel > raw_pixel_start) {
            *raw_pixels_count_byte = (uint8_t)(pixel - raw_pixel_start);
        } else {
            cmd--;
        }
        *cmd_pixels_count_byte = (uint8_t)(pixel - cmd_pixel_start);
        dev_addr += (uint32_t)(pixel - cmd_pixel_start) * 2;
    }
    return (size_t)(cmd - out);
}

// ---------------------------------------------------------------
// チップ判別
// ---------------------------------------------------------------

static bool dl_select_channel(usb_disp_t *d) {
    static const uint8_t key[16] = {
        0x57, 0xCD, 0xDC, 0xA7, 0x1C, 0x88, 0x5E, 0x15,
        0x60, 0xFE, 0xC6, 0x97, 0x16, 0x3D, 0x47, 0xF2,
    };
    uint8_t buf[16];
    memcpy(buf, key, 16);
    return dl_ctrl(d, 0x40, 0x12, 0, 0, buf, 16, NULL);
}

// ベンダーディスクリプタ (0x5F) の KLV 列から key 0x0200 = max_area
static uint32_t parse_vendor_desc(const uint8_t *buf, uint16_t buflen) {
    if (buflen < 6) return 0;
    uint16_t total = buf[0];
    if (total > buflen) total = buflen;
    if (buf[1] != 0x5F || buf[2] != 0x01 || buf[3] != 0x00) return 0;
    const uint8_t *p = buf + 5;
    const uint8_t *end = buf + total;
    while (p + 3 <= end) {
        uint16_t key = (uint16_t)(p[0] | (p[1] << 8));
        uint8_t len = p[2];
        p += 3;
        if (p + len > end) break;
        if (key == 0x0200 && len >= 4) {
            return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
                   ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
        }
        p += len;
    }
    return 0;
}

// チップ種別 → 公称 max_area [px]。
// 通常は max_area をチップが自己申告する (0x5F ベンダーディスクリプタ) が、
// 申告しない個体をチップ確定リスト (usb_disp_model.h) で救済したときはここから導出する
static uint32_t dl_chip_nominal_area(usb_disp_chip_t chip) {
    switch (chip) {
    case USB_DISP_CHIP_DL120: return 1470000;   // 1400x1050
    case USB_DISP_CHIP_DL160: return 1920000;   // 1600x1200
    case USB_DISP_CHIP_DL115: return 614400;    // 1024x600
    case USB_DISP_CHIP_DL125: return 1310720;   // 1280x1024
    case USB_DISP_CHIP_DL165: return 2073600;   // 1920x1080
    case USB_DISP_CHIP_DL195: return 2359296;   // 2048x1152
    default:                  return 0;
    }
}

// チップ判別: status dword (世代) + ベンダーディスクリプタ (SKU)。attach から呼ばれる
static void dl_detect_chip(usb_disp_t *d) {
    d->chip = USB_DISP_CHIP_UNKNOWN;
    d->max_area = 0;

    bool alex = false, ollie = false;
    uint8_t sbuf[4] = {0};
    uint16_t actual = 0;
    if (dl_ctrl(d, 0xC0, 0x06, 0, 0, sbuf, 4, &actual) && actual == 4) {
        usb_disp_log("[DL] status dword: %02X %02X %02X %02X", sbuf[0],
                     sbuf[1], sbuf[2], sbuf[3]);
        if (sbuf[3] == 0xF1)            ollie = true;  // DL-1x5 世代
        else if ((sbuf[3] >> 4) == 0xF) alex = true;   // DL-1x0 世代
    }

    actual = 0;
    if (dl_ctrl(d, 0x80, 0x06, 0x5F00, 0, s_desc_buf, 64, &actual) &&
        actual > 5) {
        usb_disp_log("[DL] vendor desc: len=%u %02X %02X %02X %02X %02X...",
                     actual, s_desc_buf[0], s_desc_buf[1], s_desc_buf[2],
                     s_desc_buf[3], s_desc_buf[4]);
        d->max_area = parse_vendor_desc(s_desc_buf, actual);
    }
    if (d->max_area == 0) {
        // フォールバック: コンフィグディスクリプタ内の 0x5F (HAL が捕捉)
        uint16_t n = usb_disp_hal_vendor_desc(d->hal, s_desc_buf,
                                              sizeof(s_desc_buf));
        if (n > 5) {
            d->max_area = parse_vendor_desc(s_desc_buf, n);
            usb_disp_log("[DL] vendor desc from config (len=%u, max_area=%lu)",
                         n, (unsigned long)d->max_area);
        }
    }

    // チップ確定リスト (usb_disp_model.h) による救済:
    // 0x5F に応答しない個体でも、分解等で実チップが確認済みならチップを直接確定し、
    // max_area はチップ種別の公称値から導出する
    if (d->max_area == 0) {
        usb_disp_chip_t known = usb_disp_model_chip(d->vid, d->pid);
        if (known != USB_DISP_CHIP_UNKNOWN) {
            d->chip = known;
            d->max_area = dl_chip_nominal_area(known);
            usb_disp_log("[DL] known product: %s",
                         usb_disp_model_name(d->vid, d->pid));
        }
    }

    if (d->chip != USB_DISP_CHIP_UNKNOWN) {
        // チップ確定リストで判定済み (以下の閾値判定は不要)
    } else if (d->max_area > 0 && alex) {
        d->chip = (d->max_area >= 1764000) ? USB_DISP_CHIP_DL160
                                           : USB_DISP_CHIP_DL120;
    } else if (d->max_area > 0) {
        if (d->max_area >= 2359296)      d->chip = USB_DISP_CHIP_DL195;
        else if (d->max_area >= 2073600) d->chip = USB_DISP_CHIP_DL165;
        else if (d->max_area >= 1310720) d->chip = USB_DISP_CHIP_DL125;
        else                             d->chip = USB_DISP_CHIP_DL115;
    } else if (ollie) {
        d->chip = USB_DISP_CHIP_DL1X5;
    } else if (alex) {
        d->chip = USB_DISP_CHIP_DL1X0;
    }
    usb_disp_log("[DL] chip: %s (max_area=%lu px)", usb_disp_chip_name(d),
                 (unsigned long)d->max_area);
}

// ---------------------------------------------------------------
// prot ops
// ---------------------------------------------------------------

static bool dl_match(uint16_t vid, uint16_t pid) {
    (void)pid;
    return vid == 0x17E9;
}

static bool dl_attach(usb_disp_t *d) {
    if (!dl_select_channel(d))
        usb_disp_log("[DISP%d] channel select failed (continue)",
                     usb_disp_index(d));
    dl_detect_chip(d);
    return true;
}

// EDID 読み出し (1バイトずつ)。
// バイトオフセットは wValue の上位バイトに載せるため 0..255 しか指定できない
// このチップから読めるのは EDID の先頭 256 バイト (ベースブロック + 拡張ブロック1個) まで
#define DL_EDID_MAX 256

static uint16_t dl_read_edid(usb_disp_t *d, uint16_t offset, uint8_t *buf,
                             uint16_t len) {
    uint8_t rbuf[2];
    if (offset >= DL_EDID_MAX) return 0;
    if ((uint32_t)offset + len > DL_EDID_MAX) len = (uint16_t)(DL_EDID_MAX - offset);
    for (uint16_t i = 0; i < len; i++) {
        uint16_t actual = 0;
        if (!dl_ctrl(d, 0xC0, 0x02, (uint16_t)((offset + i) << 8), 0xA1, rbuf,
                     2, &actual) ||
            actual != 2) {
            return i;
        }
        buf[i] = rbuf[1];
    }
    return len;
}

static bool dl_set_mode(usb_disp_t *d, const usb_disp_mode_t *m) {
    uint8_t buf[192];
    uint8_t *w = buf;
    uint32_t fb_bytes = (uint32_t)m->width * m->height * 2;

    uint16_t xds = (uint16_t)(m->hbp + m->hsync);
    uint16_t xde = (uint16_t)(xds + m->width);
    uint16_t yds = (uint16_t)(m->vbp + m->vsync);
    uint16_t yde = (uint16_t)(yds + m->height);
    uint16_t yec = (uint16_t)(m->height + m->vbp + m->vfp + m->vsync);

    w = set_register(w, 0xFF, 0x00);
    // 色深度: 0x00 = 16bpp / 0x01 = 24bpp
    // (16+8 デュアルプレーン、base16 = RGB565、base8 = R[2:0]G[1:0]B[2:0] の下位ビット面。
    // 分割は libdlo dlo_grfx.c の DLO_RG16/GB16/RGB8 と同一)
    w = set_register(w, 0x00, d->depth24 ? 0x01 : 0x00);
    w = set_register(w, 0x20, 0);
    w = set_register(w, 0x21, 0);
    w = set_register(w, 0x22, 0);
    w = set_register(w, 0x26, (uint8_t)(fb_bytes >> 16));
    w = set_register(w, 0x27, (uint8_t)(fb_bytes >> 8));
    w = set_register(w, 0x28, (uint8_t)fb_bytes);
    w = set_register_lfsr16(w, 0x01, xds);
    w = set_register_lfsr16(w, 0x03, xde);
    w = set_register_lfsr16(w, 0x05, yds);
    w = set_register_lfsr16(w, 0x07, yde);
    w = set_register_lfsr16(w, 0x09, (uint16_t)(xde + m->hfp - 1));
    w = set_register_lfsr16(w, 0x0B, 1);
    w = set_register_lfsr16(w, 0x0D, (uint16_t)(m->hsync + 1));
    w = set_register_16(w, 0x0F, m->width);
    w = set_register_lfsr16(w, 0x11, yec);
    w = set_register_lfsr16(w, 0x13, 0);
    w = set_register_lfsr16(w, 0x15, m->vsync);
    w = set_register_16(w, 0x17, m->height);
    w = set_register_16be(w, 0x1B, (uint16_t)(m->pclk_khz / 5));
    w = set_register(w, 0x1F, 0x00);
    w = set_register(w, 0xFF, 0xFF);

    uint32_t n = (uint32_t)(w - buf);
    if (usb_disp_hal_bulk_write(d->hal, buf, n) != n) return false;
    return usb_disp_hal_bulk_flush(d->hal, 1000);
}

// 矩形更新 (クリップ済み)。行毎に RLE で送る。stride_px=0 は同一行の繰り返し
static bool dl_update(usb_disp_t *d, uint16_t x, uint16_t y, uint16_t w,
                      uint16_t h, const uint16_t *px, uint32_t stride_px) {
    for (uint16_t row = 0; row < h; row++) {
        const uint16_t *src = stride_px ? px + (uint32_t)row * stride_px : px;
        uint32_t dev_addr = (((uint32_t)(y + row) * d->width) + x) * 2;
        size_t n = dl_compress_span(dev_addr, src, w, s_cmdbuf);
        if (usb_disp_hal_bulk_write(d->hal, s_cmdbuf, (uint32_t)n) != n)
            return false;
    }
    return true;
}

// 画面内矩形コピー (COPY16 0xAF 0x6A)
// ---- 24bpp (16+8 デュアルプレーン) ----

// B,G,R 3バイト → RGB565 (base16 プレーン用)
static inline uint16_t dl_px565(const uint8_t *p) {
    return (uint16_t)(((p[2] & 0xF8) << 8) | ((p[1] & 0xFC) << 3) |
                      (p[0] >> 3));
}
// B,G,R 3バイト → base8 プレーンの下位ビット面 (R[2:0] G[1:0] B[2:0])
static inline uint8_t dl_px8(const uint8_t *p) {
    return (uint8_t)(((p[2] & 0x07) << 5) | ((p[1] & 0x03) << 3) |
                     (p[0] & 0x07));
}

static uint16_t s_row565[USB_DISP_MAX_WIDTH];   // 888 → 565 変換した1行

// 矩形更新 (RGB888)。行毎に base16 (RLE) と base8 (RAW8) の両方を送る
static bool dl_update888(usb_disp_t *d, uint16_t x, uint16_t y, uint16_t w,
                         uint16_t h, const uint8_t *px, uint32_t stride_px) {
    uint32_t base8_start = (uint32_t)d->width * d->height * 2;
    for (uint16_t row = 0; row < h; row++) {
        const uint8_t *src =
            stride_px ? px + (uint32_t)row * stride_px * 3 : px;

        // base16 プレーン (RGB565, 既存の RLE 圧縮)
        for (uint16_t i = 0; i < w; i++) s_row565[i] = dl_px565(src + i * 3);
        uint32_t adr16 = (((uint32_t)(y + row) * d->width) + x) * 2;
        size_t n = dl_compress_span(adr16, s_row565, w, s_cmdbuf);
        if (usb_disp_hal_bulk_write(d->hal, s_cmdbuf, (uint32_t)n) != n)
            return false;

        // base8 プレーン (下位ビット面, RAW8: AF 60 addr[3] count(0=256) data)
        uint32_t adr8 = base8_start + ((uint32_t)(y + row) * d->width) + x;
        uint8_t *q = s_cmdbuf;
        uint32_t rem = w;
        const uint8_t *sp = src;
        while (rem) {
            uint32_t seg = (rem > 256) ? 256 : rem;
            *q++ = 0xAF;
            *q++ = 0x60;
            *q++ = (uint8_t)(adr8 >> 16);
            *q++ = (uint8_t)(adr8 >> 8);
            *q++ = (uint8_t)adr8;
            *q++ = (uint8_t)(seg == 256 ? 0 : seg);
            for (uint32_t i = 0; i < seg; i++, sp += 3) *q++ = dl_px8(sp);
            adr8 += seg;
            rem -= seg;
        }
        uint32_t len8 = (uint32_t)(q - s_cmdbuf);
        if (usb_disp_hal_bulk_write(d->hal, s_cmdbuf, len8) != len8)
            return false;
    }
    return true;
}

static bool dl_copy(usb_disp_t *d, uint16_t sx, uint16_t sy, uint16_t dx,
                    uint16_t dy, uint16_t w, uint16_t h) {
    uint32_t seg = 256;
    bool rtl = false;
    if (sy == dy && sx != dx) {  // 同一行内の水平シフトのみ分割が必要
        uint32_t dist = (dx > sx) ? (uint32_t)(dx - sx) : (uint32_t)(sx - dx);
        if (dist < seg) seg = dist;
        rtl = (dx > sx);  // 右シフトは右端セグメントから
    }
    bool bottom_up = (dy > sy);  // コピー先が下 → 下の行から
    uint32_t nseg = ((uint32_t)w + seg - 1) / seg;

    for (uint16_t i = 0; i < h; i++) {
        uint16_t row = bottom_up ? (uint16_t)(h - 1 - i) : i;
        uint32_t src = (((uint32_t)(sy + row) * d->width) + sx) * 2;
        uint32_t dst = (((uint32_t)(dy + row) * d->width) + dx) * 2;
        uint8_t *p = s_cmdbuf;
        for (uint32_t k = 0; k < nseg; k++) {
            uint32_t off = (rtl ? (nseg - 1 - k) : k) * seg;
            uint32_t n = w - off;
            if (n > seg) n = seg;
            uint32_t s_adr = src + off * 2;
            uint32_t d_adr = dst + off * 2;
            *p++ = 0xAF;
            *p++ = 0x6A;
            *p++ = (uint8_t)(d_adr >> 16);
            *p++ = (uint8_t)(d_adr >> 8);
            *p++ = (uint8_t)d_adr;
            *p++ = (uint8_t)(n == 256 ? 0 : n);
            *p++ = (uint8_t)(s_adr >> 16);
            *p++ = (uint8_t)(s_adr >> 8);
            *p++ = (uint8_t)s_adr;
            if (p + 9 > s_cmdbuf + sizeof(s_cmdbuf)) {
                uint32_t len = (uint32_t)(p - s_cmdbuf);
                if (usb_disp_hal_bulk_write(d->hal, s_cmdbuf, len) != len)
                    return false;
                p = s_cmdbuf;
            }
        }
        // 24bpp 時は base8 プレーンも同じ形でコピー
        // (COPY8: AF 62 dest[3] len(0=256) src[3]、アドレスはバイト単位)
        if (d->depth24) {
            uint32_t base8 = (uint32_t)d->width * d->height * 2;
            uint32_t src8 = base8 + ((uint32_t)(sy + row) * d->width) + sx;
            uint32_t dst8 = base8 + ((uint32_t)(dy + row) * d->width) + dx;
            for (uint32_t k = 0; k < nseg; k++) {
                uint32_t off = (rtl ? (nseg - 1 - k) : k) * seg;
                uint32_t n = w - off;
                if (n > seg) n = seg;
                uint32_t s_adr = src8 + off;
                uint32_t d_adr = dst8 + off;
                *p++ = 0xAF;
                *p++ = 0x62;
                *p++ = (uint8_t)(d_adr >> 16);
                *p++ = (uint8_t)(d_adr >> 8);
                *p++ = (uint8_t)d_adr;
                *p++ = (uint8_t)(n == 256 ? 0 : n);
                *p++ = (uint8_t)(s_adr >> 16);
                *p++ = (uint8_t)(s_adr >> 8);
                *p++ = (uint8_t)s_adr;
                if (p + 9 > s_cmdbuf + sizeof(s_cmdbuf)) {
                    uint32_t len = (uint32_t)(p - s_cmdbuf);
                    if (usb_disp_hal_bulk_write(d->hal, s_cmdbuf, len) != len)
                        return false;
                    p = s_cmdbuf;
                }
            }
        }
        uint32_t len = (uint32_t)(p - s_cmdbuf);
        if (len && usb_disp_hal_bulk_write(d->hal, s_cmdbuf, len) != len)
            return false;
    }
    return true;
}

static bool dl_flush(usb_disp_t *d, uint32_t timeout_ms) {
    // DL チップはストリーム最後のコマンドを「次のデータの先頭」が来るまで
    // 実行保留することがある → フラッシュコマンド 0xAF 0xA0
    if (d->ready) {
        static const uint8_t k_sync[2] = {0xAF, 0xA0};
        usb_disp_hal_bulk_write(d->hal, k_sync, 2);
    }
    return usb_disp_hal_bulk_flush(d->hal, timeout_ms);
}

static bool dl_blank(usb_disp_t *d, bool on) {
    uint8_t buf[16];
    uint8_t *w = buf;
    w = set_register(w, 0xFF, 0x00);
    w = set_register(w, 0x1F, on ? 0x07 : 0x00);
    w = set_register(w, 0xFF, 0xFF);
    uint32_t n = (uint32_t)(w - buf);
    if (usb_disp_hal_bulk_write(d->hal, buf, n) != n) return false;
    return usb_disp_hal_bulk_flush(d->hal, 1000);
}

const usb_disp_prot_t usb_disp_prot_dl1xx = {
    .name = "DL-1xx",
    .caps = USB_DISP_PROT_CAP_SHADOW | USB_DISP_PROT_CAP_888,
    .match = dl_match,
    .attach = dl_attach,
    .detach = NULL,
    .set_mode = dl_set_mode,
    .read_edid = dl_read_edid,
    .update = dl_update,
    .update888 = dl_update888,
    .copy = dl_copy,
    .flush = dl_flush,
    .blank = dl_blank,
    .poll = NULL,
};

