//
// ######################################################################
//
//    usb_disp_prot_t6 - MCT Trigger 6 プロトコル実装
//
//    Copyright (C) 2026
//      Hideto Kikuchi / PJラボ (@pcjpnet) - https://pc-jp.net/
//
// ######################################################################
//

#include "usb_disp_prot.h"

#if USB_DISP_PROT_HS

#include <stdlib.h>
#include <string.h>

#if USB_DISP_PORT_ESP32
  #include "driver/jpeg_encode.h"   // ESP32-P4 HW JPEG エンコーダ
  #include "esp_heap_caps.h"        // PSRAM 有無の診断用
#else
  #include "usb_disp_prot_t6_jpeg.h"  // PC: 依存なしソフトエンコーダ
#endif

#define USB_DISP_T6_JPEG_Q 85
#define USB_DISP_T6_MB (1024u * 1024u)
#define USB_DISP_T6_MAX_MODES 40
#define USB_DISP_T6_JOUT_CAP (1024u * 1024u)  // cmd リングの 1MB ステップ前提

typedef struct {
    // チップ情報 (attach で取得)
    uint8_t ram_mb;                   // VRAM サイズ [MB] (1 バイト応答)
    uint8_t nmodes;
    uint8_t modes[USB_DISP_T6_MAX_MODES][32];  // チップのモード表 (0x89)
    // フレーム送信状態
    uint32_t fb_slot[3];
    uint32_t cmd_addr, cmd_limit;
    uint32_t frames;
    // フレームバッファ (ESP32=RGB565 / PC=RGB888) + JPEG 出力
    uint8_t *fb;
    size_t fb_bytes;
    uint8_t *jout;
    size_t jout_cap;
    uint16_t w, h;
    bool dirty;
    bool m24;             // 24bit マスタ (ESP32: FB=RGB888 / PC は常に888)
    uint8_t bpp;          // FB のバイト/px (2 or 3)
    uint16_t alloc_fail_cnt;  // FB 確保失敗の連発ログ抑制
#if USB_DISP_PORT_ESP32
    jpeg_encoder_handle_t enc;
#endif
} t6_priv_t;

static t6_priv_t s_t6[USB_DISP_MAX];

static t6_priv_t *t6p(usb_disp_t *d) { return &s_t6[usb_disp_index(d)]; }

static uint16_t rd16(const uint8_t *p) { return (uint16_t)(p[0] | (p[1] << 8)); }
static void wr32(uint8_t *p, uint32_t v) {
    p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8);
    p[2] = (uint8_t)(v >> 16); p[3] = (uint8_t)(v >> 24);
}
static void wr16(uint8_t *p, uint16_t v) {
    p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8);
}

static bool t6_vin(usb_disp_t *d, uint8_t req, uint16_t wv, uint16_t wi,
                   void *buf, uint16_t len, uint16_t *actual) {
    return usb_disp_prot_ctrl(d, 0xC0, req, wv, wi, buf, len, actual);
}
static bool t6_vout(usb_disp_t *d, uint8_t req, uint16_t wv, uint16_t wi,
                    void *buf, uint16_t len) {
    return usb_disp_prot_ctrl(d, 0x40, req, wv, wi, buf, len, NULL);
}

// ---------------------------------------------------------------
// バッファ管理
// ---------------------------------------------------------------

static void t6_free_bufs(t6_priv_t *p) {
    // ESP32 の jpeg_alloc_encoder_mem も heap_caps 確保なので free でよい
    if (p->fb) { free(p->fb); p->fb = NULL; }
    if (p->jout) { free(p->jout); p->jout = NULL; }
    p->fb_bytes = 0;
}

static bool t6_alloc_bufs(usb_disp_t *d, t6_priv_t *p, uint16_t w, uint16_t h) {
    size_t need = (size_t)w * h * p->bpp;
    if (p->fb && p->fb_bytes == need) return true;
    t6_free_bufs(p);
#if USB_DISP_PORT_ESP32
    jpeg_encode_memory_alloc_cfg_t ic = {JPEG_ENC_ALLOC_INPUT_BUFFER};
    jpeg_encode_memory_alloc_cfg_t oc = {JPEG_ENC_ALLOC_OUTPUT_BUFFER};
    size_t asz;
    p->fb = (uint8_t *)jpeg_alloc_encoder_mem(need, &ic, &asz);
    p->jout = (uint8_t *)jpeg_alloc_encoder_mem(USB_DISP_T6_JOUT_CAP, &oc,
                                                &p->jout_cap);
#else
    p->fb = (uint8_t *)malloc(need);
    p->jout = (uint8_t *)malloc(USB_DISP_T6_JOUT_CAP);
    p->jout_cap = USB_DISP_T6_JOUT_CAP;
#endif
    if (!p->fb || !p->jout) {
        // モード自動選択が候補を総当たりするため失敗は連発する → 抑制
        p->alloc_fail_cnt++;
        if (p->alloc_fail_cnt <= 8 || (p->alloc_fail_cnt & 0x3F) == 0) {
            usb_disp_log("[T6] FB alloc failed (%lu KB)",
                         (unsigned long)(need / 1024));
        }
        t6_free_bufs(p);
        return false;
    }
    p->alloc_fail_cnt = 0;
    p->fb_bytes = need;
    memset(p->fb, 0, need);  // 黒
    return true;
}

// ---------------------------------------------------------------
// JPEG エンコード (全面)
// ---------------------------------------------------------------

// 戻り値: JPEG バイト数、負 = エンコード失敗/バッファ不足
static int32_t t6_encode(usb_disp_t *d, t6_priv_t *p) {
#if USB_DISP_PORT_ESP32
    jpeg_encode_cfg_t cfg = {};
    cfg.height = p->h;
    cfg.width = p->w;
    cfg.src_type = p->m24 ? JPEG_ENCODE_IN_FORMAT_RGB888
                          : JPEG_ENCODE_IN_FORMAT_RGB565;
    cfg.sub_sample = JPEG_DOWN_SAMPLING_YUV420;
    cfg.image_quality = USB_DISP_T6_JPEG_Q;
    uint32_t jlen = 0;
    esp_err_t err = jpeg_encoder_process(p->enc, &cfg, p->fb,
                                         (uint32_t)p->fb_bytes, p->jout,
                                         (uint32_t)p->jout_cap, &jlen);
    if (err != 0) {
        usb_disp_log("[T6] HW encode err=0x%X", (unsigned)err);
        return -1;
    }
    return (int32_t)jlen;
#else
    return usb_disp_prot_t6_jpeg_encode(p->jout, p->jout_cap, p->fb, p->w,
                                        p->h, USB_DISP_T6_JPEG_Q,
                                        USB_DISP_PROT_T6_JPEG_420);
#endif
}

// ---------------------------------------------------------------
// フレーム送信
// ---------------------------------------------------------------

static bool t6_send_frame(usb_disp_t *d, t6_priv_t *p, uint32_t jlen) {
    static uint8_t pad[1024];  // ゼロ (static 初期値)
    uint8_t sel[32], vh[48];

    uint32_t pitch = (uint32_t)((p->w + 31) / 32) * 32;
    uint32_t hceil = (uint32_t)((p->h + 31) / 32) * 32;
    uint32_t y_block = pitch * hceil + 1024;
    uint32_t video_size = jlen + 1024;
    uint32_t total = 48 + video_size;
    uint32_t fb = p->fb_slot[p->frames % 3];
    uint8_t flag = (p->frames < 10) ? 0x80 : 0x00;

    uint32_t step = (total + USB_DISP_T6_MB - 1) / USB_DISP_T6_MB *
                    USB_DISP_T6_MB;
    if (p->cmd_addr + step > p->cmd_limit) {
        p->cmd_addr = 0;
        flag = 0x80;
    }

    memset(vh, 0, 48);
    wr32(vh + 0, 3);             // FLIP_PRIMARY
    wr32(vh + 4, video_size);
    wr32(vh + 12, 6);            // TargetFormat = NV12
    wr16(vh + 16, (uint16_t)pitch);
    wr16(vh + 18, (uint16_t)pitch);
    wr32(vh + 20, fb);
    wr32(vh + 24, fb + y_block);
    wr32(vh + 32, 13);           // SourceFormat = JPEG
    vh[47] = flag;

    memset(sel, 0, 32);
    wr32(sel + 4, total);        // session 0 = video
    wr32(sel + 8, p->cmd_addr);
    wr32(sel + 12, total);

    // セレクタは独立した USB 転送にする (32B ショートパケット)。
    // PC / 実験スケッチで実証済みのワイヤ形式に合わせる
    if (usb_disp_hal_bulk_write(d->hal, sel, 32) != 32) return false;
    if (!usb_disp_hal_bulk_split(d->hal)) return false;
    if (usb_disp_hal_bulk_write(d->hal, vh, 48) != 48) return false;
    if (usb_disp_hal_bulk_write(d->hal, p->jout, jlen) != jlen) return false;
    if (usb_disp_hal_bulk_write(d->hal, pad, 1024) != 1024) return false;

    p->cmd_addr += step;
    p->frames++;
    return true;
}

// ---------------------------------------------------------------
// prot ops
// ---------------------------------------------------------------

static bool t6_match(uint16_t vid, uint16_t pid) {
    if (vid == 0x0711 && (pid & 0xFFE0) == 0x5600) return true;  // MCT
    if (vid == 0x19FF && (pid & 0xFFE0) == 0x5600) return true;  // Insignia?
    if (vid == 0x03F0 && (pid == 0x0182 || pid == 0x0788)) return true; // HP?
    return false;
}

static bool t6_attach(usb_disp_t *d) {
    t6_priv_t *p = t6p(d);

    // VRAM サイズ → アドレス計画 (triggerdm 1出力ドングル流)
    uint8_t b1 = 0;
    uint16_t actual = 0;
    if (!t6_vin(d, 0x88, 0, 0, &b1, 1, &actual) || actual != 1 || b1 < 16) {
        usb_disp_log("[T6] VRAM query failed");
        return false;
    }
    p->ram_mb = b1;
    p->fb_slot[0] = (uint32_t)(p->ram_mb - 12) * USB_DISP_T6_MB;
    p->fb_slot[1] = (uint32_t)(p->ram_mb - 8) * USB_DISP_T6_MB;
    p->fb_slot[2] = (uint32_t)(p->ram_mb - 4) * USB_DISP_T6_MB;
    p->cmd_addr = 0;
    p->cmd_limit = p->fb_slot[0];
    p->frames = 0;

    b1 = 0;
    t6_vin(d, 0x87, 0, 0, &b1, 1, NULL);
    usb_disp_log("[T6] VRAM=%uMB connector=%u", p->ram_mb, b1);

    // モード表 (32B × N)。オフセットは wIndex 指定なので 256B ずつ読む
    uint8_t cnt4[4] = {0};
    t6_vin(d, 0x84, 0, 0, cnt4, 4, NULL);
    uint16_t nmodes = (uint16_t)(cnt4[0] | (cnt4[1] << 8));
    if (nmodes == 0 || nmodes > USB_DISP_T6_MAX_MODES)
        nmodes = USB_DISP_T6_MAX_MODES;
    uint16_t mlen = 0;
    for (uint16_t off = 0; off < nmodes * 32; off += 256) {
        uint16_t want = (uint16_t)(nmodes * 32 - off);
        if (want > 256) want = 256;
        actual = 0;
        if (!t6_vin(d, 0x89, 0, off, (uint8_t *)p->modes + off, want,
                    &actual) || actual == 0)
            break;
        mlen = (uint16_t)(off + actual);
        if (actual < want) break;
    }
    p->nmodes = (uint8_t)(mlen / 32);

    // max_area = モード表の最大解像度
    uint32_t max_area = 0;
    for (uint8_t i = 0; i < p->nmodes; i++) {
        uint32_t a = (uint32_t)rd16(p->modes[i] + 8) * rd16(p->modes[i] + 16);
        if (a > max_area) max_area = a;
    }
    d->chip = USB_DISP_CHIP_T6;
    d->max_area = max_area;
    usb_disp_log("[T6] %u modes, max_area=%lu px", p->nmodes,
                 (unsigned long)max_area);
#if USB_DISP_PORT_ESP32
    // T6 はフルフレーム FB + JPEG 出力バッファが必須
    // PSRAM 無効ビルド (P4 のボード設定 PSRAM: Disabled) では確保できず
    // 表示が出ないので、原因が分かるようにここで明示しておく
    if (heap_caps_get_total_size(MALLOC_CAP_SPIRAM) == 0) {
        usb_disp_log("[T6] warning: PSRAM not available. Frame buffer "
                     "alloc will fail - enable board option PSRAM");
    }
#endif
    p->alloc_fail_cnt = 0;
    return p->nmodes > 0;
}

static void t6_detach(usb_disp_t *d) {
    t6_priv_t *p = t6p(d);
    p->dirty = false;
    // FB/エンコーダは保持 (再接続で再利用。解像度が変われば realloc)
}

static uint16_t t6_read_edid(usb_disp_t *d, uint16_t offset, uint8_t *buf,
                             uint16_t len) {
    // 0x80: 128B ブロック読み (wValue = バイトオフセット)
    uint16_t got = 0;
    while (got < len) {
        uint16_t want = (uint16_t)(len - got);
        if (want > 128) want = 128;
        uint16_t actual = 0;
        if (!t6_vin(d, 0x80, (uint16_t)(offset + got), 0, buf + got, want,
                    &actual) || actual == 0)
            break;
        got = (uint16_t)(got + actual);
        if (actual < want) break;
    }
    return got;
}

// モード表から W/H/Hz の一致エントリを探す
static const uint8_t *t6_find_mode(t6_priv_t *p, uint16_t w, uint16_t h,
                                   uint16_t hz) {
    for (uint8_t i = 0; i < p->nmodes; i++) {
        const uint8_t *m = p->modes[i];
        if (rd16(m + 8) == w && rd16(m + 16) == h && rd16(m + 4) == hz)
            return m;
    }
    return NULL;
}

static bool t6_set_mode(usb_disp_t *d, const usb_disp_mode_t *m) {
    t6_priv_t *p = t6p(d);
    // リフレッシュレートをタイミングから概算 (内蔵テーブルは 60Hz)
    uint32_t htot = (uint32_t)m->width + m->hfp + m->hsync + m->hbp;
    uint32_t vtot = (uint32_t)m->height + m->vfp + m->vsync + m->vbp;
    uint16_t hz = (uint16_t)(((uint64_t)m->pclk_khz * 1000 +
                              htot * vtot / 2) /
                             ((uint64_t)htot * vtot));
    const uint8_t *entry = t6_find_mode(p, m->width, m->height, hz);
    if (!entry && hz != 60) entry = t6_find_mode(p, m->width, m->height, 60);
    if (!entry) {
        usb_disp_log("[T6] %ux%u@%u not in chip mode table", m->width,
                     m->height, hz);
        return false;
    }
#if USB_DISP_PORT_ESP32
    p->m24 = d->depth24;
    p->bpp = (uint8_t)(p->m24 ? 3 : 2);
#else
    p->m24 = true;               // PC ソフトエンコーダの FB は常に RGB888
    p->bpp = 3;
#endif
    if (!t6_alloc_bufs(d, p, m->width, m->height)) return false;

    uint8_t mode[32];
    memcpy(mode, entry, 32);  // チップのテーブルエントリをそのまま echo
    if (!t6_vout(d, 0x12, 0, 0, mode, 32)) return false;
    usb_disp_prot_sleep_ms(50);
    t6_vout(d, 0x31, 0, 0, NULL, 0);   // SOFTWARE_READY
    t6_vout(d, 0x03, 0, 1, NULL, 0);   // 出力 ON
    p->w = m->width;
    p->h = m->height;
    p->frames = 0;
    p->cmd_addr = 0;
    p->dirty = true;  // 黒 FB を初回 flush で送る

#if USB_DISP_PORT_ESP32
    if (!p->enc) {
        jpeg_encode_engine_cfg_t ecfg = {};
        ecfg.intr_priority = 0;
        ecfg.timeout_ms = 1000;
        if (jpeg_new_encoder_engine(&ecfg, &p->enc) != 0) {
            usb_disp_log("[T6] HW JPEG encoder init failed");
            p->enc = NULL;
            return false;
        }
    }
#endif
    return true;
}

// 矩形更新: FB へ書き込むだけ (送信は flush)
static bool t6_update(usb_disp_t *d, uint16_t x, uint16_t y, uint16_t w,
                      uint16_t h, const uint16_t *px, uint32_t stride_px) {
    t6_priv_t *p = t6p(d);
    if (!p->fb || p->w == 0) return false;
    for (uint16_t row = 0; row < h; row++) {
        const uint16_t *src = stride_px ? px + (uint32_t)row * stride_px : px;
#if USB_DISP_PORT_ESP32
        if (p->m24) {
            // 24bit マスタ: 565 を B,G,R へ展開
            // (P4 HW エンコーダの RGB888 入力はメモリ順 B,G,R)
            uint8_t *dst = p->fb + ((uint32_t)(y + row) * p->w + x) * 3;
            for (uint16_t i = 0; i < w; i++) {
                uint16_t v = src[i];
                dst[i * 3 + 0] = (uint8_t)((v & 0x1F) * 255 / 31);          // B
                dst[i * 3 + 1] = (uint8_t)(((v >> 5) & 0x3F) * 255 / 63);   // G
                dst[i * 3 + 2] = (uint8_t)(((v >> 11) & 0x1F) * 255 / 31);  // R
            }
        } else {
            // RGB565 のまま (HW エンコーダ直接入力)
            memcpy(p->fb + ((uint32_t)(y + row) * p->w + x) * 2, src,
                   (size_t)w * 2);
        }
#else
        // PC: RGB888 へ変換して保持 (ソフトエンコーダ入力)
        uint8_t *dst = p->fb + ((uint32_t)(y + row) * p->w + x) * 3;
        for (uint16_t i = 0; i < w; i++) {
            uint16_t v = src[i];
            dst[i * 3 + 0] = (uint8_t)(((v >> 11) & 0x1F) * 255 / 31);
            dst[i * 3 + 1] = (uint8_t)(((v >> 5) & 0x3F) * 255 / 63);
            dst[i * 3 + 2] = (uint8_t)((v & 0x1F) * 255 / 31);
        }
#endif
    }
    p->dirty = true;
    return true;
}

// 矩形更新 (RGB888, 入力 B,G,R)。
// ESP32-P4: HW エンコーダの入力も B,G,R → そのままコピー
// PC: ソフトエンコーダは R,G,B → 入れ替えて書く
static bool t6_update888(usb_disp_t *d, uint16_t x, uint16_t y, uint16_t w,
                         uint16_t h, const uint8_t *px, uint32_t stride_px) {
    t6_priv_t *p = t6p(d);
    if (!p->fb || p->w == 0 || !p->m24) return false;
    for (uint16_t row = 0; row < h; row++) {
        const uint8_t *src =
            stride_px ? px + (uint32_t)row * stride_px * 3 : px;
        uint8_t *dst = p->fb + ((uint32_t)(y + row) * p->w + x) * 3;
#if USB_DISP_PORT_ESP32
        memcpy(dst, src, (size_t)w * 3);
#else
        for (uint16_t i = 0; i < w; i++) {
            dst[i * 3 + 0] = src[i * 3 + 2];   // R
            dst[i * 3 + 1] = src[i * 3 + 1];   // G
            dst[i * 3 + 2] = src[i * 3 + 0];   // B
        }
#endif
    }
    p->dirty = true;
    return true;
}

// 画面内コピー: FB 上の memmove (送信は flush)
static bool t6_copy(usb_disp_t *d, uint16_t sx, uint16_t sy, uint16_t dx,
                    uint16_t dy, uint16_t w, uint16_t h) {
    t6_priv_t *p = t6p(d);
    if (!p->fb || p->w == 0) return false;
    uint8_t bpp = p->bpp;
    bool bottom_up = (dy > sy);
    for (uint16_t i = 0; i < h; i++) {
        uint16_t row = bottom_up ? (uint16_t)(h - 1 - i) : i;
        memmove(p->fb + ((uint32_t)(dy + row) * p->w + dx) * bpp,
                p->fb + ((uint32_t)(sy + row) * p->w + sx) * bpp,
                (size_t)w * bpp);
    }
    p->dirty = true;
    return true;
}

static bool t6_flush(usb_disp_t *d, uint32_t timeout_ms) {
    t6_priv_t *p = t6p(d);
    if (p->dirty && p->fb && p->w) {
        int32_t jlen = t6_encode(d, p);
        if (jlen <= 0) {
            usb_disp_log("[T6] encode failed (%ld)", (long)jlen);
            return false;
        }
        if (!t6_send_frame(d, p, (uint32_t)jlen)) return false;
        p->dirty = false;
    }
    return usb_disp_hal_bulk_flush(d->hal, timeout_ms);
}

static bool t6_blank(usb_disp_t *d, bool on) {
    if (!t6_vout(d, 0x03, 0, on ? 0 : 1, NULL, 0)) return false;
    if (!on) t6p(d)->dirty = true;  // 復帰時は再送
    return true;
}

const usb_disp_prot_t usb_disp_prot_t6 = {
    .name = "T6",
    .caps = USB_DISP_PROT_CAP_888,  // フルフレーム型 (シャドウ差分は非適用)
    .match = t6_match,
    .attach = t6_attach,
    .detach = t6_detach,
    .set_mode = t6_set_mode,
    .read_edid = t6_read_edid,
    .update = t6_update,
    .update888 = t6_update888,
    .copy = t6_copy,
    .flush = t6_flush,
    .blank = t6_blank,
    .poll = NULL,
};

#endif  // USB_DISP_PROT_HS

