//
// ######################################################################
//
//    usb_disp_prot - プロトコル層抽象
//
//    プロトコル実装
//      usb_disp_prot_dl-1xx.cpp  : DisplayLink DL-1x0/1x5
//      usb_disp_prot_ms91xx.cpp  : MacroSilicon MS912x/MS913x
//      usb_disp_prot_t6.cpp      : MCT Trigger 6
//
//    Copyright (C) 2026
//      Hideto Kikuchi / PJラボ (@pcjpnet) - https://pc-jp.net/
//
// ######################################################################
//

#ifndef USB_DISP_PROT_H_
#define USB_DISP_PROT_H_

#include "usb_disp.h"
#include "usb_disp_hal.h"

// ---- HS プロトコル (T6/MS91xx) を組み込むかどうか ----
//  PC (libusb) と ESP32-P4 (HS ホスト) のみ
//  それ以外は FS で帯域が不足するため、実装ごとコンパイルしない
//  Teensy 4.x は HS ホストだが、
//  T6/MS91xx はフレームバッファがRAMに収まらないため組み込まない
#if USB_DISP_PORT_ESP32
  #include "sdkconfig.h"
#endif
#if USB_DISP_PORT_LIBUSB || \
    (USB_DISP_PORT_ESP32 && defined(CONFIG_IDF_TARGET_ESP32P4))
  #define USB_DISP_PROT_HS 1
#else
  #define USB_DISP_PROT_HS 0
#endif

#ifdef __cplusplus
extern "C" {
#endif

// ---- 接続状態 ----
typedef enum {
    USB_DISP_STAGE_WAIT_DEVICE = 0,
    USB_DISP_STAGE_MODE_SETUP,
    USB_DISP_STAGE_READY,
    USB_DISP_STAGE_FAILED,
} usb_disp_stage_t;

typedef struct usb_disp_prot usb_disp_prot_t;

// ---- ディスプレイインスタンス ----
struct usb_disp {
    bool in_use;
    usb_disp_hal_t *hal;
    bool ready;
    usb_disp_config_t cfg;
    uint16_t vid, pid;
    usb_disp_chip_t chip;
    uint32_t max_area;
    uint16_t width, height;
    usb_disp_mode_t cur_mode;       // 現在のモード (タイミング込み。未設定は全0)
    bool depth24_want;              // アプリ要求 (cfg.depth24 / set_depth)
    bool depth24;                   // 実効 24bit カラー (set_mode 時に確定。
                                    // prot が非対応なら false のまま = 565 動作)

    const usb_disp_prot_t *prot;    // 判別されたプロトコル (未接続は NULL)
    void *pp;                       // プロトコル私有状態 (実装が管理)

    usb_disp_stage_t stage;
    uint32_t failed_since_ms;
    uint32_t mode_deadline_ms;
    uint32_t mode_next_ms;
    bool edid_pending;
    uint32_t edid_next_ms;
    uint32_t edid_until_ms;

    // シャドウFB (差分更新)。スパン更新型プロトコル (CAP_SHADOW) のみ
    bool shadow_want;
    bool shadow_on;
    uint16_t *shadow;
    uint32_t shadow_bytes;
};

// ---- プロトコル ops ----
//   すべての描画系は READY 後・クリップ済み座標で呼ばれる。
//   NULL 許容: copy / blank / poll / detach (非対応は NULL)
struct usb_disp_prot {
    const char *name;   // ログ用 ("DL-1xx" 等)
    uint8_t caps;

    // このプロトコルが担当するデバイスか (VID/PID)
    bool (*match)(uint16_t vid, uint16_t pid);

    // 接続直後の初期化: チップ判別 (d->chip / d->max_area 設定)、
    // プロトコル初期化。false でこのデバイスを FAILED 扱い
    bool (*attach)(usb_disp_t *d);
    // 切断時のクリーンアップ
    void (*detach)(usb_disp_t *d);

    // モード設定。非対応モードは false (コアがフォールバックを続ける)
    bool (*set_mode)(usb_disp_t *d, const usb_disp_mode_t *m);
    // EDID 読み出し
    // offset バイト目から len バイト読み、読めたバイト数を返す
    // 拡張ブロック (128B 単位) を読むため offset を取る
    // DL-1xx はレジスタのオフセットが 8bit なので 256B 目以降は読めない
    uint16_t (*read_edid)(usb_disp_t *d, uint16_t offset, uint8_t *buf,
                          uint16_t len);

    // 矩形更新 (RGB565, stride_px=0 は同一行の繰り返し)
    bool (*update)(usb_disp_t *d, uint16_t x, uint16_t y, uint16_t w,
                   uint16_t h, const uint16_t *px, uint32_t stride_px);
    // 矩形更新 (RGB888, 3B/px メモリ順 B,G,R)。NULL = 24bit 非対応。
    // d->depth24 (実効) が真のときだけ呼ばれる。
    // set_mode は d->depth24 を見てモードを組み、
    // 対応できない場合は d->depth24 を false に戻してよい
    bool (*update888)(usb_disp_t *d, uint16_t x, uint16_t y, uint16_t w,
                      uint16_t h, const uint8_t *px, uint32_t stride_px);
    // 画面内矩形コピー (NULL = 非対応)
    bool (*copy)(usb_disp_t *d, uint16_t sx, uint16_t sy, uint16_t dx,
                 uint16_t dy, uint16_t w, uint16_t h);
    // フレーム境界: 蓄積した更新の送出+送信完了待ち
    bool (*flush)(usb_disp_t *d, uint32_t timeout_ms);
    bool (*blank)(usb_disp_t *d, bool on);
    // READY 中の定期処理 (キープアライブ等)。usb_disp_poll から呼ばれる
    void (*poll)(usb_disp_t *d);
};

// スパン更新型 (行内の任意区間を独立に送れる) = コアのシャドウFB差分が使える。
// フルフレーム型 (T6/MS91xx) はプロトコル側の dirty 管理に任せる
#define USB_DISP_PROT_CAP_SHADOW 0x01
// 24bit カラー (RGB888) 対応
#define USB_DISP_PROT_CAP_888    0x02

// ---- プロトコル実装 ----
extern const usb_disp_prot_t usb_disp_prot_dl1xx;
#if USB_DISP_PROT_HS
extern const usb_disp_prot_t usb_disp_prot_t6;
extern const usb_disp_prot_t usb_disp_prot_ms91xx;
#endif

// VID/PID からプロトコルを探す
// (コア実装。HAL は usb_disp.h の usb_disp_supported_device() を使う)
const usb_disp_prot_t *usb_disp_prot_find(uint16_t vid, uint16_t pid);

// チップ確定リスト (usb_disp_model.h) から実チップを引く。
// SKU 情報 (0x5F) を公開しない DL-1x0 個体の型番判定用
// (リストに無ければ USB_DISP_CHIP_UNKNOWN)
usb_disp_chip_t usb_disp_model_chip(uint16_t vid, uint16_t pid);

// ---- 共有ヘルパ (コア提供) ----
// コントロール転送 (setup 8B を組み立てて HAL へ)
bool usb_disp_prot_ctrl(usb_disp_t *d, uint8_t bmRequestType,
                         uint8_t bRequest, uint16_t wValue, uint16_t wIndex,
                         void *data, uint16_t wLength, uint16_t *actual);

// HS プロトコル用スリープ (初期化シーケンスの待ち時間。
// PC / ESP32-P4 のみで使われる, Pico にはブロッキング待ちを持ち込まない)
#if USB_DISP_PROT_HS
  #if USB_DISP_PORT_ESP32
    #include "freertos/FreeRTOS.h"
    #include "freertos/task.h"
    static inline void usb_disp_prot_sleep_ms(uint32_t ms) {
        vTaskDelay(pdMS_TO_TICKS(ms));
    }
  #elif defined(_WIN32)
    void __stdcall Sleep(unsigned long ms);  // <windows.h> を引き込まない
    static inline void usb_disp_prot_sleep_ms(uint32_t ms) { Sleep(ms); }
  #else
    #include <unistd.h>
    static inline void usb_disp_prot_sleep_ms(uint32_t ms) {
        usleep(ms * 1000);
    }
  #endif
#endif

#ifdef __cplusplus
}
#endif

#endif  // USB_DISP_PROT_H_

