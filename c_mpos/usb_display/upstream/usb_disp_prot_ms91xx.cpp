//
// ######################################################################
//
//    usb_disp_prot_ms91xx - MacroSilicon MS912x / MS913x プロトコル実装
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
  #include "esp_heap_caps.h"   // PSRAM 有無の診断用
#endif

#define USB_DISP_MS_KEEPALIVE_MS 2000  // MS913x: 公式ドライバと同じ2秒毎再送

typedef enum { MS_VAR_912X, MS_VAR_913X } ms_variant_t;

typedef struct {
    ms_variant_t var;
    // フレームバッファ
    uint16_t *fb565;      // マスタ (RGB565。m24 時は 3B/px B,G,R として使用)
    bool m24;             // 24bit マスタ
    uint8_t *wire;        // ワイヤ形式 (UYVY=2B/px or RGB24=3B/px)
    size_t fb_bytes, wire_bytes;
    uint16_t w, h;
    // dirty 矩形 (565→wire 変換範囲の限定用)
    bool dirty;
    uint16_t dx0, dy0, dx1, dy1;
    // MS913x
    bool first;           // 次フレームで video_enable + unmute
    uint8_t frame_index;  // 0/1 (ダブルバッファトグル)
    uint32_t last_send_ms;
    uint32_t mute_chk_ms;  // MS913x: HDMIミュート監視の前回時刻
    uint32_t frames_dbg;  // 診断ログ用フレームカウンタ
    uint16_t alloc_fail_cnt;  // FB 確保失敗の連発ログ抑制
} ms_priv_t;

static ms_priv_t s_ms[USB_DISP_MAX];
static ms_priv_t *msp(usb_disp_t *d) { return &s_ms[usb_disp_index(d)]; }

// ---------------------------------------------------------------
// 制御 (HID Feature Report 8B, EP0)
// ---------------------------------------------------------------

static bool hid_set(usb_disp_t *d, const uint8_t data[8]) {
    return usb_disp_prot_ctrl(d, 0x21, 0x09, 0x0300, 0, (void *)data, 8,
                               NULL);
}
static bool hid_get(usb_disp_t *d, uint8_t data[8]) {
    return usb_disp_prot_ctrl(d, 0xA1, 0x01, 0x0300, 0, data, 8, NULL);
}

// レジスタ読み。0..255 = 値, -1 = 転送失敗
static int16_t ms_read_reg(usb_disp_t *d, uint16_t addr) {
    uint8_t b[8] = {0xB5, (uint8_t)(addr >> 8), (uint8_t)addr, 0, 0, 0, 0, 0};
    if (!hid_set(d, b)) return -1;
    if (!hid_get(d, b)) return -1;
    return b[3];
}
static bool ms_write_reg(usb_disp_t *d, uint16_t addr, uint8_t val) {
    uint8_t b[8] = {0xB6, (uint8_t)(addr >> 8), (uint8_t)addr, val,
                    0, 0, 0, 0};
    return hid_set(d, b);
}
// MS912x: 6バイト書き (0xA6 addr data[6])
static bool ms_write6(usb_disp_t *d, uint8_t addr, const uint8_t data[6]) {
    uint8_t b[8] = {0xA6, addr, 0, 0, 0, 0, 0, 0};
    memcpy(b + 2, data, 6);
    return hid_set(d, b);
}
// MS913x: 映像コマンド (0xA6 sub_op + 6バイト)
static bool ms3_vid_cmd(usb_disp_t *d, uint8_t sub, uint8_t a, uint8_t b2,
                        uint8_t e, uint8_t f, uint8_t g, uint8_t h) {
    uint8_t b[8] = {0xA6, sub, a, b2, e, f, g, h};
    return hid_set(d, b);
}

// MS913x: HDMI TX mute (reg 0xFB07 bit1、enable でクリア)
static void ms3_screen_enable(usb_disp_t *d, bool en) {
    int16_t v = ms_read_reg(d, 0xFB07);
    if (v < 0) return;
    uint8_t nv = en ? (uint8_t)(v & ~0x02) : (uint8_t)(v | 0x02);
    ms_write_reg(d, 0xFB07, nv);
}

// ---------------------------------------------------------------
// 初期化シーケンス
// ---------------------------------------------------------------

// MS912x: rhgndf/ms912x の ms912x_set_resolution() と同一処理
static bool ms2_set_resolution(usb_disp_t *d, uint16_t w, uint16_t h,
                               uint16_t mode_id) {
    const uint16_t pixfmt = 0x2200;
    uint8_t b[6];
    memset(b, 0, 6);
    if (!ms_write6(d, 0x04, b)) return false;
    ms_read_reg(d, 0x30);
    ms_read_reg(d, 0x33);
    ms_read_reg(d, 0xC620);
    memset(b, 0, 6);
    b[0] = 0x03;
    if (!ms_write6(d, 0x03, b)) return false;
    b[0] = (uint8_t)(w >> 8); b[1] = (uint8_t)w;
    b[2] = (uint8_t)(h >> 8); b[3] = (uint8_t)h;
    b[4] = (uint8_t)(pixfmt >> 8); b[5] = (uint8_t)pixfmt;
    if (!ms_write6(d, 0x01, b)) return false;
    b[0] = (uint8_t)(mode_id >> 8); b[1] = (uint8_t)mode_id;
    b[2] = (uint8_t)(w >> 8); b[3] = (uint8_t)w;
    b[4] = (uint8_t)(h >> 8); b[5] = (uint8_t)h;
    if (!ms_write6(d, 0x02, b)) return false;
    memset(b, 0, 6);
    b[0] = 1;
    if (!ms_write6(d, 0x04, b)) return false;
    memset(b, 0, 6);
    b[0] = 1;
    if (!ms_write6(d, 0x05, b)) return false;
    return true;
}

static bool ms2_power(usb_disp_t *d, bool on) {
    uint8_t b[6] = {0, 0, 0, 0, 0, 0};
    if (on) { b[0] = 0x01; b[1] = 0x02; }
    return ms_write6(d, 0x07, b);
}

// MS913x: 公式 ms9132_event_disable / enable と同一処理
static void ms3_pipe_disable(usb_disp_t *d) {
    ms3_vid_cmd(d, 0x04, 0, 0, 0, 0, 0, 0);   // trans_enable(0)
    ms3_vid_cmd(d, 0x05, 0, 0, 0, 0, 0, 0);   // video_enable(0)
    ms3_screen_enable(d, false);
    ms3_vid_cmd(d, 0x07, 0, 2, 0, 0, 0, 0);   // power(off)
}

static void ms3_pipe_enable(usb_disp_t *d, uint16_t w, uint16_t h,
                            uint8_t vic) {
    uint8_t wh = (uint8_t)(w >> 8), wl = (uint8_t)w;
    uint8_t hh = (uint8_t)(h >> 8), hl = (uint8_t)h;
    ms3_vid_cmd(d, 0x04, 0, 0, 0, 0, 0, 0);
    ms3_vid_cmd(d, 0x05, 0, 0, 0, 0, 0, 0);
    ms3_screen_enable(d, false);
    usb_disp_prot_sleep_ms(50);
    ms3_vid_cmd(d, 0x07, 1, 2, 0, 0, 0, 0);          // power(on)
    usb_disp_prot_sleep_ms(50);
    ms3_vid_cmd(d, 0x03, 0, 0, 0, 0, 0, 0);          // trans_mode(FRAME)
    ms3_vid_cmd(d, 0x01, wh, wl, hh, hl, 0x21, 0);   // in_info (RGB888=24bpp)
    ms3_vid_cmd(d, 0x02, vic, 0x01, wh, wl, hh, hl); // out_info
    ms3_vid_cmd(d, 0x04, 1, 0, 0, 0, 0, 0);          // trans_enable(1)
    usb_disp_prot_sleep_ms(50);
    ms3_vid_cmd(d, 0x05, 0, 0, 0, 0, 0, 0);          // video は初フレームまで
    ms3_screen_enable(d, false);
}

// ---------------------------------------------------------------
// フレームバッファ / 変換
// ---------------------------------------------------------------

static void ms_free_bufs(ms_priv_t *p) {
    if (p->fb565) { free(p->fb565); p->fb565 = NULL; }
    if (p->wire) { free(p->wire); p->wire = NULL; }
    p->fb_bytes = p->wire_bytes = 0;
}

static bool ms_alloc_bufs(ms_priv_t *p, uint16_t w, uint16_t h) {
    uint8_t wbpp = (p->var == MS_VAR_913X) ? 3 : 2;
    size_t need565 = (size_t)w * h * (p->m24 ? 3 : 2);
    size_t needw = (size_t)w * h * wbpp;
    if (p->fb565 && p->fb_bytes == need565 && p->wire &&
        p->wire_bytes == needw)
        return true;
    ms_free_bufs(p);
    p->fb565 = (uint16_t *)malloc(need565);
    p->wire = (uint8_t *)malloc(needw);
    if (!p->fb565 || !p->wire) {
        // モード自動選択が候補を総当たりするため失敗は連発する → 抑制
        p->alloc_fail_cnt++;
        if (p->alloc_fail_cnt <= 8 || (p->alloc_fail_cnt & 0x3F) == 0) {
            usb_disp_log("[MS91xx] FB alloc failed (%lu KB)",
                         (unsigned long)((need565 + needw) / 1024));
        }
        ms_free_bufs(p);
        return false;
    }
    p->alloc_fail_cnt = 0;
    p->fb_bytes = need565;
    p->wire_bytes = needw;
    memset(p->fb565, 0, need565);
    // 黒: UYVY = 0x10 0x80 / RGB24 = 0
    if (p->var == MS_VAR_913X) {
        memset(p->wire, 0, needw);
    } else {
        for (size_t i = 0; i < needw; i += 2) {
            p->wire[i] = 0x80;      // U/V
            p->wire[i + 1] = 0x10;  // Y
        }
    }
    return true;
}

static void ms_dirty_add(ms_priv_t *p, uint16_t x, uint16_t y, uint16_t w,
                         uint16_t h) {
    uint16_t x1 = (uint16_t)(x + w - 1), y1 = (uint16_t)(y + h - 1);
    if (!p->dirty) {
        p->dx0 = x; p->dy0 = y; p->dx1 = x1; p->dy1 = y1;
        p->dirty = true;
    } else {
        if (x < p->dx0) p->dx0 = x;
        if (y < p->dy0) p->dy0 = y;
        if (x1 > p->dx1) p->dx1 = x1;
        if (y1 > p->dy1) p->dy1 = y1;
    }
}

// RGB565 → Y/U/V (BT.601, TV レンジ近似)
static inline void rgb565_yuv(uint16_t v, uint8_t *Y, uint8_t *U, uint8_t *V) {
    int r = ((v >> 11) & 0x1F) * 255 / 31;
    int g = ((v >> 5) & 0x3F) * 255 / 63;
    int b = (v & 0x1F) * 255 / 31;
    int y = (77 * r + 150 * g + 29 * b) >> 8;          // 0..255
    *Y = (uint8_t)(16 + y * 219 / 255);
    *U = (uint8_t)(128 + (((b - y) * 126) >> 8));
    *V = (uint8_t)(128 + (((r - y) * 160) >> 8));
}

// B,G,R 3バイト → Y/U/V (BT.601, TV レンジ近似)
static inline void rgb888_yuv(const uint8_t *px, uint8_t *Y, uint8_t *U,
                              uint8_t *V) {
    int b = px[0], g = px[1], r = px[2];
    int y = (77 * r + 150 * g + 29 * b) >> 8;
    *Y = (uint8_t)(16 + y * 219 / 255);
    *U = (uint8_t)(128 + (((b - y) * 126) >> 8));
    *V = (uint8_t)(128 + (((r - y) * 160) >> 8));
}

// dirty 領域を 565 マスタ → ワイヤ形式へ変換
static void ms_convert_dirty(ms_priv_t *p) {
    if (!p->dirty) return;
    uint16_t x0 = p->dx0, x1 = p->dx1;
    if (p->var != MS_VAR_913X) {  // UYVY はピクセルペア境界に拡張
        x0 &= (uint16_t)~1u;
        x1 |= 1;
        if (x1 >= p->w) x1 = (uint16_t)(p->w - 1);
    }
    for (uint16_t y = p->dy0; y <= p->dy1; y++) {
        if (p->m24) {
            // 24bit マスタ (B,G,R)
            const uint8_t *src8 =
                (const uint8_t *)p->fb565 + (uint32_t)y * p->w * 3;
            if (p->var == MS_VAR_913X) {
                // ワイヤも B,G,R → そのままコピー
                memcpy(p->wire + ((uint32_t)y * p->w + x0) * 3,
                       src8 + (uint32_t)x0 * 3,
                       (size_t)(x1 - x0 + 1) * 3);
            } else {
                uint8_t *dst = p->wire + ((uint32_t)y * p->w + x0) * 2;
                for (uint16_t x = x0; x <= x1; x += 2) {
                    uint8_t Y0, U0, V0, Y1, U1, V1;
                    uint16_t xb = (uint16_t)(x + 1 <= x1 ? x + 1 : x);
                    rgb888_yuv(src8 + (uint32_t)x * 3, &Y0, &U0, &V0);
                    rgb888_yuv(src8 + (uint32_t)xb * 3, &Y1, &U1, &V1);
                    *dst++ = (uint8_t)((U0 + U1) / 2);
                    *dst++ = Y0;
                    *dst++ = (uint8_t)((V0 + V1) / 2);
                    *dst++ = Y1;
                }
            }
            continue;
        }
        const uint16_t *src = p->fb565 + (uint32_t)y * p->w;
        if (p->var == MS_VAR_913X) {
            uint8_t *dst = p->wire + ((uint32_t)y * p->w + x0) * 3;
            for (uint16_t x = x0; x <= x1; x++) {
                uint16_t v = src[x];
                // ワイヤ順 B,G,R
                *dst++ = (uint8_t)((v & 0x1F) * 255 / 31);
                *dst++ = (uint8_t)(((v >> 5) & 0x3F) * 255 / 63);
                *dst++ = (uint8_t)(((v >> 11) & 0x1F) * 255 / 31);
            }
        } else {
            uint8_t *dst = p->wire + ((uint32_t)y * p->w + x0) * 2;
            for (uint16_t x = x0; x <= x1; x += 2) {
                uint8_t Y0, U0, V0, Y1, U1, V1;
                rgb565_yuv(src[x], &Y0, &U0, &V0);
                rgb565_yuv(src[x + 1 <= x1 ? x + 1 : x], &Y1, &U1, &V1);
                *dst++ = (uint8_t)((U0 + U1) / 2);
                *dst++ = Y0;
                *dst++ = (uint8_t)((V0 + V1) / 2);
                *dst++ = Y1;
            }
        }
    }
}

// ---------------------------------------------------------------
// フレーム送信
// ---------------------------------------------------------------

static bool ms_send_frame(usb_disp_t *d, ms_priv_t *p) {
    if (p->var == MS_VAR_913X) {
        // RGB24 全面 1 ストリーム + ZLP + frame_index トグル + trigger。
        // 送信が不完全でもトリガーまで必ず進める (公式ドライバと同じ流儀)。
        // 0x9133 実測: チップは TRIGGER_FRAME を受けるまでバルク受信 DMA を
        // 起こさないことがあり (-88KB の FIFO が埋まって NAK 連発)、
        // ここで諦めるとトリガーが永遠に出ずデッドロックする。
        // トリガーは EP0 経由なので詰まっていても届き、受信 DMA が起きて
        // 滞留データが流れ出す → 次フレームから正常化する
        uint32_t sent = usb_disp_hal_bulk_write(d->hal, p->wire,
                                                (uint32_t)p->wire_bytes);
        bool zok = usb_disp_hal_bulk_zlp(d->hal);  // フレーム長は 512 の倍数
        bool fok = usb_disp_hal_bulk_flush(d->hal, 5000);
        p->frame_index ^= 1;
        bool tok = ms3_vid_cmd(d, 0x00, (uint8_t)p->frame_index, 100, 0, 0,
                               0, 0);
        if (sent != p->wire_bytes || !zok || !fok) {
            usb_disp_log("[MS913x] partial frame: sent=%lu/%lu zlp=%d "
                         "flush=%d trig=%d",
                         (unsigned long)sent, (unsigned long)p->wire_bytes,
                         (int)zok, (int)fok, (int)tok);
            return false;
        }
        if (p->first) {
            bool vok = ms3_vid_cmd(d, 0x05, 1, 0, 0, 0, 0, 0);
            ms3_screen_enable(d, true);               // HDMI unmute
            p->first = false;
            usb_disp_log("[MS913x] first frame: %lu B zlp=%d trig=%d "
                         "ven=%d mute=%02X d003=%02X",
                         (unsigned long)p->wire_bytes, zok, tok, vok,
                         ms_read_reg(d, 0xFB07), ms_read_reg(d, 0xD003));
        } else if ((p->frames_dbg++ & 0x3F) == 0) {
            usb_disp_log("[MS913x] frame#%lu zlp=%d trig=%d idx=%d "
                         "mute=%02X d003=%02X",
                         (unsigned long)p->frames_dbg, zok, tok,
                         p->frame_index, ms_read_reg(d, 0xFB07),
                         ms_read_reg(d, 0xD003));
        }
    } else {
        // MS912x: [8B ヘッダ (全画面)] + UYVY + [8B 終端]
        uint8_t hdr[8], eob[8];
        hdr[0] = 0xFF; hdr[1] = 0x00;
        hdr[2] = 0;                                  // x/16
        hdr[3] = 0; hdr[4] = 0;                      // y (BE16)
        hdr[5] = (uint8_t)(p->w / 16);               // width/16
        hdr[6] = (uint8_t)(p->h >> 8); hdr[7] = (uint8_t)p->h;
        memset(eob, 0, 8);
        eob[0] = 0xFF; eob[1] = 0xC0;
        if (usb_disp_hal_bulk_write(d->hal, hdr, 8) != 8) return false;
        if (usb_disp_hal_bulk_write(d->hal, p->wire, (uint32_t)p->wire_bytes)
            != p->wire_bytes)
            return false;
        if (usb_disp_hal_bulk_write(d->hal, eob, 8) != 8) return false;
        if (!usb_disp_hal_bulk_flush(d->hal, 5000)) return false;
    }
    p->last_send_ms = usb_disp_hal_ms();
    return true;
}

// ---------------------------------------------------------------
// チップ判定
// ---------------------------------------------------------------

//  ここに並ぶ VID/PID 推測で追加することはしない
//  (誤って別物を掴むと、映像が出ないだけでなく MS913x では固着 → VBUS 物理切断が必要になる)
//
//  未知の個体を入手したときの追加手順:
//    1. その PID をここに追加して認識させる
//    2. MS913x 世代なら ms_attach の変種判定にも PID を足す
//       (RGB24 経路。足さないと MS912x 扱い = UYVY で誤動作する)
//    3. attach 時に出る chip_id=XXXX ログで世代を確認する

static bool ms_match(uint16_t vid, uint16_t pid) {
    if (vid == 0x534D && pid == 0x6021) return true;                 // MS912x
    if (vid == 0x345F && (pid == 0x9132 || pid == 0x9133)) return true;
    return false;
}

static bool ms_attach(usb_disp_t *d) {
    ms_priv_t *p = msp(d);
    // 世代の振り分け
    // 既定は MS912x で、既知の MS913x 世代の PID だけを RGB24 経路へ回す
    p->var = (d->vid == 0x345F && d->pid == 0x9133) ? MS_VAR_913X
                                                    : MS_VAR_912X;
    // 疎通確認
    // ※最初のベンダーコマンドが ZeroCD イジェクトのトリガーになる
    // (未イジェクト個体は約5秒後に再列挙 → コアが自動で再 attach)
    int16_t r30 = ms_read_reg(d, 0x30);
    if (r30 < 0) {
        usb_disp_log("[MS91xx] control probe failed");
        return false;
    }
#if USB_DISP_PORT_ESP32
    // MS91xx はフルフレーム FB + ワイヤバッファが必須
    // PSRAM 無効ビルド (P4 のボード設定 PSRAM: Disabled) では確保できず
    // 表示が出ないので、原因が分かるようにここで明示しておく
    if (heap_caps_get_total_size(MALLOC_CAP_SPIRAM) == 0) {
        usb_disp_log("[MS91xx] warning: PSRAM not available. Frame buffer "
                     "alloc will fail - enable board option PSRAM");
    }
#endif
    p->alloc_fail_cnt = 0;
    if (p->var == MS_VAR_913X) {
        int16_t hi = ms_read_reg(d, 0xFF00), lo = ms_read_reg(d, 0xFF01);
        usb_disp_log("[MS913x] chip_id=%02X%02X", hi, lo);
        d->chip = USB_DISP_CHIP_MS913X;
        d->max_area = 2073600;  // 1920x1080
    } else {
        d->chip = USB_DISP_CHIP_MS912X;
        d->max_area = 2073600;  // 1920x1080
    }
    return true;
}

static void ms_detach(usb_disp_t *d) {
    ms_priv_t *p = msp(d);
    p->dirty = false;
    // MS913x: 可能なら映像パイプを止めておく
    // (固着予防。切断後なので失敗しても無害 - hid_set が false を返すだけ)
    if (p->var == MS_VAR_913X) ms3_pipe_disable(d);
}

static uint16_t ms_read_edid(usb_disp_t *d, uint16_t offset, uint8_t *buf,
                             uint16_t len) {
    // レジスタ 0xC000 + offset を 1 バイトずつ
    for (uint16_t i = 0; i < len; i++) {
        int16_t v = ms_read_reg(d, (uint16_t)(0xC000 + offset + i));
        if (v < 0) return i;
        buf[i] = (uint8_t)v;
    }
    return len;
}

// 既知モード (MS912x の mode_id / MS913x の vic)
// MS913x の vic は CEA-861 ではなく MS 独自番号 (公式ドライバ g_support_mode)
// MS912x の mode_id 上位バイトと同じ体系 (0x8100 -> 129 / 0x4F00 -> 79)
static const struct { uint16_t w, h, mode_id; uint8_t vic; } k_ms_modes[] = {
    { 1920, 1080, 0x8100, 129 },
    { 1280,  720, 0x4F00, 79 },
};

static bool ms_set_mode(usb_disp_t *d, const usb_disp_mode_t *m) {
    ms_priv_t *p = msp(d);
    int8_t mi = -1;
    for (uint8_t i = 0; i < sizeof(k_ms_modes) / sizeof(k_ms_modes[0]); i++) {
        if (k_ms_modes[i].w == m->width && k_ms_modes[i].h == m->height) {
            mi = (int8_t)i;
            break;
        }
    }
    if (mi < 0) {
        usb_disp_log("[MS91xx] %ux%u not in known mode list", m->width,
                     m->height);
        return false;
    }
    p->m24 = d->depth24;
    if (!ms_alloc_bufs(p, m->width, m->height)) {
        if (p->m24) {          // メモリ不足なら 565 マスタで再試行
            p->m24 = false;
            d->depth24 = false;
            if (!ms_alloc_bufs(p, m->width, m->height)) return false;
        } else {
            return false;
        }
    }
    p->w = m->width;
    p->h = m->height;

    if (p->var == MS_VAR_913X) {
        ms3_pipe_disable(d);
        usb_disp_prot_sleep_ms(200);
        ms3_pipe_enable(d, p->w, p->h, k_ms_modes[mi].vic);
        int16_t fsw = ms_read_reg(d, 0xD003);
        p->frame_index = (fsw > 0) ? 1 : 0;
        // 先行トリガー: バルク受信 DMA を起こす。まだミュート中なので画面には出ない。
        //  (ms_send_frame の 0x9133 実測コメント参照)
        // これが無いと初回フレームが FIFO 分 (-88KB) で詰まり、
        // トリガー到達までの数秒間デッドロック状態になる。
        // コールドスタートではこの先行トリガーも空振りすることがあるが、
        // その場合も ms_send_frame の partial 経路 (詰まってもトリガーを送る) 
        // が数秒で受信 DMA を起こし、次のフレームから正常化する
        usb_disp_prot_sleep_ms(200);
        ms3_vid_cmd(d, 0x00, (uint8_t)p->frame_index, 100, 0, 0, 0, 0);
        p->first = true;
    } else {
        ms2_power(d, false);
        usb_disp_prot_sleep_ms(100);
        if (!ms2_power(d, true)) return false;
        if (!ms2_set_resolution(d, p->w, p->h, k_ms_modes[mi].mode_id))
            return false;
    }
    // 黒 FB を初回 flush で送る (全面 dirty)
    p->dirty = false;
    ms_dirty_add(p, 0, 0, p->w, p->h);
    return true;
}

static bool ms_update(usb_disp_t *d, uint16_t x, uint16_t y, uint16_t w,
                      uint16_t h, const uint16_t *px, uint32_t stride_px) {
    ms_priv_t *p = msp(d);
    if (!p->fb565 || p->w == 0) return false;
    for (uint16_t row = 0; row < h; row++) {
        const uint16_t *src = stride_px ? px + (uint32_t)row * stride_px : px;
        if (p->m24) {
            uint8_t *dst =
                (uint8_t *)p->fb565 + ((uint32_t)(y + row) * p->w + x) * 3;
            for (uint16_t i = 0; i < w; i++) {
                uint16_t v = src[i];
                dst[i * 3 + 0] = (uint8_t)((v & 0x1F) * 255 / 31);          // B
                dst[i * 3 + 1] = (uint8_t)(((v >> 5) & 0x3F) * 255 / 63);   // G
                dst[i * 3 + 2] = (uint8_t)(((v >> 11) & 0x1F) * 255 / 31);  // R
            }
        } else {
            memcpy(p->fb565 + (uint32_t)(y + row) * p->w + x, src,
                   (size_t)w * 2);
        }
    }
    ms_dirty_add(p, x, y, w, h);
    return true;
}

// 矩形更新 (RGB888, B,G,R)。24bit マスタへそのまま書く
static bool ms_update888(usb_disp_t *d, uint16_t x, uint16_t y, uint16_t w,
                         uint16_t h, const uint8_t *px, uint32_t stride_px) {
    ms_priv_t *p = msp(d);
    if (!p->fb565 || p->w == 0 || !p->m24) return false;
    for (uint16_t row = 0; row < h; row++) {
        const uint8_t *src =
            stride_px ? px + (uint32_t)row * stride_px * 3 : px;
        memcpy((uint8_t *)p->fb565 + ((uint32_t)(y + row) * p->w + x) * 3,
               src, (size_t)w * 3);
    }
    ms_dirty_add(p, x, y, w, h);
    return true;
}

static bool ms_copy(usb_disp_t *d, uint16_t sx, uint16_t sy, uint16_t dx,
                    uint16_t dy, uint16_t w, uint16_t h) {
    ms_priv_t *p = msp(d);
    if (!p->fb565 || p->w == 0) return false;
    bool bottom_up = (dy > sy);
    uint8_t bpp = (uint8_t)(p->m24 ? 3 : 2);
    uint8_t *fb = (uint8_t *)p->fb565;
    for (uint16_t i = 0; i < h; i++) {
        uint16_t row = bottom_up ? (uint16_t)(h - 1 - i) : i;
        memmove(fb + ((uint32_t)(dy + row) * p->w + dx) * bpp,
                fb + ((uint32_t)(sy + row) * p->w + sx) * bpp,
                (size_t)w * bpp);
    }
    ms_dirty_add(p, dx, dy, w, h);
    return true;
}

static bool ms_flush(usb_disp_t *d, uint32_t timeout_ms) {
    ms_priv_t *p = msp(d);
    if (p->dirty && p->fb565 && p->w) {
        ms_convert_dirty(p);
        p->dirty = false;
        if (!ms_send_frame(d, p)) return false;
    }
    return usb_disp_hal_bulk_flush(d->hal, timeout_ms);
}

static bool ms_blank(usb_disp_t *d, bool on) {
    ms_priv_t *p = msp(d);
    if (p->var == MS_VAR_913X) {
        if (on) {
            ms3_vid_cmd(d, 0x05, 0, 0, 0, 0, 0, 0);
            ms3_screen_enable(d, false);
        } else {
            p->first = true;  // 次フレームで video_enable + unmute
            ms_dirty_add(p, 0, 0, p->w, p->h);
        }
    } else {
        if (on) {
            ms2_power(d, false);
        } else {
            // 復帰はモード再設定が必要 → 全面再送
            usb_disp_mode_t m;
            memset(&m, 0, sizeof(m));
            m.width = p->w;
            m.height = p->h;
            m.pclk_khz = 60u * ((uint32_t)p->w + 160) * (p->h + 40) / 1000;
            if (!ms_set_mode(d, &m)) return false;
        }
    }
    return true;
}

// MS913x キープアライブ: 最終送信から 12 秒でブランクする →
// 2秒毎にワイヤ FB をそのまま再送する (公式ドライバの周期再送と同じ)
static void ms_poll(usb_disp_t *d) {
    ms_priv_t *p = msp(d);
    if (p->var != MS_VAR_913X || !d->ready || !p->wire || p->w == 0) return;
    uint32_t now = usb_disp_hal_ms();
    if (now - p->last_send_ms >= USB_DISP_MS_KEEPALIVE_MS) {
        ms_send_frame(d, p);
    }
    // HDMI側の抜き差し等で出力がミュートされるとフレーム再送だけでは黒のまま復帰しない。
    // ミュートレジスタ (0xFB07 bit1) を監視し、立っていたら video_enable + unmute を再発行する。
    // 注意: 外乱の種類によっては FB07=00 (非ミュート)・フレーム消費正常のまま
    // 出力だけ黒になる状態があり、これはレジスタから検出できない
    // その場合はアプリから usb_disp_set_mode / set_auto_mode の
    // 再実行 (パイプ再初期化) で復旧する - DL の HPD ブランクと同じ作法
    if (now - p->mute_chk_ms >= USB_DISP_MS_KEEPALIVE_MS) {
        p->mute_chk_ms = now;
        int16_t mv = ms_read_reg(d, 0xFB07);
        if (mv >= 0 && (mv & 0x02)) {
            usb_disp_log("[MS913x] HDMI muted (FB07=%02X) - re-enabling", mv);
            ms3_vid_cmd(d, 0x05, 1, 0, 0, 0, 0, 0);     // video_enable(1)
            ms3_screen_enable(d, true);                 // unmute
            ms_send_frame(d, p);                        // フレームも即再送
        }
    }
}

const usb_disp_prot_t usb_disp_prot_ms91xx = {
    .name = "MS91xx",
    .caps = USB_DISP_PROT_CAP_888,  // フルフレーム型
    .match = ms_match,
    .attach = ms_attach,
    .detach = ms_detach,
    .set_mode = ms_set_mode,
    .read_edid = ms_read_edid,
    .update = ms_update,
    .update888 = ms_update888,
    .copy = ms_copy,
    .flush = ms_flush,
    .blank = ms_blank,
    .poll = ms_poll,
};

#endif  // USB_DISP_PROT_HS

