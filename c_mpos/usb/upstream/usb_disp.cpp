//
// ######################################################################
//
//    usb_disp - USB Display Driver Core
//
//    プロトコル非依存のコア: ライフサイクル・接続ステート・モード管理
//    (内蔵タイミングテーブル / CVT-RB / EDID パース)・クリッピング・
//    シャドウFB差分更新。チップ別プロトコルは usb_disp_prot_*.cpp:
//
//      usb_disp_prot_dl-1xx.cpp  : DisplayLink DL-1x0/1x5
//      usb_disp_prot_t6.cpp      : MCT Trigger 6
//      usb_disp_prot_ms91xx.cpp  : MacroSilicon MS912x/MS913x
//
//    Copyright (C) 2026
//      Hideto Kikuchi / PJラボ (@pcjpnet) - https://pc-jp.net/
//
// ######################################################################
//

#include <stdarg.h>
#include <stdio.h>
#include <string.h>

#if defined(ARDUINO)
#include <Arduino.h>   // 既定ログの Serial 出力用
#endif

#include "usb_disp.h"
#include "usb_disp_hal.h"
#include "usb_disp_prot.h"
#include "usb_disp_model.h"   // 既知製品の VID/PID 型番テーブル

// ---------------------------------------------------------------
// ビデオモードテーブル (VESA DMT / CEA, 60Hz)
//   タイミングは Linux drm_dmt_modes[] (VESA DMT 規格値) より
//   ※面積降順に並べること (auto mode のフォールバックが先頭から試す)
// ---------------------------------------------------------------

static const usb_disp_mode_t s_modes[] = {
    //  W     H     pclk    hfp hsw  hbp  vfp vsw vbp
    { 2048, 1152, 162000,  26,  80,  96,  1, 3, 44 },  // DMT 0x54 RB
    { 1920, 1200, 154000,  48,  32,  80,  3, 6, 26 },  // DMT 0x44 RB
    { 1920, 1080, 148500,  88,  44, 148,  4, 5, 36 },  // CEA-861 1080p60
    { 1600, 1200, 162000,  64, 192, 304,  1, 3, 46 },  // DMT 0x33
    { 1680, 1050, 119000,  48,  32,  80,  3, 6, 21 },  // DMT 0x39 RB
    { 1400, 1050, 101000,  48,  32,  80,  3, 4, 23 },  // DMT 0x29 RB
    { 1600,  900, 108000,  24,  80,  96,  1, 3, 96 },  // DMT 0x53 RB
    { 1280, 1024, 108000,  48, 112, 248,  1, 3, 38 },  // DMT 0x23
    { 1440,  900,  88750,  48,  32,  80,  3, 6, 17 },  // DMT 0x2E RB
    { 1280,  960, 108000,  96, 112, 312,  1, 3, 36 },  // DMT 0x20
    { 1366,  768,  85500,  70, 143, 213,  3, 3, 24 },  // DMT 0x56
    { 1280,  800,  71000,  48,  32,  80,  3, 6, 14 },  // DMT 0x1B RB
    { 1280,  720,  74250, 110,  40, 220,  5, 5, 20 },  // CEA-861 720p60
    { 1024,  768,  65000,  24, 136, 160,  3, 6, 29 },  // DMT 0x10
    {  800,  600,  40000,  40, 128,  88,  1, 4, 23 },  // DMT 0x09
    {  640,  480,  25175,  16,  96,  48, 10, 2, 33 },  // DMT 0x04
};

#define USB_DISP_MODE_COUNT \
    ((uint8_t)(sizeof(s_modes) / sizeof(s_modes[0])))

static usb_disp_t s_disp[USB_DISP_MAX];
static uint8_t s_ndisp = 0;

static void shadow_setup(usb_disp_t *d);
static uint32_t auto_max_area(usb_disp_t *d);

#define USB_DISP_UNSUPPORTED_RETRY_MS 30000  // 非対応デバイスの周期再試行間隔
#define USB_DISP_MODE_SETUP_WAIT_MS   2500   // EDID/モード設定を粘る時間
#define USB_DISP_MODE_SETUP_RETRY_MS  300    // モード設定の試行間隔
#define USB_DISP_EDID_RECHECK_MS      3000   // READY 後の EDID 遅延再チェック間隔
#define USB_DISP_EDID_RECHECK_MAX_MS  30000  // 打ち切り

// fill 用の共有ラインバッファ
static uint16_t s_fill_line[USB_DISP_MAX_WIDTH];

// 24bit カラー用の行バッファと変換
static uint8_t s_line888[USB_DISP_MAX_WIDTH * 3];
static uint16_t s_line565[USB_DISP_MAX_WIDTH];

// B,G,R 3バイト → RGB565
static inline uint16_t px_888_565(const uint8_t *p) {
    return (uint16_t)(((p[2] & 0xF8) << 8) | ((p[1] & 0xFC) << 3) |
                      (p[0] >> 3));
}
static void row_888_to_565(const uint8_t *src, uint16_t *dst, uint16_t w) {
    for (uint16_t i = 0; i < w; i++, src += 3) dst[i] = px_888_565(src);
}
// RGB565 → B,G,R (ビット複製で 8bit へ展開)
static void row_565_to_888(const uint16_t *src, uint8_t *dst, uint16_t w) {
    for (uint16_t i = 0; i < w; i++) {
        uint16_t c = src[i];
        uint8_t r5 = (uint8_t)(c >> 11);
        uint8_t g6 = (uint8_t)((c >> 5) & 0x3F);
        uint8_t b5 = (uint8_t)(c & 0x1F);
        *dst++ = (uint8_t)((b5 << 3) | (b5 >> 2));
        *dst++ = (uint8_t)((g6 << 2) | (g6 >> 4));
        *dst++ = (uint8_t)((r5 << 3) | (r5 >> 2));
    }
}

// ---- ログ ----
// 既定実装 (weak, アプリの usb_disp_log 定義で完全に差し替え可)
//   - 既定では何も出さない
//   - usb_disp_set_log(true) で Arduino は Serial へ出力するようになる
//     (Arduino 以外の既定実装は出力先が無いので set_log しても出ない。
//      pico-sdk / ESP-IDF / PC では usb_disp_log を定義して使う)
static bool s_log_on = false;

void usb_disp_set_log(bool on) { s_log_on = on; }

__attribute__((weak)) void usb_disp_log(const char *fmt, ...) {
#if defined(ARDUINO)
    if (!s_log_on) return;
    char buf[192];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(buf, sizeof(buf), fmt, ap);
    va_end(ap);
    Serial.println(buf);
#else
    (void)s_log_on;
    (void)fmt;
#endif
}

// ---------------------------------------------------------------
// プロトコルテーブル
// ---------------------------------------------------------------

static const usb_disp_prot_t *const k_prots[] = {
    &usb_disp_prot_dl1xx,
#if USB_DISP_PROT_HS
    &usb_disp_prot_t6,
    &usb_disp_prot_ms91xx,
#endif
};
#define USB_DISP_PROT_COUNT \
    ((uint8_t)(sizeof(k_prots) / sizeof(k_prots[0])))

const usb_disp_prot_t *usb_disp_prot_find(uint16_t vid, uint16_t pid) {
    for (uint8_t i = 0; i < USB_DISP_PROT_COUNT; i++) {
        if (k_prots[i]->match(vid, pid)) return k_prots[i];
    }
    return NULL;
}

// HAL のデバイス走査用
bool usb_disp_supported_device(uint16_t vid, uint16_t pid) {
    return usb_disp_prot_find(vid, pid) != NULL;
}

// プロトコル実装向け共有ヘルパ: コントロール転送
bool usb_disp_prot_ctrl(usb_disp_t *d, uint8_t bmRequestType,
                         uint8_t bRequest, uint16_t wValue, uint16_t wIndex,
                         void *data, uint16_t wLength, uint16_t *actual) {
    uint8_t setup[8];
    setup[0] = bmRequestType;
    setup[1] = bRequest;
    setup[2] = (uint8_t)wValue;
    setup[3] = (uint8_t)(wValue >> 8);
    setup[4] = (uint8_t)wIndex;
    setup[5] = (uint8_t)(wIndex >> 8);
    setup[6] = (uint8_t)wLength;
    setup[7] = (uint8_t)(wLength >> 8);
    return usb_disp_hal_ctrl(d->hal, setup, data, actual);
}

// ---------------------------------------------------------------
// チップ情報
// ---------------------------------------------------------------

usb_disp_chip_t usb_disp_chip(usb_disp_t *d) { return d->chip; }
uint32_t usb_disp_max_area(usb_disp_t *d) { return d->max_area; }

const char *usb_disp_chip_name(usb_disp_t *d) {
    switch (d->chip) {
    case USB_DISP_CHIP_DL120:  return "DL-120";
    case USB_DISP_CHIP_DL160:  return "DL-160";
    case USB_DISP_CHIP_DL1X0:  return "DL-1x0";
    case USB_DISP_CHIP_DL115:  return "DL-115";
    case USB_DISP_CHIP_DL125:  return "DL-125";
    case USB_DISP_CHIP_DL165:  return "DL-165";
    case USB_DISP_CHIP_DL195:  return "DL-195";
    case USB_DISP_CHIP_DL1X5:  return "DL-1x5";
    case USB_DISP_CHIP_T6:     return "T6";
    case USB_DISP_CHIP_MS912X: return "MS912x";
    case USB_DISP_CHIP_MS913X: return "MS913x";
    default:
        return d->prot ? d->prot->name : "???";
    }
}

uint16_t usb_disp_read_edid(usb_disp_t *d, uint8_t *buf, uint16_t len) {
    if (!d->prot || !d->prot->read_edid) return 0;
    return d->prot->read_edid(d, 0, buf, len);
}

uint16_t usb_disp_read_edid_at(usb_disp_t *d, uint16_t offset, uint8_t *buf,
                               uint16_t len) {
    if (!d->prot || !d->prot->read_edid) return 0;
    return d->prot->read_edid(d, offset, buf, len);
}

// ---------------------------------------------------------------
// 製品型番判別 (VID/PID 照合)
// ---------------------------------------------------------------

const char *usb_disp_model_name(uint16_t vid, uint16_t pid) {
    for (uint8_t i = 0; i < sizeof(usb_disp_models) /
                                sizeof(usb_disp_models[0]); i++) {
        if (usb_disp_models[i].vid == vid && usb_disp_models[i].pid == pid)
            return usb_disp_models[i].name;
    }
    return NULL;
}

const char *usb_disp_model(usb_disp_t *d) {
    if (!d || d->vid == 0) return NULL;
    return usb_disp_model_name(d->vid, d->pid);
}

// DL-1xx プロトコル用: 実チップ確定リスト (usb_disp_model.h) を引く
usb_disp_chip_t usb_disp_model_chip(uint16_t vid, uint16_t pid) {
    for (uint8_t i = 0; i < sizeof(usb_disp_model_chips) /
                                sizeof(usb_disp_model_chips[0]); i++) {
        if (usb_disp_model_chips[i].vid == vid &&
            usb_disp_model_chips[i].pid == pid)
            return usb_disp_model_chips[i].chip;
    }
    return USB_DISP_CHIP_UNKNOWN;
}

// ---------------------------------------------------------------
// モード選択 (プロトコル非依存)
// ---------------------------------------------------------------

// モードがチップ上限・ドライバ制限内に収まるか (実測 max_area のみ強制)
// アプリ/CLI の明示指定はここを通る = SKU 不明時は制限しない
static bool mode_fits(usb_disp_t *d, uint16_t width, uint16_t height) {
    if (width == 0 || height == 0 || width > USB_DISP_MAX_WIDTH) return false;
    if (d->max_area && (uint32_t)width * height > d->max_area) return false;
    return true;
}

// 自動選択用: DL の SKU 不明個体は世代内の最小 SKU 相当で保守的に制限
// (上限超過モードを勝手に選ぶと黒画面になるため)。明示指定は対象外
static uint32_t auto_max_area(usb_disp_t *d) {
    if (d->max_area) return d->max_area;
    if (d->chip == USB_DISP_CHIP_DL1X0) return 1470000;   // DL-120 相当
    if (d->chip == USB_DISP_CHIP_DL1X5) return 1310720;   // DL-115 相当
    return 0;  // 世代も不明なら制限なし (従来動作)
}

static bool mode_fits_auto(usb_disp_t *d, uint16_t width, uint16_t height) {
    uint32_t cap = auto_max_area(d);
    if (!mode_fits(d, width, height)) return false;
    if (cap && (uint32_t)width * height > cap) return false;
    return true;
}

// CVT-RB (VESA Coordinated Video Timings, Reduced Blanking v1) で
// 任意解像度のタイミングを生成する
static bool cvt_rb_mode(uint16_t width, uint16_t height, uint8_t hz,
                        usb_disp_mode_t *out) {
    if (!width || !height || !hz) return false;
    uint16_t vsync;
    if ((uint32_t)width * 3 == (uint32_t)height * 4)        vsync = 4;
    else if ((uint32_t)width * 9 == (uint32_t)height * 16)  vsync = 5;
    else if ((uint32_t)width * 10 == (uint32_t)height * 16) vsync = 6;
    else if ((uint32_t)width * 4 == (uint32_t)height * 5)   vsync = 7;
    else                                                    vsync = 10;

    uint32_t frame_ns = 1000000000u / hz;
    if (frame_ns <= 460000u) return false;
    uint32_t h_period_ns = (frame_ns - 460000u) / height;
    if (h_period_ns == 0) return false;
    uint32_t vbi = 460000u / h_period_ns + 1;
    uint32_t min_vbi = 3u + vsync + 6u;
    if (vbi < min_vbi) vbi = min_vbi;

    uint32_t h_total = (uint32_t)width + 160u;
    uint32_t v_total = (uint32_t)height + vbi;
    uint32_t pclk_khz = (uint32_t)((uint64_t)h_total * v_total * hz / 1000u);
    if (pclk_khz / 5 > 0xFFFF) return false;  // DL レジスタ 0x1B の制約

    out->width = width;
    out->height = height;
    out->pclk_khz = pclk_khz;
    out->hfp = 48; out->hsync = 32; out->hbp = 80;
    out->vfp = 3;  out->vsync = vsync;
    out->vbp = (uint16_t)(vbi - 3 - vsync);
    return true;
}

bool usb_disp_set_mode_ex(usb_disp_t *d, const usb_disp_mode_t *m) {
    if (!d->prot) return false;
    if (!mode_fits(d, m->width, m->height)) {
        usb_disp_log("[%s] mode %ux%u exceeds chip limit (max_area=%lu)",
                     d->prot->name, m->width, m->height,
                     (unsigned long)d->max_area);
        return false;
    }
    // 実効カラー深度を決定してからモードを組む
    // プロトコルは d->depth24 を見て構成し対応できなければ false に戻してよい
    d->depth24 = d->depth24_want && d->prot->update888 &&
                 (d->prot->caps & USB_DISP_PROT_CAP_888) != 0;
    if (!d->prot->set_mode(d, m)) return false;
    if (d->depth24_want && !d->depth24)
        usb_disp_log("[%s] 24bit not supported here - using 16bit",
                     d->prot->name);
    d->width = m->width;
    d->height = m->height;
    d->cur_mode = *m;   // usb_disp_current_mode / refresh_hz 用に保持
    shadow_setup(d);  // 解像度が変わるので再確保・再同期
    return true;
}

bool usb_disp_set_depth(usb_disp_t *d, uint8_t bits) {
    if (!d || (bits != 16 && bits != 24)) return false;
    bool want = (bits == 24);
    d->depth24_want = want;
    d->cfg.depth24 = want;
    if (d->ready && d->cur_mode.width) {
        usb_disp_mode_t m = d->cur_mode;   // 同一モードで深度だけ切替
        if (!usb_disp_set_mode_ex(d, &m)) return false;
        return d->depth24 == want;
    }
    return true;   // 未接続: 接続時のモード設定で反映される
}

uint8_t usb_disp_depth(usb_disp_t *d) { return (d && d->depth24) ? 24 : 16; }

bool usb_disp_current_mode(usb_disp_t *d, usb_disp_mode_t *out) {
    if (!d || d->cur_mode.width == 0) return false;
    if (out) *out = d->cur_mode;
    return true;
}

uint16_t usb_disp_refresh_hz(usb_disp_t *d) {
    if (!d || d->cur_mode.width == 0 || d->cur_mode.pclk_khz == 0) return 0;
    const usb_disp_mode_t *m = &d->cur_mode;
    uint32_t htotal = (uint32_t)m->width + m->hfp + m->hsync + m->hbp;
    uint32_t vtotal = (uint32_t)m->height + m->vfp + m->vsync + m->vbp;
    if (htotal == 0 || vtotal == 0) return 0;
    uint64_t px = (uint64_t)htotal * vtotal;
    return (uint16_t)(((uint64_t)m->pclk_khz * 1000 + px / 2) / px);
}

bool usb_disp_set_mode_hz(usb_disp_t *d, uint16_t width, uint16_t height,
                          uint8_t refresh_hz) {
    if (!d->prot) return false;
    if (refresh_hz == 0) refresh_hz = 60;
    if (!mode_fits(d, width, height)) {
        usb_disp_log("[%s] mode %ux%u exceeds chip limit (max_area=%lu)",
                     d->prot->name, width, height,
                     (unsigned long)d->max_area);
        return false;
    }
    // 60Hz は内蔵リスト (VESA/CEA の標準タイミング) を優先
    if (refresh_hz == 60) {
        for (uint8_t i = 0; i < USB_DISP_MODE_COUNT; i++) {
            if (s_modes[i].width == width && s_modes[i].height == height)
                return usb_disp_set_mode_ex(d, &s_modes[i]);
        }
    }
    usb_disp_mode_t m;
    if (!cvt_rb_mode(width, height, refresh_hz, &m)) {
        usb_disp_log("[%s] no timing for %ux%u@%u", d->prot->name, width,
                     height, refresh_hz);
        return false;
    }
    usb_disp_log("[%s] CVT-RB %ux%u@%u: pclk=%lu kHz vblank=%u",
                 d->prot->name, m.width, m.height, refresh_hz,
                 (unsigned long)m.pclk_khz, m.vfp + m.vsync + m.vbp);
    return usb_disp_set_mode_ex(d, &m);
}

bool usb_disp_set_mode(usb_disp_t *d, uint16_t width, uint16_t height) {
    return usb_disp_set_mode_hz(d, width, height, 60);
}

uint8_t usb_disp_builtin_mode_count(void) { return USB_DISP_MODE_COUNT; }
const usb_disp_mode_t *usb_disp_builtin_mode(uint8_t idx) {
    return (idx < USB_DISP_MODE_COUNT) ? &s_modes[idx] : NULL;
}

// ---------------------------------------------------------------
// EDID (prot->read_edid が返すバイト列をパース)
// ---------------------------------------------------------------

// EDID はベースブロック (128B) + 拡張ブロック (128B 単位) から成る。
// 拡張ブロックの個数は byte 126 にある。CEA-861 拡張 (tag 0x02) には
// ベースブロックに載らない対応フォーマットが入っており、これを読まないと
// 「1080p を受けられるのに 480p しか申告していないように見える」中継機
// (HDMI アナライザ / スプリッタ / KVM) で取りこぼす。
//
// 読み出しブロック数の上限。既定 2 (= ベース + 拡張1個) で実機の大半を
// カバーする。DL-1xx はレジスタのオフセットが 8bit なのでそもそも 256B が
// ハード上限。拡張が2個以上ある表示機を T6/MS91xx で使う場合だけ増やす。
#ifndef USB_DISP_EDID_MAX_BLOCKS
  #define USB_DISP_EDID_MAX_BLOCKS 2
#endif
#define USB_DISP_EDID_BUF_SIZE (128 * USB_DISP_EDID_MAX_BLOCKS)

// 読み出し済み EDID のキャッシュ (全ポート共有)
static uint8_t s_edid[USB_DISP_EDID_BUF_SIZE];
static uint16_t s_edid_len;            // 有効バイト数 (0 = 未取得)
static usb_disp_t *s_edid_owner;       // どのポートの EDID か

static void edid_cache_drop(void) {
    s_edid_len = 0;
    s_edid_owner = NULL;
}

// 128B ブロックのチェックサム (全バイトの和が 0)
static bool edid_block_ok(const uint8_t *b) {
    uint8_t sum = 0;
    for (uint8_t i = 0; i < 128; i++) sum = (uint8_t)(sum + b[i]);
    return sum == 0;
}

// EDID を拡張ブロックまで読んでキャッシュする。戻り値: 有効バイト数 (0=失敗)
// ignore_edid が有効なポートでは一切読まない
static uint16_t edid_read_all(usb_disp_t *d) {
    if (s_edid_owner == d && s_edid_len) return s_edid_len;   // poll 内キャッシュ
    edid_cache_drop();
    if (d->cfg.ignore_edid) return 0;

    if (usb_disp_read_edid_at(d, 0, s_edid, 128) != 128) return 0;
    static const uint8_t hdr[8] = {0, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0};
    if (memcmp(s_edid, hdr, 8) != 0) return 0;

    uint16_t len = 128;
    uint8_t ext = s_edid[126];
    if (ext > USB_DISP_EDID_MAX_BLOCKS - 1) ext = USB_DISP_EDID_MAX_BLOCKS - 1;
    for (uint8_t i = 0; i < ext; i++) {
        if (usb_disp_read_edid_at(d, len, s_edid + len, 128) != 128) break;
        // 化けた拡張ブロックを解釈すると出鱈目なモードを拾うので検証する
        // (ベースブロックはヘッダ一致で従来どおり通す)
        if (!edid_block_ok(s_edid + len)) {
            usb_disp_log("[DISP%d] EDID ext block %u checksum error (ignored)",
                         usb_disp_index(d), i + 1);
            break;
        }
        len = (uint16_t)(len + 128);
    }

    s_edid_len = len;
    s_edid_owner = d;
    return len;
}


// 18B の Detailed Timing Descriptor をパースする。
// インタレース (byte17 bit7) は本ライブラリでは出力できないので弾く
// (CEA 拡張には 1080i が "1920x540" の DTD として載っていることがあり、
//  そのまま採用すると 540 ライン設定になってしまう)
static bool edid_dtd_parse(const uint8_t *t, usb_disp_mode_t *out) {
    uint32_t pclk10 = (uint32_t)(t[0] | (t[1] << 8));
    if (pclk10 == 0) return false;
    if (t[17] & 0x80) return false;
    uint16_t hact   = (uint16_t)(t[2] | ((t[4] >> 4) << 8));
    uint16_t hblank = (uint16_t)(t[3] | ((t[4] & 0x0F) << 8));
    uint16_t vact   = (uint16_t)(t[5] | ((t[7] >> 4) << 8));
    uint16_t vblank = (uint16_t)(t[6] | ((t[7] & 0x0F) << 8));
    uint16_t hfp    = (uint16_t)(t[8] | ((t[11] >> 6) << 8));
    uint16_t hsync  = (uint16_t)(t[9] | (((t[11] >> 4) & 3) << 8));
    uint16_t vfp    = (uint16_t)((t[10] >> 4) | (((t[11] >> 2) & 3) << 4));
    uint16_t vsync  = (uint16_t)((t[10] & 0x0F) | ((t[11] & 3) << 4));
    if (!hact || !vact || hblank < hfp + hsync || vblank < vfp + vsync)
        return false;
    out->width = hact;
    out->height = vact;
    out->pclk_khz = pclk10 * 10;
    out->hfp = hfp; out->hsync = hsync;
    out->hbp = (uint16_t)(hblank - hfp - hsync);
    out->vfp = vfp; out->vsync = vsync;
    out->vbp = (uint16_t)(vblank - vfp - vsync);
    return true;
}

// CEA-861 の VIC (Video Identification Code) → アクティブ解像度。
// 本ライブラリが出せるプログレッシブのものだけ
// 同じ解像度でリフレッシュ違いの VIC が複数あるが、
// 判定に使うのは解像度だけなので全部同じ w/h を指す
static const struct { uint8_t vic; uint16_t w, h; } k_cea_vic[] = {
    {  1,  640,  480 },
    {  2,  720,  480 }, {  3,  720,  480 },
    { 48,  720,  480 }, { 49,  720,  480 },
    { 17,  720,  576 }, { 18,  720,  576 },
    { 42,  720,  576 }, { 43,  720,  576 },
    {  4, 1280,  720 }, { 19, 1280,  720 }, { 41, 1280,  720 },
    { 47, 1280,  720 }, { 60, 1280,  720 }, { 61, 1280,  720 },
    { 62, 1280,  720 },
    { 16, 1920, 1080 }, { 31, 1920, 1080 }, { 32, 1920, 1080 },
    { 33, 1920, 1080 }, { 34, 1920, 1080 }, { 63, 1920, 1080 },
    { 64, 1920, 1080 },
};

// VIC → 解像度。テーブルに無い VIC (4K/21:9 など) は false
static bool cea_vic_res(uint8_t vic, uint16_t *w, uint16_t *h) {
    for (uint8_t i = 0; i < sizeof(k_cea_vic) / sizeof(k_cea_vic[0]); i++) {
        if (k_cea_vic[i].vic == vic) {
            *w = k_cea_vic[i].w;
            *h = k_cea_vic[i].h;
            return true;
        }
    }
    return false;
}

// SVD バイト → VIC。値 1..127 は bit7 が native フラグ、
// 値 129..192 はバイト全体が VIC (native フラグ無し)
// 後者を 0x7F でマスクすると別の VIC に化けるので分ける
static inline uint8_t cea_svd_vic(uint8_t v) {
    return (v >= 129 && v <= 192) ? v : (uint8_t)(v & 0x7F);
}

static bool cea_vic_is(uint8_t vic, uint16_t w, uint16_t h) {
    uint16_t vw, vh;
    return cea_vic_res(vic, &vw, &vh) && vw == w && vh == h;
}

// 18B ディスクリプタ列 (ベースの DTD1-4 / 拡張ブロックの DTD) から解像度一致を探す
static bool edid_dtds_list(const uint8_t *p, uint8_t count, uint16_t w,
                           uint16_t h) {
    for (uint8_t i = 0; i < count; i++) {
        usb_disp_mode_t m;
        if (!edid_dtd_parse(&p[i * 18], &m)) continue;
        if (m.width == w && m.height == h) return true;
    }
    return false;
}

// CEA-861 拡張ブロック (128B) が w x h への対応を明示しているか
// データブロックコレクション内の Video Data Block (tag 2) の SVD とブロック後半の DTD の両方を見る
static bool edid_cea_lists_mode(const uint8_t *b, uint16_t w, uint16_t h) {
    if (b[0] != 0x02) return false;          // CEA-861 拡張ではない
    uint8_t dtd_off = b[2];                  // 最初の DTD のオフセット (0 = 無し)

    if (b[1] >= 3 && dtd_off > 4) {
        // データブロックコレクション: [tag(3bit) | len(5bit)] + データ len バイト
        uint8_t p = 4;
        while (p < dtd_off && p < 127) {
            uint8_t tag = (uint8_t)(b[p] >> 5);
            uint8_t len = (uint8_t)(b[p] & 0x1F);
            if (len == 0 && tag == 0) break;            // パディング
            if (tag == 2) {                             // Video Data Block
                for (uint8_t i = 1; i <= len && p + i < 127; i++) {
                    if (cea_vic_is(cea_svd_vic(b[p + i]), w, h)) return true;
                }
            }
            p = (uint8_t)(p + 1 + len);
        }
    }

    if (dtd_off >= 4 && dtd_off < 127) {
        uint8_t n = (uint8_t)((127 - dtd_off) / 18);
        if (edid_dtds_list(b + dtd_off, n, w, h)) return true;
    }
    return false;
}

// established timings のビット割当 (ベースブロック 0x23..0x25)
static const struct { uint16_t w, h; uint8_t ofs, bit; } k_est[] = {
    { 720,  400, 0x23, 7 }, { 720,  400, 0x23, 6 }, { 640,  480, 0x23, 5 },
    { 640,  480, 0x23, 4 }, { 640,  480, 0x23, 3 }, { 640,  480, 0x23, 2 },
    { 800,  600, 0x23, 1 }, { 800,  600, 0x23, 0 }, { 800,  600, 0x24, 7 },
    { 800,  600, 0x24, 6 }, { 832,  624, 0x24, 5 }, { 1024, 768, 0x24, 3 },
    { 1024, 768, 0x24, 2 }, { 1024, 768, 0x24, 1 }, { 1280, 1024, 0x24, 0 },
    { 1152, 870, 0x25, 7 },
};
#define USB_DISP_EST_COUNT ((uint8_t)(sizeof(k_est) / sizeof(k_est[0])))

// standard timing 1エントリ → 解像度 (未使用エントリは false)
static bool edid_std_res(const uint8_t *t, uint16_t *w, uint16_t *h) {
    if (t[0] <= 0x01) return false;
    uint16_t sw = (uint16_t)(((uint16_t)t[0] + 31) * 8);
    switch (t[1] >> 6) {
    case 0:  *h = (uint16_t)(sw * 10 / 16); break;
    case 1:  *h = (uint16_t)(sw * 3 / 4);   break;
    case 2:  *h = (uint16_t)(sw * 4 / 5);   break;
    default: *h = (uint16_t)(sw * 9 / 16);  break;
    }
    *w = sw;
    return true;
}

// モニタが EDID で対応を明示している解像度か (拡張ブロック込み)
// キャッシュ済み EDID (edid_read_all) を見る
static bool edid_lists_mode(uint16_t w, uint16_t h) {
    if (s_edid_len < 128) return false;
    const uint8_t *e = s_edid;

    for (uint8_t i = 0; i < USB_DISP_EST_COUNT; i++) {
        if (k_est[i].w == w && k_est[i].h == h &&
            (e[k_est[i].ofs] & (1u << k_est[i].bit)))
            return true;
    }
    for (uint8_t i = 0; i < 8; i++) {  // standard timings
        uint16_t sw, sh;
        if (edid_std_res(&e[0x26 + i * 2], &sw, &sh) && sw == w && sh == h)
            return true;
    }
    if (edid_dtds_list(&e[54], 4, w, h)) return true;   // ベースの DTD 1-4

    // 拡張ブロック (CEA-861 の SVD / DTD)
    for (uint16_t off = 128; off + 128 <= s_edid_len; off += 128) {
        if (edid_cea_lists_mode(&e[off], w, h)) return true;
    }
    return false;
}

// ---- EDID 記載の最大解像度を探す (edid_policy = MAX 用) ----
// 候補は「DTD (実タイミング付き)」と「解像度だけの記載
// (established / standard timings / CEA の VIC)」の2種類。
// チップ上限 (mode_fits_auto) に収まるもののうち面積最大を採る
typedef struct {
    usb_disp_t *d;
    uint32_t best;            // 採用中の面積 (0 = 未採用)
    uint16_t w, h;
    usb_disp_mode_t dtd;      // is_dtd のときだけ有効
    bool is_dtd;
} edid_scan_t;

static void edid_scan_res(edid_scan_t *s, uint16_t w, uint16_t h) {
    if (!mode_fits_auto(s->d, w, h)) return;
    uint32_t area = (uint32_t)w * h;
    if (area <= s->best) return;
    s->best = area;
    s->w = w;
    s->h = h;
    s->is_dtd = false;
}

static void edid_scan_dtd(edid_scan_t *s, const uint8_t *t) {
    usb_disp_mode_t m;
    if (!edid_dtd_parse(t, &m)) return;
    if (!mode_fits_auto(s->d, m.width, m.height)) return;
    uint32_t area = (uint32_t)m.width * m.height;
    if (area <= s->best) return;
    s->best = area;
    s->w = m.width;
    s->h = m.height;
    s->dtd = m;
    s->is_dtd = true;
}

// EDID 全体を走査して、チップ上限に収まる最大の申告モードを探す
static bool edid_scan_max(usb_disp_t *d, edid_scan_t *s) {
    if (edid_read_all(d) < 128) return false;
    const uint8_t *e = s_edid;
    memset(s, 0, sizeof(*s));
    s->d = d;

    for (uint8_t i = 0; i < 4; i++) edid_scan_dtd(s, &e[54 + i * 18]);
    for (uint8_t i = 0; i < USB_DISP_EST_COUNT; i++) {
        if (e[k_est[i].ofs] & (1u << k_est[i].bit))
            edid_scan_res(s, k_est[i].w, k_est[i].h);
    }
    for (uint8_t i = 0; i < 8; i++) {
        uint16_t sw, sh;
        if (edid_std_res(&e[0x26 + i * 2], &sw, &sh)) edid_scan_res(s, sw, sh);
    }

    // 拡張ブロック (CEA-861): VDB の VIC と DTD
    for (uint16_t off = 128; off + 128 <= s_edid_len; off += 128) {
        const uint8_t *b = &e[off];
        if (b[0] != 0x02) continue;
        uint8_t dtd_off = b[2];
        if (b[1] >= 3 && dtd_off > 4) {
            uint8_t p = 4;
            while (p < dtd_off && p < 127) {
                uint8_t tag = (uint8_t)(b[p] >> 5);
                uint8_t len = (uint8_t)(b[p] & 0x1F);
                if (len == 0 && tag == 0) break;
                if (tag == 2) {
                    for (uint8_t i = 1; i <= len && p + i < 127; i++) {
                        uint16_t vw, vh;
                        if (cea_vic_res(cea_svd_vic(b[p + i]), &vw, &vh))
                            edid_scan_res(s, vw, vh);
                    }
                }
                p = (uint8_t)(p + 1 + len);
            }
        }
        if (dtd_off >= 4 && dtd_off < 127) {
            uint8_t n = (uint8_t)((127 - dtd_off) / 18);
            for (uint8_t i = 0; i < n; i++)
                edid_scan_dtd(s, b + dtd_off + i * 18);
        }
    }
    return s->best != 0;
}

// EDID からモードを決める (適用はしない)
// is_dtd が真なら dtd に実タイミングが入る (そのまま set_mode_ex できる)
static bool edid_target_mode(usb_disp_t *d, uint16_t *w, uint16_t *h,
                             usb_disp_mode_t *dtd, bool *is_dtd) {
    if (edid_read_all(d) < 128) return false;
    if (d->cfg.edid_policy == USB_DISP_EDID_POLICY_PREFERRED) {
        // オフセット 54 = ベースブロック先頭の DTD
        // (preferred timing = モニタのネイティブ解像度)
        usb_disp_mode_t pref;
        if (!edid_dtd_parse(&s_edid[54], &pref)) return false;
        if (!mode_fits_auto(d, pref.width, pref.height)) return false;
        *w = pref.width;
        *h = pref.height;
        *dtd = pref;
        *is_dtd = true;
        return true;
    }
    edid_scan_t s;
    if (!edid_scan_max(d, &s)) return false;
    *w = s.w;
    *h = s.h;
    *is_dtd = s.is_dtd;
    if (s.is_dtd) *dtd = s.dtd;
    return true;
}

// edid_target_mode の結果を適用する
static bool edid_apply_mode(usb_disp_t *d, uint16_t w, uint16_t h,
                            const usb_disp_mode_t *dtd, bool is_dtd) {
    if (is_dtd && usb_disp_set_mode_ex(d, dtd)) return true;
    // DTD が無い (VIC/established/standard 由来) or DTD で失敗 →
    // 内蔵タイミング表 or CVT-RB で組む
    return usb_disp_set_mode_hz(d, w, h, 60);
}

// EDID からモードを決めて設定する。
// *have_edid には「EDID 自体は読めたか」を返す
static bool auto_mode_from_edid(usb_disp_t *d, bool *have_edid) {
    uint16_t w = 0, h = 0;
    usb_disp_mode_t dtd;
    bool is_dtd = false;
    *have_edid = (edid_read_all(d) >= 128);
    if (!*have_edid) return false;
    if (!edid_target_mode(d, &w, &h, &dtd, &is_dtd)) return false;
    if (!edid_apply_mode(d, w, h, &dtd, is_dtd)) return false;
    usb_disp_log("[%s] auto mode: EDID %s %ux%u%s", d->prot->name,
                 d->cfg.edid_policy == USB_DISP_EDID_POLICY_PREFERRED
                     ? "preferred" : "max",
                 w, h, is_dtd ? " (EDID timing)" : "");
    return true;
}

// 内蔵テーブルからのフォールバック選択 (EDID 記載モード優先 → 面積降順)
static bool auto_fallback_mode(usb_disp_t *d) {
    bool have_edid = edid_read_all(d) >= 128;
    for (uint8_t pass = have_edid ? 0 : 1; pass < 2; pass++) {
        for (uint8_t i = 0; i < USB_DISP_MODE_COUNT; i++) {
            if (!mode_fits_auto(d, s_modes[i].width, s_modes[i].height))
                continue;
            if (pass == 0 &&
                !edid_lists_mode(s_modes[i].width, s_modes[i].height))
                continue;
            if (usb_disp_set_mode_ex(d, &s_modes[i])) {
                usb_disp_log("[%s] auto mode: fallback %ux%u%s",
                             d->prot->name, s_modes[i].width,
                             s_modes[i].height,
                             pass == 0 ? " (EDID listed)" : "");
                return true;
            }
        }
    }
    return false;
}

void usb_disp_set_ignore_edid(usb_disp_t *d, bool on) {
    if (!d) return;
    d->cfg.ignore_edid = on;
    if (on) {
        d->edid_pending = false;   // 遅延再チェックも打ち切る
        if (s_edid_owner == d) edid_cache_drop();
    }
}

bool usb_disp_ignore_edid(usb_disp_t *d) { return d && d->cfg.ignore_edid; }

void usb_disp_set_edid_policy(usb_disp_t *d, usb_disp_edid_policy_t policy) {
    if (d) d->cfg.edid_policy = policy;
}

usb_disp_edid_policy_t usb_disp_edid_policy(usb_disp_t *d) {
    return d ? d->cfg.edid_policy : USB_DISP_EDID_POLICY_MAX;
}

bool usb_disp_edid_supports(usb_disp_t *d, uint16_t width, uint16_t height) {
    if (!d || d->cfg.ignore_edid || !width || !height) return false;
    if (edid_read_all(d) < 128) return false;
    return edid_lists_mode(width, height);
}

uint16_t usb_disp_edid_size(usb_disp_t *d) {
    if (!d) return 0;
    return edid_read_all(d);
}

bool usb_disp_edid_max_mode(usb_disp_t *d, uint16_t *width, uint16_t *height) {
    if (!d || d->cfg.ignore_edid) return false;
    edid_scan_t s;
    if (!edid_scan_max(d, &s)) return false;
    if (width) *width = s.w;
    if (height) *height = s.h;
    return true;
}

bool usb_disp_set_auto_mode(usb_disp_t *d) {
    if (!d->prot) return false;
    bool have_edid = false;
    if (auto_mode_from_edid(d, &have_edid)) return true;
    if (auto_fallback_mode(d)) return true;
    usb_disp_log("[%s] auto mode: no mode fits (max_area=%lu)",
                 d->prot->name, (unsigned long)d->max_area);
    return false;
}

// ---------------------------------------------------------------
// シャドウFB (差分更新) - スパン更新型プロトコル (CAP_SHADOW) のみ
// ---------------------------------------------------------------

static bool prot_can_shadow(usb_disp_t *d) {
    return d->prot && (d->prot->caps & USB_DISP_PROT_CAP_SHADOW);
}

// デバイスFBを黒で塗り、シャドウを 0 クリアして同期状態にする
static bool shadow_sync(usb_disp_t *d) {
    if (d->depth24) {
        memset(s_line888, 0, (size_t)d->width * 3);
        if (!d->prot->update888(d, 0, 0, d->width, d->height, s_line888, 0))
            return false;
        memset(d->shadow, 0, d->shadow_bytes);
        return d->prot->flush(d, 1000);
    }
    memset(s_fill_line, 0, (size_t)d->width * 2);
    if (!d->prot->update(d, 0, 0, d->width, d->height, s_fill_line, 0))
        return false;
    if (!d->prot->flush(d, 10000)) return false;
    memset(d->shadow, 0, (size_t)d->width * d->height * 2);
    return true;
}

// モード確定後に呼ぶ。希望に応じて確保/解放し、有効ならデバイスと同期する
static void shadow_setup(usb_disp_t *d) {
    uint32_t need = (uint32_t)d->width * d->height * (d->depth24 ? 3 : 2);
    d->shadow_on = false;
    if (!d->shadow_want || need == 0 || !prot_can_shadow(d)) {
        if (d->shadow) {
            usb_disp_hal_fb_free(d->shadow, d->shadow_bytes);
            d->shadow = NULL;
            d->shadow_bytes = 0;
        }
        if (d->shadow_want && d->prot && !prot_can_shadow(d))
            usb_disp_log("[%s] shadow FB not applicable (full-frame protocol)",
                         d->prot->name);
        return;
    }
    if (d->shadow && d->shadow_bytes != need) {
        usb_disp_hal_fb_free(d->shadow, d->shadow_bytes);
        d->shadow = NULL;
        d->shadow_bytes = 0;
    }
    if (!d->shadow) {
        d->shadow = (uint16_t *)usb_disp_hal_fb_alloc(need);
        if (!d->shadow) {
            usb_disp_log("[DISP%d] shadow FB unavailable (%lu KB)",
                         usb_disp_index(d), (unsigned long)(need / 1024));
            return;
        }
        d->shadow_bytes = need;
    }
    if (!shadow_sync(d)) return;
    d->shadow_on = true;
    usb_disp_log("[DISP%d] shadow FB on (%ux%u, %lu KB)", usb_disp_index(d),
                 d->width, d->height, (unsigned long)(need / 1024));
}

bool usb_disp_set_shadow(usb_disp_t *d, bool on) {
    d->shadow_want = on;
    if (!d->ready || !d->width) return true;
    shadow_setup(d);
    return d->shadow_on == on;
}

bool usb_disp_shadow_active(usb_disp_t *d) { return d->shadow_on; }

const uint16_t *usb_disp_shadow_row(usb_disp_t *d, uint16_t row) {
    if (d && d->depth24) return NULL;   // 24bit 時は非対応 (3B/px のため)
    if (!d->shadow_on || row >= d->height) return NULL;
    return d->shadow + (uint32_t)row * d->width;
}

// ---------------------------------------------------------------
// 描画 API (クリッピング + シャドウ差分はコア、送出はプロトコル)
// ---------------------------------------------------------------

// 1行ぶんの 565 更新 (シャドウ有効時は差分だけ送る)
static bool core_update565_row(usb_disp_t *d, uint16_t x, uint16_t y,
                               uint16_t w, const uint16_t *src) {
    if (!d->shadow_on) return d->prot->update(d, x, y, w, 1, src, 0);
    uint16_t *sh = d->shadow + (uint32_t)y * d->width + x;
    if (memcmp(sh, src, (size_t)w * 2) == 0) return true;
    uint32_t a = 0, b = (uint32_t)w - 1;
    while (sh[a] == src[a]) a++;
    while (sh[b] == src[b]) b--;
    uint16_t cw = (uint16_t)(b - a + 1);
    memcpy(sh + a, src + a, (size_t)cw * 2);
    return d->prot->update(d, (uint16_t)(x + a), y, cw, 1, src + a, 0);
}

// 1行ぶんの 888 更新 (シャドウ有効時は差分だけ送る)。src = 3B/px B,G,R
static bool core_update888_row(usb_disp_t *d, uint16_t x, uint16_t y,
                               uint16_t w, const uint8_t *src) {
    if (!d->shadow_on) return d->prot->update888(d, x, y, w, 1, src, 0);
    uint8_t *sh = (uint8_t *)d->shadow + ((uint32_t)y * d->width + x) * 3;
    if (memcmp(sh, src, (size_t)w * 3) == 0) return true;
    uint32_t a = 0, b = (uint32_t)w - 1;
    while (memcmp(sh + a * 3, src + a * 3, 3) == 0) a++;
    while (memcmp(sh + b * 3, src + b * 3, 3) == 0) b--;
    uint16_t cw = (uint16_t)(b - a + 1);
    memcpy(sh + a * 3, src + a * 3, (size_t)cw * 3);
    return d->prot->update888(d, (uint16_t)(x + a), y, cw, 1, src + a * 3, 0);
}

bool usb_disp_update_565(usb_disp_t *d, uint16_t x, uint16_t y, uint16_t w,
                         uint16_t h, const uint16_t *rgb565,
                         uint32_t stride_px) {
    if (!d->ready || d->width == 0 || !d->prot) return false;
    // 実解像度でクリッピング (右端・下端のみ)
    if (x >= d->width || y >= d->height) return true;  // 完全に画面外
    if ((uint32_t)x + w > d->width) w = (uint16_t)(d->width - x);
    if ((uint32_t)y + h > d->height) h = (uint16_t)(d->height - y);

    if (d->depth24) {
        // 24bit モード: 565 入力を 888 に展開して 24bit 経路へ (行単位)
        for (uint16_t row = 0; row < h; row++) {
            const uint16_t *src =
                stride_px ? rgb565 + (uint32_t)row * stride_px : rgb565;
            row_565_to_888(src, s_line888, w);
            if (!core_update888_row(d, x, (uint16_t)(y + row), w, s_line888))
                return false;
        }
        return true;
    }

    if (!d->shadow_on)
        return d->prot->update(d, x, y, w, h, rgb565, stride_px);

    // 差分更新: 変化のない行はスキップ、変化した行は先頭/末尾の一致部分を
    // 削って変化区間だけを送る (スパン更新型プロトコルのみ到達)
    for (uint16_t row = 0; row < h; row++) {
        const uint16_t *src =
            stride_px ? rgb565 + (uint32_t)row * stride_px : rgb565;
        if (!core_update565_row(d, x, (uint16_t)(y + row), w, src))
            return false;
    }
    return true;
}

// RGB888 版の矩形更新 (px = 3B/px, B,G,R 順)
bool usb_disp_update_888(usb_disp_t *d, uint16_t x, uint16_t y, uint16_t w,
                         uint16_t h, const uint8_t *px, uint32_t stride_px) {
    if (!d->ready || d->width == 0 || !d->prot) return false;
    if (x >= d->width || y >= d->height) return true;  // 完全に画面外
    if ((uint32_t)x + w > d->width) w = (uint16_t)(d->width - x);
    if ((uint32_t)y + h > d->height) h = (uint16_t)(d->height - y);

    if (d->depth24) {
        if (!d->shadow_on)
            return d->prot->update888(d, x, y, w, h, px, stride_px);
        for (uint16_t row = 0; row < h; row++) {
            const uint8_t *src =
                stride_px ? px + (uint32_t)row * stride_px * 3 : px;
            if (!core_update888_row(d, x, (uint16_t)(y + row), w, src))
                return false;
        }
        return true;
    }

    // 16bit モード: 888 入力を 565 に落として通常経路へ (行単位)
    for (uint16_t row = 0; row < h; row++) {
        const uint8_t *src = stride_px ? px + (uint32_t)row * stride_px * 3 : px;
        row_888_to_565(src, s_line565, w);
        if (d->shadow_on) {
            if (!core_update565_row(d, x, (uint16_t)(y + row), w, s_line565))
                return false;
        } else {
            if (!d->prot->update(d, x, (uint16_t)(y + row), w, 1, s_line565, 0))
                return false;
        }
    }
    return true;
}

// 汎用形: fmt でピクセル形式を選ぶ (565/888 のディスパッチ)
bool usb_disp_update(usb_disp_t *d, uint16_t x, uint16_t y, uint16_t w,
                     uint16_t h, const void *px, uint32_t stride_px,
                     usb_disp_fmt_t fmt) {
    if (fmt == USB_DISP_FMT_RGB888)
        return usb_disp_update_888(d, x, y, w, h, (const uint8_t *)px,
                                   stride_px);
    return usb_disp_update_565(d, x, y, w, h, (const uint16_t *)px, stride_px);
}

bool usb_disp_copy(usb_disp_t *d, uint16_t sx, uint16_t sy, uint16_t dx,
                   uint16_t dy, uint16_t w, uint16_t h) {
    if (!d->ready || d->width == 0 || !d->prot || !d->prot->copy)
        return false;
    if (w == 0 || h == 0) return true;
    if ((uint32_t)sx + w > d->width || (uint32_t)dx + w > d->width ||
        (uint32_t)sy + h > d->height || (uint32_t)dy + h > d->height)
        return false;
    if (sx == dx && sy == dy) return true;
    if (!d->prot->copy(d, sx, sy, dx, dy, w, h)) return false;

    // シャドウにも同じコピーを反映
    if (d->shadow_on) {
        bool bottom_up = (dy > sy);
        uint8_t bpp = d->depth24 ? 3 : 2;
        uint8_t *sh = (uint8_t *)d->shadow;
        for (uint16_t i = 0; i < h; i++) {
            uint16_t row = bottom_up ? (uint16_t)(h - 1 - i) : i;
            memmove(sh + ((uint32_t)(dy + row) * d->width + dx) * bpp,
                    sh + ((uint32_t)(sy + row) * d->width + sx) * bpp,
                    (size_t)w * bpp);
        }
    }
    return true;
}

bool usb_disp_fill(usb_disp_t *d, uint16_t x, uint16_t y, uint16_t w,
                  uint16_t h, uint16_t color) {
    if (!d->ready || w > USB_DISP_MAX_WIDTH) return false;
    for (uint16_t i = 0; i < w; i++) s_fill_line[i] = color;
    return usb_disp_update_565(d, x, y, w, h, s_fill_line, 0);
}

bool usb_disp_flush(usb_disp_t *d, uint32_t timeout_ms) {
    if (!d->prot) return usb_disp_hal_bulk_flush(d->hal, timeout_ms);
    return d->prot->flush(d, timeout_ms);
}

bool usb_disp_blank(usb_disp_t *d, bool on) {
    if (!d->ready || !d->prot || !d->prot->blank) return false;
    return d->prot->blank(d, on);
}

// ---------------------------------------------------------------
// ライフサイクル
// ---------------------------------------------------------------

void usb_disp_init(void) {
    memset(s_disp, 0, sizeof(s_disp));
    s_ndisp = 0;
}

usb_disp_t *usb_disp_add_cfg(const usb_disp_config_t *cfg) {
    if (!cfg || s_ndisp >= USB_DISP_MAX) return NULL;
    usb_disp_hal_t *hal = usb_disp_hal_add(cfg);
    if (!hal) return NULL;
    usb_disp_t *d = &s_disp[s_ndisp];
    memset(d, 0, sizeof(*d));
    d->in_use = true;
    d->hal = hal;
    d->cfg = *cfg;
    d->shadow_want = cfg->shadow_fb;
    d->depth24_want = cfg->depth24;
    d->stage = USB_DISP_STAGE_WAIT_DEVICE;
    s_ndisp++;
    return d;
}

usb_disp_t *usb_disp_add(uint8_t port, uint8_t pin_dp, uint8_t pin_dm,
                         uint16_t width, uint16_t height, bool ignore_edid) {
    usb_disp_config_t cfg;
    memset(&cfg, 0, sizeof(cfg));
    cfg.port = port;
    cfg.pin_dp = pin_dp;
    cfg.pin_dm = pin_dm;
    cfg.width = width;
    cfg.height = height;
    cfg.ignore_edid = ignore_edid;
    return usb_disp_add_cfg(&cfg);
}

void usb_disp_start(void) {
    usb_disp_hal_start();
}

void usb_disp_start_manual(void) {
    usb_disp_hal_start_manual();
}

void usb_disp_task(void) {
    usb_disp_hal_task();
}

uint8_t usb_disp_count(void) { return s_ndisp; }
usb_disp_t *usb_disp_at(uint8_t idx) {
    return (idx < s_ndisp) ? &s_disp[idx] : NULL;
}
uint8_t usb_disp_index(usb_disp_t *d) { return (uint8_t)(d - s_disp); }

bool usb_disp_ready(usb_disp_t *d) { return d->ready; }
uint16_t usb_disp_width(usb_disp_t *d) { return d->width; }
uint16_t usb_disp_height(usb_disp_t *d) { return d->height; }
uint16_t usb_disp_vid(usb_disp_t *d) { return d->vid; }
uint16_t usb_disp_pid(usb_disp_t *d) { return d->pid; }
uint64_t usb_disp_stat_bytes(usb_disp_t *d) {
    return usb_disp_hal_stat_bytes(d->hal);
}

#if USB_DISP_PORT_PICO
// 宣言は usb_disp_hal.h (extern "C" 内)
usb_disp_udh_host_t *usb_disp_get_host(usb_disp_t *d) {
    return usb_disp_hal_pico_host(d->hal);
}
#endif

void usb_disp_force_reenum(usb_disp_t *d) {
    usb_disp_hal_request_reenum(d->hal);
}

static void reset_device_state(usb_disp_t *d) {
    if (d->prot && d->prot->detach) d->prot->detach(d);
    d->ready = false;
    d->vid = d->pid = 0;
    d->prot = NULL;
    d->chip = USB_DISP_CHIP_UNKNOWN;
    d->max_area = 0;
    d->width = d->height = 0;
    memset(&d->cur_mode, 0, sizeof(d->cur_mode));
    d->edid_pending = false;
    if (s_edid_owner == d) edid_cache_drop();
    // シャドウは同期が切れるので無効化 (メモリは保持、shadow_setup が再同期する)
    d->shadow_on = false;
}

bool usb_disp_poll(usb_disp_t *d) {
    bool changed = false;
    uint32_t now = usb_disp_hal_ms();

    // EDID キャッシュは 1回の poll 内でのみ有効
    edid_cache_drop();

    usb_disp_hal_poll(d->hal);
    bool attached = usb_disp_hal_attached(d->hal);

    switch (d->stage) {
    case USB_DISP_STAGE_WAIT_DEVICE:
        if (!attached) break;
        d->vid = usb_disp_hal_vid(d->hal);
        d->pid = usb_disp_hal_pid(d->hal);
        d->prot = usb_disp_prot_find(d->vid, d->pid);
        if (d->prot && d->prot->attach(d)) {
            usb_disp_log("[DISP%d] protocol: %s", usb_disp_index(d),
                         d->prot->name);
            if (d->cfg.ignore_edid)
                usb_disp_log("[DISP%d] ignore_edid: EDID is not read; "
                             "mode comes from cfg/builtin list only",
                             usb_disp_index(d));
            if (d->cfg.no_auto_mode) {
                d->ready = true;
                d->stage = USB_DISP_STAGE_READY;
                changed = true;
            } else {
                d->mode_deadline_ms = now + USB_DISP_MODE_SETUP_WAIT_MS;
                d->mode_next_ms = now;
                d->stage = USB_DISP_STAGE_MODE_SETUP;
            }
        } else {
            usb_disp_log("[DISP%d] unsupported device (VID=%04X PID=%04X)%s",
                         usb_disp_index(d), d->vid, d->pid,
                         d->prot ? " (attach failed)" : "");
            d->prot = NULL;
            d->stage = USB_DISP_STAGE_FAILED;
            d->failed_since_ms = now;
        }
        break;

    case USB_DISP_STAGE_MODE_SETUP: {
        if (!attached) {
            reset_device_state(d);
            d->stage = USB_DISP_STAGE_WAIT_DEVICE;
            break;
        }
        if ((int32_t)(now - d->mode_next_ms) < 0) break;
        d->mode_next_ms = now + USB_DISP_MODE_SETUP_RETRY_MS;
        bool expired = (int32_t)(now - d->mode_deadline_ms) >= 0;

        bool mode_ok = false;
        // 1. cfg 指定解像度 (あれば最優先)
        if (d->cfg.width && d->cfg.height)
            mode_ok = usb_disp_set_mode_hz(d, d->cfg.width, d->cfg.height,
                                           d->cfg.refresh_hz);
        // 2. EDID から自動選択
        if (!mode_ok && !d->cfg.ignore_edid) {
            bool have_edid = false;
            if (auto_mode_from_edid(d, &have_edid)) {
                mode_ok = true;
            } else if (!have_edid && !expired) {
                break;  // EDID がまだ読めない → リトライ
            } else if (!have_edid) {
                usb_disp_log("[%s] auto mode: EDID unavailable, fallback",
                             d->prot->name);
                d->edid_pending = true;
                d->edid_next_ms = now + USB_DISP_EDID_RECHECK_MS;
                d->edid_until_ms = now + USB_DISP_EDID_RECHECK_MAX_MS;
            }
        }
        // 3. 内蔵テーブルから (EDID 記載モード優先 → 面積降順)
        if (!mode_ok) {
            mode_ok = auto_fallback_mode(d);
        }
        if (!mode_ok && !expired) break;
        if (!mode_ok)
            usb_disp_log("[%s] auto mode: no mode set (max_area=%lu)",
                         d->prot->name, (unsigned long)d->max_area);
        d->ready = true;
        d->stage = USB_DISP_STAGE_READY;
        changed = true;
        break;
    }

    case USB_DISP_STAGE_READY:
        if (!attached) {
            if (d->ready) changed = true;
            usb_disp_log("[DISP%d] disconnected", usb_disp_index(d));
            reset_device_state(d);
            d->stage = USB_DISP_STAGE_WAIT_DEVICE;
            break;
        }
        // プロトコル定期処理 (MS913x のキープアライブ等)
        if (d->prot && d->prot->poll) d->prot->poll(d);
        // EDID 遅延再チェック (フォールバック起動後のモード昇格)
        if (d->edid_pending && !d->cfg.ignore_edid &&
            (int32_t)(now - d->edid_next_ms) >= 0) {
            d->edid_next_ms = now + USB_DISP_EDID_RECHECK_MS;
            if (edid_read_all(d) >= 128) {
                d->edid_pending = false;
                // 既に同じ解像度なら触らない
                uint16_t tw = 0, th = 0;
                usb_disp_mode_t tdtd;
                bool tis_dtd = false;
                if (edid_target_mode(d, &tw, &th, &tdtd, &tis_dtd) &&
                    (tw != d->width || th != d->height)) {
                    usb_disp_log("[%s] EDID arrived late: switching to %ux%u",
                                 d->prot->name, tw, th);
                    if (edid_apply_mode(d, tw, th, &tdtd, tis_dtd))
                        changed = true;
                }
            } else if ((int32_t)(now - d->edid_until_ms) > 0) {
                d->edid_pending = false;
            }
        }
        break;

    case USB_DISP_STAGE_FAILED:
        if (!attached) {
            reset_device_state(d);
            d->stage = USB_DISP_STAGE_WAIT_DEVICE;
            break;
        }
        if (now - d->failed_since_ms >= USB_DISP_UNSUPPORTED_RETRY_MS) {
            usb_disp_log("[DISP%d] periodic re-enumeration...",
                         usb_disp_index(d));
            reset_device_state(d);
            usb_disp_hal_request_reenum(d->hal);
            d->stage = USB_DISP_STAGE_WAIT_DEVICE;
        }
        break;
    }
    return changed;
}

