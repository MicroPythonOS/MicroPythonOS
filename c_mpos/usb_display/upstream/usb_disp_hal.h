//
// ######################################################################
//
//    usb_disp_hal - USB ホストトランスポート抽象層 (HAL)
//
//    プラットフォーム固有の USB ホスト実装を分離するインターフェース
//
//    - usb_disp_hal_pico.cpp   : [RP2040/RP2350] PIO USB FS ホスト
//    - usb_disp_hal_esp32.cpp  : [ESP32-S2/S3/P4] ESP-IDF usb_host
//    - usb_disp_hal_teensy.cpp : [Teensy 4.x] Teensyduino USBHost_t36
//    - usb_disp_hal_libusb.cpp : [PC] libusb host
//
//    Copyright (C) 2026
//      Hideto Kikuchi / PJラボ (@pcjpnet) - https://pc-jp.net/
//
// ######################################################################
//

#ifndef USB_DISP_HAL_H_
#define USB_DISP_HAL_H_

#include <stdint.h>
#include <stdbool.h>

#include "usb_disp.h"  // usb_disp_config_t / プラットフォーム判定マクロ

#ifdef __cplusplus
extern "C" {
#endif

typedef struct usb_disp_hal usb_disp_hal_t;  // バックエンド定義

// ポート登録
// usb_disp_hal_start() の前に呼ぶ。失敗 (上限/ピン不正) は NULL。
usb_disp_hal_t *usb_disp_hal_add(const usb_disp_config_t *cfg);

// 全ポート登録後に一度だけ呼ぶ (ホストスタック/ワーカーの起動)
void usb_disp_hal_start(void);

// 手動サービスモード (Pico のみ実体あり、他は start/no-op と同義)
// start の代わりに start_manual を呼び、以後 task を専有コンテキスト
// (arduino-pico の loop1() 等) から休みなく呼び続ける
void usb_disp_hal_start_manual(void);
void usb_disp_hal_task(void);

// 定期的に呼ぶ。接続検出・エニュメレーションを進める (ESP32 では no-op)
void usb_disp_hal_poll(usb_disp_hal_t *h);

// エニュメレーション完了済みで ctrl/bulk が使えるか
bool usb_disp_hal_attached(usb_disp_hal_t *h);
uint16_t usb_disp_hal_vid(usb_disp_hal_t *h);
uint16_t usb_disp_hal_pid(usb_disp_hal_t *h);

// コントロール転送。setup は 8 バイトの SETUP パケット
// data は方向に応じて送信元/受信先。actual は NULL 可。
bool usb_disp_hal_ctrl(usb_disp_hal_t *h, const uint8_t setup[8], void *data,
                       uint16_t *actual);

// バルク OUT。戻り値は受理したバイト数 (len 未満 = 失敗/タイムアウト)
uint32_t usb_disp_hal_bulk_write(usb_disp_hal_t *h, const void *data,
                                 uint32_t len);
// 送信完了待ち
bool usb_disp_hal_bulk_flush(usb_disp_hal_t *h, uint32_t timeout_ms);
// ストリーム終端に ZLP (長さ0パケット) を置く。
// 保留中の書き込みがあればそれを送出した上で終端する。
// フレーム長が常に mps の倍数になるプロトコル (MS913x) 用。
// bulk_write の後・bulk_flush の前に呼ぶ。
// (Pico バックエンドは対応チップが無いため no-op)
bool usb_disp_hal_bulk_zlp(usb_disp_hal_t *h);

// 転送境界: 保留中の書き込みを「ここまでで1つの転送」として送出する
// (末尾が mps 未満ならショートパケットになる)。
// 転送単位に意味があるプロトコル (T6 の 32B セレクタ等) 用。
// (Pico は no-op = 常時ストリーム)
bool usb_disp_hal_bulk_split(usb_disp_hal_t *h);

// 再エニュメレーション要求 (非対応デバイスの周期再試行等。
// スタックが自動管理するバックエンドでは no-op でよい)
void usb_disp_hal_request_reenum(usb_disp_hal_t *h);

// 単調ミリ秒カウンタ (コアのタイマー用)
uint32_t usb_disp_hal_ms(void);

// 累積バルク送信バイト数 (統計用。シャドウFB差分更新の効果測定など)
uint64_t usb_disp_hal_stat_bytes(usb_disp_hal_t *h);

#if USB_DISP_PORT_PICO
// Pico 固有: 統計アクセス用に udh ホストハンドルを公開 (usb_disp_get_host 用)。
// 宣言をここに置くことで定義側 (usb_disp_hal_pico.cpp) と呼び出し側
// (usb_disp.cpp) が同じ宣言を見る = シグネチャ不一致がコンパイルエラーになる
usb_disp_udh_host_t *usb_disp_hal_pico_host(usb_disp_hal_t *h);
#endif

// コンフィグディスクリプタに埋め込まれた DisplayLink ベンダーディスクリプタ
// (bDescriptorType=0x5F、エニュメレーション時に捕捉) を buf へコピーして
// 長さを返す (無ければ 0)。GET_DESCRIPTOR type 0x5F 要求に応答しない個体の
// フォールバック用 (udlfb: dlfb_parse_vendor_descriptor と同じ二段構え)
uint16_t usb_disp_hal_vendor_desc(usb_disp_hal_t *h, void *buf,
                                  uint16_t maxlen);

// ---- 大容量フレームバッファ用メモリ (シャドウFB 等) ----
// プラットフォームの「大きくて多少遅くてもよい」メモリから確保する:
//   - Pico : 常に NULL (内蔵 RAM に FullHD 級は置けない → 機能オフ)
//   - ESP32: PSRAM (MALLOC_CAP_SPIRAM)。合計確保量を
//            USB_DISP_PSRAM_LIMIT_KB (コンパイル時定数, 0=無制限) の
//            範囲で管理し、超える要求には NULL を返す
//   - Teensy 4.1: 増設 PSRAM (extmem_malloc)。未実装ボードでは NULL
//   - PC   : malloc
// 呼び出し側は NULL を「この環境では使えない」として扱うこと。
void *usb_disp_hal_fb_alloc(uint32_t size);
void usb_disp_hal_fb_free(void *p, uint32_t size);
uint32_t usb_disp_hal_fb_used(void);  // 現在の合計確保量 [byte]

#ifdef __cplusplus
}
#endif

#endif  // USB_DISP_HAL_H_

