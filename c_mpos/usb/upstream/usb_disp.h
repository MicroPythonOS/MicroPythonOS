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

#ifndef USB_DISP_H_
#define USB_DISP_H_

#include <stdint.h>
#include <stdbool.h>

// ---- プラットフォーム判定 ----
//   1. Raspberry Pi Pico (RP2040/RP2350): ARDUINO_ARCH_RP2040 / PICO_ON_DEVICE 定義
//   2. ESP32 系 (S2/S3/P4): ESP_PLATFORM 定義
//   3. Teensy 4.x (i.MX RT1062): __IMXRT1062__ 定義
//   4. その他の Arduino ボード (AVR 等): 非対応 → #error で案内
//   5. それ以外: PC / 組み込み OS → libusb バックエンド
//        (_WIN32=Windows, __APPLE__=macOS, __unix__=Linux/BSD 等)

#if defined(ARDUINO_ARCH_RP2040) || defined(PICO_ON_DEVICE) || \
    defined(PICO_RP2040) || defined(PICO_RP2350)
  #define USB_DISP_PORT_ESP32  0
  #define USB_DISP_PORT_LIBUSB 0
  #define USB_DISP_PORT_PICO   1
  #define USB_DISP_PORT_TEENSY 0
#elif defined(ESP_PLATFORM) || defined(ARDUINO_ARCH_ESP32)
  #define USB_DISP_PORT_ESP32  1
  #define USB_DISP_PORT_LIBUSB 0
  #define USB_DISP_PORT_PICO   0
  #define USB_DISP_PORT_TEENSY 0
#elif defined(__IMXRT1062__)
  #define USB_DISP_PORT_ESP32  0
  #define USB_DISP_PORT_LIBUSB 0
  #define USB_DISP_PORT_PICO   0
  #define USB_DISP_PORT_TEENSY 1
#elif defined(ARDUINO)
  #error "Pico_USB_Disp: Unsupported Arduino board. Supported: Raspberry Pi Pico / Pico 2 (arduino-pico core), ESP32-S2/S3/P4 (esp32 core 3.x), or Teensy 4.x (Teensyduino). / このボードは非対応です。ツール > ボード で Raspberry Pi Pico/Pico 2 / ESP32-S2/S3/P4 / Teensy 4.x を選択してください。"
#elif defined(_WIN32) || defined(__APPLE__) || defined(__unix__)
  #define USB_DISP_PORT_ESP32  0
  #define USB_DISP_PORT_LIBUSB 1
  #define USB_DISP_PORT_PICO   0
  #define USB_DISP_PORT_TEENSY 0
#else
  #error "Pico_USB_Disp: Unknown Platform. Supported: Raspberry Pi Pico/Pico 2 (RP2040/RP2350), ESP32-S2/S3/P4, Teensy 4.x, or an OS with libusb (Windows/macOS/Linux/BSD)."
#endif

#if USB_DISP_PORT_PICO
  #include "hardware/pio.h"
  #include "usb_disp_udh_host.h"
#endif

#ifdef __cplusplus
extern "C" {
#endif

// 対応する最大水平解像度 (ラインバッファのサイズを決める)
// DL-195 の 2048x1152 まで対応。RAM の少ない RP2040 ではコンパイルオプションで小さくしてよい
#ifndef USB_DISP_MAX_WIDTH
  #define USB_DISP_MAX_WIDTH 2048
#endif

// 同時ディスプレイ数の上限
#if USB_DISP_PORT_PICO
  #define USB_DISP_MAX USB_DISP_UDH_MAX_PORTS  // PIO ブロック数 (RP2350=3, RP2040=2)
#elif USB_DISP_PORT_LIBUSB
  #ifndef USB_DISP_MAX
    #define USB_DISP_MAX 4  // PC: 対応デバイスを列挙し発見順に割り当て
  #endif
#else
  #define USB_DISP_MAX 1  // ESP32: OTG 1系統 / Teensy 4.x: EHCI ホスト1系統
#endif

typedef struct usb_disp usb_disp_t;

// 判別したチップ (usb_disp_chip() で取得)。
typedef enum {
    USB_DISP_CHIP_UNKNOWN = 0,
    // DisplayLink Gen1.0 "Alex" (DL-1x0)
    USB_DISP_CHIP_DL120,       // max 1280x1024 / 1400x1050
    USB_DISP_CHIP_DL160,       // max 1600x1200 / 1680x1050
    USB_DISP_CHIP_DL1X0,       // Gen1.0 だが型番不明
    // DisplayLink Gen1.5 "Ollie" (DL-1x5)
    USB_DISP_CHIP_DL115,       // max 1024x600
    USB_DISP_CHIP_DL125,       // max 1280x1024 / 1440x900
    USB_DISP_CHIP_DL165,       // max 1600x1200 / 1920x1080
    USB_DISP_CHIP_DL195,       // max 1920x1200 / 2048x1152
    USB_DISP_CHIP_DL1X5,       // Gen1.5 だが型番不明
    // MCT Trigger 6 (T6-688SL)
    USB_DISP_CHIP_T6,
    // MacroSilicon
    USB_DISP_CHIP_MS912X,      // MS912x 世代 (534D:6021 / 345F:9132, UYVY)
    USB_DISP_CHIP_MS913X,      // MS913x 世代 (345F:9133, RGB24, 要キープアライブ)
} usb_disp_chip_t;


// ピクセル形式 (usb_disp_update の fmt 引数 / usb_disp_set_depth の値)
typedef enum {
    USB_DISP_FMT_RGB565 = 16,   // 2 バイト/px (uint16_t)
    USB_DISP_FMT_RGB888 = 24,   // 3 バイト/px (メモリ順 B,G,R)
} usb_disp_fmt_t;


// 解像度の自動選択で EDID をどう使うか (usb_disp_config_t.edid_policy)
typedef enum {
    // 既定: EDID が対応する解像度のうち、チップ上限に収まる最大のものを選ぶ
    // CEA-861 拡張ブロックの VIC / DTD も候補に入れる
    USB_DISP_EDID_POLICY_MAX = 0,
    // ベースブロックの preferred timing (モニタのネイティブ解像度) を優先。
    // 拡張ブロックは見ない。パネルの実解像度で等倍表示したい場合や、
    // 表示側のスケーラを通したくない場合はこちら
    USB_DISP_EDID_POLICY_PREFERRED,
} usb_disp_edid_policy_t;


// ビデオモード (タイミング一式) usb_disp_set_mode_ex() に渡す
typedef struct {
    uint16_t width, height;    // アクティブ解像度
    uint32_t pclk_khz;         // ピクセルクロック [kHz]
    uint16_t hfp, hsync, hbp;  // 水平 front porch / sync / back porch
    uint16_t vfp, vsync, vbp;  // 垂直 front porch / sync / back porch
} usb_disp_mode_t;


// ポート設定 (usb_disp_add_cfg)
//  width=0 で接続時に解像度を自動選択
//  チップのピクセル数上限に収まらなければ内蔵モードリストの大きい順にフォールバック
//
// フィールドは全プラットフォームで共通
//  port の意味はバックエンドごとに違う:
//  - Pico: 専用 PIO ブロック番号 0..2 (1ポート = 1ブロック占有。RP2040 は 0..1)
//      pin_dp/pin_dm も Pico のみ有効。他プラットフォームは読み飛ばし。
//  - ESP32: USB-OTG コントローラ番号。現状 0 のみ (0 以外は登録エラー)。
//      P4 の 2系統目 (1 = USB 1.1 OTG FS) は現在未対応 (今後対応予定)
//  - Teensy 4.x: 0 のみ
//      USB ホストポート = 4.1 のホストヘッダ / 4.0 は裏面パッド
//  - PC (libusb): 対応デバイスの発見順リストの番号 (port=0 が1台目)
//      チップ種別では分けず、対応する全デバイス (DL-1xx / T6 / MS91xx)
//      が同じリストに混在する。DL-165 と T6 を同時に挿せば発見順に
//      0, 1 が振られる
//

typedef struct {
    uint8_t port;           // ホストコントローラ番号
    uint8_t pin_dp;         // [Pico] D+ の GPIO 番号
    uint8_t pin_dm;         // [Pico] D- の GPIO 番号
                            // pin_dp と隣接必須・順序は自由
                            // 非隣接は登録エラー (NULL が返る)
    uint16_t width;         // 接続時に設定する解像度 (0 = 自動選択)
    uint16_t height;
    uint8_t refresh_hz;     // リフレッシュレート (0 = 60)
    bool no_auto_mode;      // true:接続時のモード自動設定を行わない
                            //      (アプリが set_mode 群を自分で呼ぶ)
    bool shadow_fb;         // true:接続時にシャドウFB (差分更新) を有効化
                            //      メモリが確保できない環境では無効のまま動く
                            //      (usb_disp_set_shadow 参照)
    bool depth24;           // true:24bit カラー (RGB888) で動作する。
                            //      チップ/経路が非対応なら 16bit のまま動く
                            //      (実際の深度は usb_disp_depth() で確認)
    bool ignore_edid;       // true:EDID をライブラリ側から一切読まない。
                            //      モードは width/height だけで決め、
                            //      EDID による自動選択を行わない。
                            //      指定解像度を強制したい場合に使う。
                            //      アプリが明示的に呼ぶ usb_disp_read_edid()
                            //      は影響を受けない (情報表示用に読める)
    usb_disp_edid_policy_t edid_policy;   // 自動選択のポリシー (既定 = MAX)
} usb_disp_config_t;


// ---- ライフサイクル ----

// サブシステム初期化 (最初に一度)
void usb_disp_init(void);

// ディスプレイポートを登録。usb_disp_start() の前に呼ぶ
// cfg はコピーされるのでスタック上の一時変数でよい
// 戻り値: ハンドル (上限到達で NULL)
usb_disp_t *usb_disp_add_cfg(const usb_disp_config_t *cfg);

#ifdef __cplusplus
#if USB_DISP_PORT_PICO
usb_disp_t *usb_disp_add(uint8_t port, uint8_t pin_dp, uint8_t pin_dm,
                         uint16_t width = 0, uint16_t height = 0,
                         bool ignore_edid = false);
#else
// Pico 以外はホストのピンが固定 → pin_dp/pin_dm も省略可
usb_disp_t *usb_disp_add(uint8_t port, uint8_t pin_dp = 0, uint8_t pin_dm = 0,
                         uint16_t width = 0, uint16_t height = 0,
                         bool ignore_edid = false);
#endif
#else
// C では 6 引数フル指定 (width=0, height=0 が自動選択)
usb_disp_t *usb_disp_add(uint8_t port, uint8_t pin_dp, uint8_t pin_dm,
                         uint16_t width, uint16_t height, bool ignore_edid);
#endif

// 登録済み全ポートのホストを起動 (Pico: core1 常駐)。add 群の後に一度呼ぶ。
// arduino-pico でスケッチが setup1()/loop1() を定義している場合は core1 を
// 起動できないため、自動で手動モード (下記) に切り替わる (ログに案内が出る)
void usb_disp_start(void);

// 手動サービスモード (Pico のみ):
//   usb_disp_start() の代わりに usb_disp_start_manual() を呼び、以後
//   usb_disp_task() を専有できるコンテキストから休みなく呼び続ける。
//   arduino-pico なら
//     void loop1() { usb_disp_task(); }
//   が定石 (core1 で回る。loop1 に他の処理を混ぜないこと。SOF 1ms 維持が
//   必要なため、呼び出し間隔が空くとデバイスがサスペンドする)。
// ESP32 / PC では start_manual は start と同義、task は no-op
// (共通ソースがそのままビルドできるようにするための空実装)
void usb_disp_start_manual(void);
void usb_disp_task(void);

uint8_t usb_disp_count(void);
usb_disp_t *usb_disp_at(uint8_t idx);
uint8_t usb_disp_index(usb_disp_t *d);

// 各ディスプレイを定期的にポーリング。接続/切断/エニュメレーションを処理。
// READY へ変化 / 切断 / 遅延して読めた EDID による解像度切替で true を返す
// (呼び出し側で再描画等のトリガに使う)
bool usb_disp_poll(usb_disp_t *d);

// ---- 状態 ----
bool usb_disp_ready(usb_disp_t *d);
uint16_t usb_disp_width(usb_disp_t *d);
uint16_t usb_disp_height(usb_disp_t *d);
uint16_t usb_disp_vid(usb_disp_t *d);
uint16_t usb_disp_pid(usb_disp_t *d);
uint64_t usb_disp_stat_bytes(usb_disp_t *d);  // 累積バルク送信バイト数
#if USB_DISP_PORT_PICO
usb_disp_udh_host_t *usb_disp_get_host(usb_disp_t *d);  // 統計アクセス用 (Pico のみ)
#endif

// ---- チップ判別 (エニュメレーション完了時に自動実行) ----
usb_disp_chip_t usb_disp_chip(usb_disp_t *d);
uint32_t usb_disp_max_area(usb_disp_t *d);          // gen1.5: ピクセル数上限 (0=不明)
const char *usb_disp_chip_name(usb_disp_t *d);      // "DL-165" 等 (SKU 未判別は
                                                    //  "DL-1xx" 等のプロトコル名、
                                                    //  それも不明なら "???")

// ---- 製品型番判別 (VID/PID 照合) ----
// チップ判別とは独立に、既知製品の型番文字列 ("BUFFALO GX-DVI/U2" 等) を
// 返す。リストは usb_disp_model.h (実機確認済みの製品のみ登録)。
// 戻り値: 型番文字列 (リストに無い組は NULL)
const char *usb_disp_model_name(uint16_t vid, uint16_t pid);
// 接続中デバイス版 (未接続・リストに無い場合は NULL)
const char *usb_disp_model(usb_disp_t *d);

// ---- モード設定 (READY 後) ----
// いずれもチップのピクセル数上限 (max_area) を超えるモードは拒否する
// 60Hz で内蔵リストに一致があれば VESA/CEA タイミング、無ければ
// CVT-RB (Reduced Blanking) 計算で任意解像度のタイミングを生成する
bool usb_disp_set_mode(usb_disp_t *d, uint16_t width, uint16_t height);
bool usb_disp_set_mode_hz(usb_disp_t *d, uint16_t width, uint16_t height,
                          uint8_t refresh_hz);
bool usb_disp_set_mode_ex(usb_disp_t *d, const usb_disp_mode_t *mode);
// 解像度の自動選択 (poll が接続時に呼ぶもの)
//   edid_policy = MAX       : EDID 記載の最大解像度 → 内蔵リスト大きい順
//   edid_policy = PREFERRED : EDID preferred → 内蔵リスト大きい順
//   ignore_edid = true      : EDID を読まず内蔵リスト大きい順のみ
bool usb_disp_set_auto_mode(usb_disp_t *d);

// ---- EDID の使い方 ----
// 自動選択ポリシーの変更 (接続前でも READY 中でも可)
// 既に決まったモードは変わらないので、その場で反映したければ
// 続けて usb_disp_set_auto_mode() を呼ぶこと
void usb_disp_set_edid_policy(usb_disp_t *d, usb_disp_edid_policy_t policy);
usb_disp_edid_policy_t usb_disp_edid_policy(usb_disp_t *d);

// usb_disp_config_t.ignore_edid と同じ設定を後から変更する
// (接続前でも READY 中でも可。READY 中に有効化しても既に決まった
//  モードは変わらないので、必要なら usb_disp_set_mode() を呼び直すこと)。
void usb_disp_set_ignore_edid(usb_disp_t *d, bool on);
bool usb_disp_ignore_edid(usb_disp_t *d);

// 内蔵モードリスト (60Hz, VESA DMT / CEA)
uint8_t usb_disp_builtin_mode_count(void);
const usb_disp_mode_t *usb_disp_builtin_mode(uint8_t idx);

// ---- カラー深度 (既定 16bit = RGB565) ----
// READY 中に切り替えるとモード再設定 (画面クリア) を伴う
// 戻り値: 要求深度で動作できたか (非対応チップへの 24 要求は false で 16bit のまま)
// 実際の深度は usb_disp_depth() で確認
bool usb_disp_set_depth(usb_disp_t *d, uint8_t bits);   // 16 or 24
                        // (USB_DISP_FMT_RGB565/888 をそのまま渡してもよい)
uint8_t usb_disp_depth(usb_disp_t *d);

// 現在のモード (タイミング込み) を取得。モード未設定なら false。
bool usb_disp_current_mode(usb_disp_t *d, usb_disp_mode_t *out);
// 出力リフレッシュレート [Hz] (タイミングから計算、四捨五入。未設定は 0)
// マイコン側の描画レートとは独立 (チップは内部FBから常時この周期で走査出力)
uint16_t usb_disp_refresh_hz(usb_disp_t *d);

// ---- 操作 (READY 後) ----
// update/fill は実解像度 (usb_disp_width/height) で右端・下端を
// クリッピングする: はみ出した矩形は画面内の部分だけ描かれ、
// 完全に画面外なら何もしない (true を返す)。
// 矩形更新は3形態:
//   usb_disp_update(..., fmt)  : fmt でピクセル形式を選ぶ汎用形。
//                                C++ では fmt 省略可 (= RGB565)
//   usb_disp_update_565(...)   : RGB565 固定 (uint16_t*)
//   usb_disp_update_888(...)   : RGB888 固定 (uint8_t*, メモリ順 B,G,R =
//                                LVGL の LV_COLOR_FORMAT_RGB888 と同じ並び)
// stride_px はソース配列の1行あたりピクセル数 (矩形幅と同じなら w を渡す。
// 0 は「全行が先頭行の繰り返し」= 1行分のバッファで単色帯などを描ける)。
// いずれも表示側の深度 (usb_disp_set_depth) と独立に使える。
// 深度と形式が異なる場合はライブラリが変換するので、
// 「GUI は 565、写真領域だけ 888」のような混在も可能
bool usb_disp_update_565(usb_disp_t *d, uint16_t x, uint16_t y, uint16_t w,
                         uint16_t h, const uint16_t *rgb565,
                         uint32_t stride_px);
bool usb_disp_update_888(usb_disp_t *d, uint16_t x, uint16_t y, uint16_t w,
                         uint16_t h, const uint8_t *px, uint32_t stride_px);
#ifdef __cplusplus
bool usb_disp_update(usb_disp_t *d, uint16_t x, uint16_t y, uint16_t w,
                     uint16_t h, const void *px, uint32_t stride_px,
                     usb_disp_fmt_t fmt = USB_DISP_FMT_RGB565);
#else
bool usb_disp_update(usb_disp_t *d, uint16_t x, uint16_t y, uint16_t w,
                     uint16_t h, const void *px, uint32_t stride_px,
                     usb_disp_fmt_t fmt);
#endif
bool usb_disp_fill(usb_disp_t *d, uint16_t x, uint16_t y, uint16_t w,
                  uint16_t h, uint16_t color);
bool usb_disp_flush(usb_disp_t *d, uint32_t timeout_ms);

// 画面内矩形コピー (DL の COPY16 コマンド、ピクセル再送なし)
// スクロールや矩形移動に。重なりは行順/分割で自動処理。読み出しは不可
bool usb_disp_copy(usb_disp_t *d, uint16_t sx, uint16_t sy, uint16_t dx,
                   uint16_t dy, uint16_t w, uint16_t h);

// EDID 読み出し (先頭から len バイト)。読めたバイト数を返す (0 = 読めず)
// EDID は 128B のベースブロック + 拡張ブロック (個数は byte 126) から成る
// 全体を取るなら len = 128 * (1 + buf[126]) で読み直すか、下の _at を使う
// DL-1xx はレジスタのオフセットが 8bit なので 256 バイトが読み出し上限
uint16_t usb_disp_read_edid(usb_disp_t *d, uint8_t *buf, uint16_t len);
// 同上、offset バイト目から読む版 (拡張ブロックの読み出し用)
uint16_t usb_disp_read_edid_at(usb_disp_t *d, uint16_t offset, uint8_t *buf,
                               uint16_t len);
// EDID の総バイト数 (拡張ブロック込み。0 = 読めない / ignore_edid)
uint16_t usb_disp_edid_size(usb_disp_t *d);
// 接続先が EDID でこの解像度への対応を明示しているか
// ベースブロック (established / standard / DTD1-4) に加え、CEA-861 拡張
// ブロックの Video Data Block (VIC) と DTD も見る
// EDID が読めない・記載が無い・ignore_edid のときは false
// 「指定解像度を出してよいか」をアプリ側で判断するのに使う
bool usb_disp_edid_supports(usb_disp_t *d, uint16_t width, uint16_t height);
// 接続先が EDID で申告するモードのうち、チップ上限に収まる最大の解像度
// edid_policy = MAX の自動選択が選ぶものと同じ
// 「この解像度を出して大丈夫か」をアプリ側で判断するのに使う
// (これ以下なら、明示の記載が無くても表示側がスケーリングで受けられる
//  ことが多い)。EDID が読めない / 収まるものが無い / ignore_edid は false
bool usb_disp_edid_max_mode(usb_disp_t *d, uint16_t *width, uint16_t *height);
bool usb_disp_blank(usb_disp_t *d, bool on);
void usb_disp_force_reenum(usb_disp_t *d);

// ---- シャドウFB (差分更新) ----
// スパン更新型プロトコル (DisplayLink DL-1xx) 専用。
// フルフレーム型 (T6/MS91xx) では効果がないため有効にならない
// (READY 中の有効化要求は false を返す。接続前の要求は接続時に
//  "shadow FB not applicable" をログして無効のまま)。
// 有効にすると解像度と同サイズのシャドウFBを usb_disp_hal_fb_alloc
// (ESP32=PSRAM / PC=malloc / Pico=非対応) で確保し、update/fill は
// シャドウと比較して「変化した行の変化した区間」だけを送る
// 静止部分の多い画面で実効フレームレートが大きく向上する
// 有効化時は画面とシャドウを黒で同期する (一瞬黒になる)
// メモリが確保できなければ false を返し従来動作のまま
// モード変更時は自動で再確保・再同期される
bool usb_disp_set_shadow(usb_disp_t *d, bool on);
bool usb_disp_shadow_active(usb_disp_t *d);
// デバッグ用: シャドウFBの行先頭ポインタ (無効時 NULL。24bit 動作中は
// シャドウが 3B/px になり uint16_t ビューが合わないため常に NULL)。
// 読み出し専用で使うこと
const uint16_t *usb_disp_shadow_row(usb_disp_t *d, uint16_t row);

// 対応チップの VID/PID か (HAL のデバイス走査用。アプリからも使用可)
bool usb_disp_supported_device(uint16_t vid, uint16_t pid);

// ---- ログ ----
// 既定ではログは出ない。出したい場合
//   - Arduino: usb_disp_set_log(true) で Serial へ出るようになる
//   - 全プラットフォーム共通: usb_disp_log() をアプリで定義すると
//     完全に差し替えられる (weak 上書き。この場合 set_log は無関係)
void usb_disp_set_log(bool on);
void usb_disp_log(const char *fmt, ...);

#ifdef __cplusplus
}
#endif

// ---- Arduino 用の自動グルー ----
// スケッチが LovyanGFX / LVGL を include している場合に限り、追加の
// include なしで連携クラス/ヘルパーが使えるようにする:
//   - LovyanGFX: LGFX_USB_Disp (パネルアダプタ)
//   - LVGL v9  : usb_disp_lvgl_create() (画面/バッファ/flush_cb 一括セットアップ)
#if defined(ARDUINO) && defined(__cplusplus)
  #if __has_include(<LovyanGFX.hpp>)
    #include "lgfx/Panel_USB_Disp.hpp"
  #endif
  #if __has_include(<lvgl.h>)
    #include "usb_disp_lvgl.h"
  #endif
#endif

#endif // USB_DISP_H_


