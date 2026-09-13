//
// ######################################################################
//
//    usb_disp_hal_esp32 - ESP32-S2/S3/P4 バックエンド
//
//    ESP-IDF の usb_host ライブラリ (DWC_OTG ハードウェアホスト) を
//    usb_disp_hal インターフェースで包む。
//    エニュメレーションは usb_host スタックが行う。
//      - デーモン/クライアントタスクの運転
//      - NEW_DEV でディスクリプタを読みバルク OUT EP を構成
//      - コントロール転送とバルク OUT リング (4 x 8KB) の提供
//    DL プロトコルはコア (usb_disp.cpp) がそのまま動く。
//
//    Copyright (C) 2026
//      Hideto Kikuchi / PJラボ (@pcjpnet) - https://pc-jp.net/
//
// ######################################################################
//

#include "usb_disp_hal.h"

#if USB_DISP_PORT_ESP32

#include <stdio.h>
#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "esp_timer.h"
#include "esp_heap_caps.h"
#include "usb/usb_host.h"

#define USB_DISP_BULK_XFER_COUNT 4
#define USB_DISP_BULK_XFER_SIZE 8192
#define USB_DISP_CTRL_MAX_DATA 512
#define USB_DISP_CTRL_TIMEOUT_MS 1000

// ホスト起動前の切断期間 [ms] (usb_disp_hal_start のコメント参照)
#ifndef USB_DISP_ESP32_SETTLE_MS
#define USB_DISP_ESP32_SETTLE_MS 200
#endif

struct usb_disp_hal {
    bool in_use;

    // デバイス
    usb_device_handle_t dev;
    volatile bool scan_needed;       // NEW_DEV 通知 → バス上の全デバイス走査
    volatile bool gone;              // DEV_GONE 通知 (自分のデバイス)
    uint32_t scan_retry_ms;          // 開けなかったデバイスの再走査時刻 (0=なし)
    uint8_t scan_retry_cnt;          // 再走査の残り試行回数 (NEW_DEV で補充)
    volatile bool attached;
    uint16_t vid, pid;
    uint8_t bulk_ep;
    uint16_t bulk_mps;
    uint8_t iface;
    bool iface_claimed;
    uint32_t urb_max;    // 1 URB の最大バイト (通常 USB_DISP_BULK_XFER_SIZE)
    volatile bool ep_recover;        // バルクEPエラー → パイプ復旧要求
    volatile uint32_t ep_recover_cnt;
    volatile bool pending_probe;     // 他コンフィグ探索をアプリタスクで実行
    uint8_t probe_reenum_cnt;        // コンフィグ切替→再列挙の試行回数
    bool full_speed;
    uint8_t vdesc[64];               // config 内 0x5F ベンダーディスクリプタ
    uint8_t vdesc_len;

    // コントロール転送 (直列化)
    usb_transfer_t *ctrl_xfer;
    SemaphoreHandle_t ctrl_mutex;
    SemaphoreHandle_t ctrl_done;

    // バルク OUT リング。単一エンドポイントのバルク転送は投入順に
    // 完了するので、空きスロットはラウンドロビンで一意に決まる
    usb_transfer_t *bulk_xfer[USB_DISP_BULK_XFER_COUNT];
    SemaphoreHandle_t bulk_free;  // カウンティング (空きスロット数)
    uint8_t next_slot;            // 次に使うスロット番号
    usb_transfer_t *cur;          // 書き込み中スロット (未サブミット)
    uint32_t cur_fill;

    // 統計 (バルク完了コールバックで更新)
    volatile uint32_t bulk_err;       // status != COMPLETED の完了数
    volatile uint32_t bulk_short;     // actual < num_bytes の完了数
    volatile int16_t last_err_status; // 直近のエラー status (enum 値)
    uint64_t stat_bytes;              // 累積バルク送信バイト数
};

static struct usb_disp_hal s_hal[USB_DISP_MAX];
static uint8_t s_nhal = 0;
static usb_host_client_handle_t s_client;
static bool s_started = false;

uint32_t usb_disp_hal_ms(void) {
    return (uint32_t)(esp_timer_get_time() / 1000);
}

// ---------------------------------------------------------------
// 転送コールバック (usb_host クライアントタスクのコンテキスト)
// ---------------------------------------------------------------

static void ctrl_xfer_cb(usb_transfer_t *xfer) {
    struct usb_disp_hal *h = (struct usb_disp_hal *)xfer->context;
    xSemaphoreGive(h->ctrl_done);
}

static void bulk_xfer_cb(usb_transfer_t *xfer) {
    struct usb_disp_hal *h = (struct usb_disp_hal *)xfer->context;
    if (xfer->status != USB_TRANSFER_STATUS_COMPLETED) {
        // volatile への ++ は C++20 で非推奨 (-Wvolatile) のため読み書きを分ける
        h->bulk_err = h->bulk_err + 1;
        h->last_err_status = (int16_t)xfer->status;
        // エラーでパイプは HALT 状態になり以後の submit が
        // ESP_ERR_INVALID_STATE で全滅する → client_task に復旧を頼む
        // (CANCELED は復旧処理自身の flush によるものなので除く)
        if (xfer->status != USB_TRANSFER_STATUS_CANCELED) h->ep_recover = true;
        if (h->bulk_err <= 16 || (h->bulk_err & 0x3F) == 0) {
            usb_disp_log("[HAL] bulk error: status=%d (n=%d/%d, total err=%lu)",
                         (int)xfer->status, xfer->actual_num_bytes,
                         xfer->num_bytes, (unsigned long)h->bulk_err);
        }
    } else if (xfer->actual_num_bytes < xfer->num_bytes) {
        h->bulk_short = h->bulk_short + 1;
        usb_disp_log("[HAL] bulk short: %d/%d", xfer->actual_num_bytes,
                     xfer->num_bytes);
    }
    xSemaphoreGive(h->bulk_free);
}

// ---------------------------------------------------------------
// コントロール転送 (内部共通。attached 前のエニュメ診断でも使う)
// ---------------------------------------------------------------

static bool ctrl_common(struct usb_disp_hal *h, const uint8_t setup[8],
                        void *data, uint16_t *actual) {
    if (h->ctrl_xfer == NULL) return false;
    uint16_t wLength = (uint16_t)(setup[6] | (setup[7] << 8));
    if (wLength > USB_DISP_CTRL_MAX_DATA) return false;
    bool dir_in = (setup[0] & 0x80) != 0;

    if (xSemaphoreTake(h->ctrl_mutex,
                       pdMS_TO_TICKS(USB_DISP_CTRL_TIMEOUT_MS)) != pdTRUE)
        return false;

    usb_transfer_t *x = h->ctrl_xfer;
    memcpy(x->data_buffer, setup, 8);
    if (!dir_in && wLength && data) memcpy(x->data_buffer + 8, data, wLength);
    x->num_bytes = 8 + wLength;

    xSemaphoreTake(h->ctrl_done, 0);  // 念のためクリア
    bool ok = (usb_host_transfer_submit_control(s_client, x) == ESP_OK);
    if (ok) {
        ok = (xSemaphoreTake(h->ctrl_done,
                             pdMS_TO_TICKS(USB_DISP_CTRL_TIMEOUT_MS)) ==
              pdTRUE);
    }
    if (ok && x->status != USB_TRANSFER_STATUS_COMPLETED) {
        usb_disp_log("[HAL] ctrl error: status=%d (bReq=%02X)", (int)x->status,
                     setup[1]);
        ok = false;
    }
    if (ok) {
        uint16_t got =
            (x->actual_num_bytes >= 8) ? (uint16_t)(x->actual_num_bytes - 8)
                                       : 0;
        if (dir_in && data && got) memcpy(data, x->data_buffer + 8, got);
        if (actual) *actual = got;
    }
    xSemaphoreGive(h->ctrl_mutex);
    return ok;
}

static bool raw_ctrl(struct usb_disp_hal *h, uint8_t bmRequestType,
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
    return ctrl_common(h, setup, data, actual);
}

// ---------------------------------------------------------------
// デバイス接続/切断 (クライアントタスクから呼ぶ)
// ---------------------------------------------------------------

static void dump_hex(const char *tag, const uint8_t *buf, uint16_t len) {
    if (len > 192) len = 192;
    for (uint16_t i = 0; i < len; i += 16) {
        char hex[16 * 3 + 1];
        int n = 0;
        for (uint16_t j = i; j < i + 16 && j < len; j++)
            n += snprintf(hex + n, sizeof(hex) - n, "%02X ", buf[j]);
        usb_disp_log("[ENUM] %s %02X: %s", tag, i, hex);
    }
}

static void finish_setup(struct usb_disp_hal *h, const uint8_t *scan,
                         uint16_t scan_len, bool full_speed);

// コンフィグディスクリプタ列に vendor class (0xFF) のインターフェースが
// あるか
static bool cfg_has_vendor_if(const uint8_t *blob, uint16_t len) {
    const uint8_t *p = blob;
    const uint8_t *end = blob + len;
    while (p + 1 < end && p[0] >= 2 && p + p[0] <= end) {
        if (p[1] == 0x04 && p[0] >= 9 && p[5] == 0xFF) return true;
        p += p[0];
    }
    return false;
}

// コンフィグディスクリプタ列から採用するバルク OUT の EP 記述子 (7バイト)を返す
// (finish_setup と同じ方針: alt0 のみ・vendor class IF 優先)
static const uint8_t *find_bulk_out_ep(const uint8_t *blob, uint16_t len) {
    const uint8_t *p = blob;
    const uint8_t *end = blob + len;
    const uint8_t *found = NULL;
    uint8_t cur_alt = 0;
    bool cur_vendor = false, got_vendor = false;
    while (p + 1 < end && p[0] >= 2 && p + p[0] <= end) {
        if (p[1] == 0x04 && p[0] >= 9) {  // INTERFACE
            cur_alt = p[3];
            cur_vendor = (p[5] == 0xFF);
        } else if (p[1] == 0x05 && p[0] >= 7) {  // ENDPOINT
            if ((p[3] & 0x03) == 0x02 && (p[2] & 0x80) == 0 && cur_alt == 0 &&
                (found == NULL || (cur_vendor && !got_vendor))) {
                found = p;
                got_vendor = cur_vendor;
            }
        }
        p += p[0];
    }
    return found;
}

// セットアップ前半 (client_task から呼ぶ): デバイスを開いてディスクリプタを確認する。
// ハブ (class 09、スタックが内部処理する) と非 DisplayLink は開かずに閉じて false。
// アクティブコンフィグに vendor class IF があれば、そのまま finish_setup まで完了する。
// 無い場合 (DisplayLink オートインストール機は Mass Storage だけのコンフィグで列挙される) は、
// 他コンフィグの生読みが必要になるが、コントロール転送の完了イベントを処理するのは
// client_task 自身なのでここではブロックできない → 
// pending_probe を立てて usb_disp_hal_poll(アプリタスク) に後半を任せる
// 戻り値: true = このデバイスを掴んだ (h->dev != NULL のまま)
static bool device_setup(struct usb_disp_hal *h, uint8_t addr) {
    esp_err_t err = usb_host_device_open(s_client, addr, &h->dev);
    if (err != ESP_OK) {
        // ESP_ERR_INVALID_STATE: まだ列挙中か切断処理中のデバイス。
        // (arduino-esp32 3.3.11 = IDF のハブサポート有効ビルドでは
        //  "usbh_devs_open error: ESP_ERR_INVALID_STATE" の E ログも出るが、
        //  一時的な状態で害はない)
        // 列挙完了時の NEW_DEV で拾い直せるが、イベントを先に消費して
        // しまった場合の取りこぼし対策として時限再走査も仕掛けておく
        usb_disp_log("[HAL] device_open failed (addr=%u err=0x%X)", addr,
                     (unsigned)err);
        h->dev = NULL;
        if (err == ESP_ERR_INVALID_STATE && h->scan_retry_cnt > 0) {
            h->scan_retry_cnt--;
            h->scan_retry_ms = usb_disp_hal_ms() + 250;
        }
        return false;
    }
    const usb_device_desc_t *ddesc;
    const usb_config_desc_t *cdesc;
    if (usb_host_get_device_descriptor(h->dev, &ddesc) != ESP_OK ||
        usb_host_get_active_config_descriptor(h->dev, &cdesc) != ESP_OK) {
        usb_disp_log("[HAL] descriptor read failed");
        usb_host_device_close(s_client, h->dev);
        h->dev = NULL;
        return false;
    }
    if (ddesc->bDeviceClass == 0x09) {  // ハブ: スタックが下流を列挙する
        usb_disp_log("[ENUM] addr=%u hub %04X:%04X -> stack handles, "
                     "waiting for downstream", addr, ddesc->idVendor,
                     ddesc->idProduct);
        usb_host_device_close(s_client, h->dev);
        h->dev = NULL;
        return false;
    }
    if (!usb_disp_supported_device(ddesc->idVendor, ddesc->idProduct)) {
        // 非対応デバイス (ハブ同居機器など)
        usb_disp_log("[ENUM] addr=%u ignoring unsupported %04X:%04X", addr,
                     ddesc->idVendor, ddesc->idProduct);
        usb_host_device_close(s_client, h->dev);
        h->dev = NULL;
        return false;
    }
    h->vid = ddesc->idVendor;
    h->pid = ddesc->idProduct;

    usb_device_info_t dinfo;
    h->full_speed = true;
    if (usb_host_device_info(h->dev, &dinfo) == ESP_OK) {
        h->full_speed = (dinfo.speed != USB_SPEED_HIGH);
    }
    usb_disp_log("[ENUM] VID=%04X PID=%04X speed=%s ncfgs=%u cfg total=%u",
                 h->vid, h->pid, h->full_speed ? "FS" : "HS",
                 ddesc->bNumConfigurations, cdesc->wTotalLength);

    // コントロール転送は EP0 なので claim 前から使える
    if (usb_host_transfer_alloc(8 + USB_DISP_CTRL_MAX_DATA, 0,
                                &h->ctrl_xfer) != ESP_OK) {
        usb_disp_log("[HAL] ctrl transfer alloc failed");
        return true;  // 掴んだまま (切断まで放置)
    }
    h->ctrl_xfer->device_handle = h->dev;
    h->ctrl_xfer->bEndpointAddress = 0;
    h->ctrl_xfer->callback = ctrl_xfer_cb;
    h->ctrl_xfer->context = h;

    // コンフィグディスクリプタ全体をダンプ (複合デバイスの切り分け用)
    dump_hex("cfg", (const uint8_t *)cdesc, cdesc->wTotalLength);

    if (!cfg_has_vendor_if((const uint8_t *)cdesc, cdesc->wTotalLength) &&
        ddesc->bNumConfigurations > 1) {
        usb_disp_log("[ENUM] no vendor IF in active cfg, probing others...");
        h->pending_probe = true;  // 続きは usb_disp_hal_poll で
        return true;
    }
    finish_setup(h, (const uint8_t *)cdesc, cdesc->wTotalLength,
                 h->full_speed);
    return true;
}

// バス上の全デバイスを走査して DisplayLink を探す (client_task から呼ぶ)。
// ハブ経由では NEW_DEV がハブや同居デバイスにも飛ぶため、通知アドレスを
// 直接使わず毎回リストを引き直す (取り逃しも再走査で拾える)
static void scan_devices(struct usb_disp_hal *h) {
    uint8_t addrs[8];
    int n = 0;
    if (usb_host_device_addr_list_fill((int)sizeof(addrs), addrs, &n) !=
        ESP_OK)
        return;
    for (int i = 0; i < n && h->dev == NULL; i++) {
        device_setup(h, addrs[i]);
    }
}

// セットアップ中間 (アプリタスクから呼ぶ): 全コンフィグを生読みして
// vendor class IF を持つコンフィグを探し、SET_CONFIGURATION で切り替えて
// から finish_setup する。見つからなければアクティブコンフィグのまま
static void probe_and_finish(struct usb_disp_hal *h) {
    const usb_device_desc_t *ddesc;
    const usb_config_desc_t *cdesc;
    if (usb_host_get_device_descriptor(h->dev, &ddesc) != ESP_OK ||
        usb_host_get_active_config_descriptor(h->dev, &cdesc) != ESP_OK)
        return;

    static uint8_t alt_cfg[256];
    const uint8_t *scan = (const uint8_t *)cdesc;
    uint16_t scan_len = cdesc->wTotalLength;
    for (uint8_t ci = 0; ci < ddesc->bNumConfigurations && ci < 4; ci++) {
        uint16_t actual = 0;
        uint8_t hdr[9];
        if (!raw_ctrl(h, 0x80, 0x06, (uint16_t)(0x0200 + ci), 0, hdr, 9,
                      &actual) || actual < 9) {
            usb_disp_log("[ENUM] cfg[%u] read failed", ci);
            continue;
        }
        uint16_t total = (uint16_t)(hdr[2] | (hdr[3] << 8));
        if (total > sizeof(alt_cfg)) total = sizeof(alt_cfg);
        if (!raw_ctrl(h, 0x80, 0x06, (uint16_t)(0x0200 + ci), 0, alt_cfg,
                      total, &actual) || actual < total) {
            usb_disp_log("[ENUM] cfg[%u] full read failed", ci);
            continue;
        }
        char tag[8];
        snprintf(tag, sizeof(tag), "cfg[%u]", ci);
        dump_hex(tag, alt_cfg, total);
        if (cfg_has_vendor_if(alt_cfg, total)) {
            uint8_t value = alt_cfg[5];  // bConfigurationValue
            usb_disp_log("[ENUM] vendor IF in cfg[%u] (value=%u), "
                         "switching config", ci, value);
            if (raw_ctrl(h, 0x00, 0x09, value, 0, NULL, 0, NULL)) {
                scan = alt_cfg;
                scan_len = total;
            } else {
                usb_disp_log("[ENUM] SET_CONFIGURATION(%u) failed", value);
            }
            break;
        }
    }

    // usb_host スタックはエニュメ時のコンフィグでしかパイプを作れないため、
    // このままでは切替先の EP へ転送できない (Get EP handle error)。
    // デバイスのタイプ別に対処する:
    //   a) ZeroCD 型 (一度アクティブ化すると MSC コンフィグを引っ込める):
    //      コンフィグ index 0 に表示 IF が見えるようになる → 再列挙して
    //      正攻法 (スタックが表示コンフィグでパイプを作る) に乗せ直す
    //   b) コンフィグ切替型 (GX-DVI/U2AI で実測。SET_CONFIGURATION が
    //      アクティブ化そのもので、ディスクリプタは変わらない):
    //      再列挙してもスタックはまた MSC コンフィグを選んでしまう
    //      (enum filter はプリコンパイル済み usb_host ライブラリで
    //      CONFIG_USB_HOST_ENABLE_ENUM_FILTER_CALLBACK 無効のため使えない)。
    //      → スタックがキャッシュしているアクティブコンフィグ記述子の
    //      バルク OUT EP 記述子 (7B) を表示コンフィグのもので上書きして
    //      から claim する (claim はキャッシュから読むので、表示 EP の
    //      パイプが作られる)。MSC も EP も同サイズ記述子なので安全
    if (scan == alt_cfg) {
        if (h->probe_reenum_cnt < 2) {
            uint16_t actual = 0;
            uint8_t hdr[9];
            vTaskDelay(pdMS_TO_TICKS(100));  // デバイス側の構成変更を待つ
            static uint8_t cfg0[256];
            if (raw_ctrl(h, 0x80, 0x06, 0x0200, 0, hdr, 9, &actual) &&
                actual >= 9) {
                uint16_t total = (uint16_t)(hdr[2] | (hdr[3] << 8));
                if (total > sizeof(cfg0)) total = sizeof(cfg0);
                if (raw_ctrl(h, 0x80, 0x06, 0x0200, 0, cfg0, total,
                             &actual) && actual >= total &&
                    cfg_has_vendor_if(cfg0, total)) {
                    usb_disp_log("[ENUM] cfg[0] now has vendor IF -> "
                                 "re-enumerate");
                    h->probe_reenum_cnt++;
                    usb_disp_hal_request_reenum(h);
                    return;  // 再列挙後の device_setup が通常経路で完了
                }
            }
        }
        const uint8_t *disp_ep = find_bulk_out_ep(alt_cfg, scan_len);
        uint8_t *cache_ep = (uint8_t *)(uintptr_t)find_bulk_out_ep(
            (const uint8_t *)cdesc, cdesc->wTotalLength);
        if (disp_ep && cache_ep) {
            usb_disp_log("[ENUM] repipe: cached EP %02X (mps=%u) <- "
                         "display EP %02X (mps=%u)", cache_ep[2],
                         cache_ep[4] | (cache_ep[5] << 8), disp_ep[2],
                         disp_ep[4] | (disp_ep[5] << 8));
            memcpy(cache_ep, disp_ep, 7);
        } else {
            usb_disp_log("[ENUM] repipe failed (disp_ep=%d cache_ep=%d)",
                         disp_ep != NULL, cache_ep != NULL);
        }
    }
    finish_setup(h, scan, scan_len, h->full_speed);
}

// セットアップ後半: EP スキャン, claim, バルク確保, attached。
// scan/scan_len は使用するコンフィグディスクリプタ列
// (アクティブとは限らない, probe_and_finish が切り替えた場合はそのコンフィグ)
static void finish_setup(struct usb_disp_hal *h, const uint8_t *scan,
                         uint16_t scan_len, bool full_speed) {
    // 使用コンフィグからバルク OUT EP とそのインターフェースを探す。
    //  - alt setting 0 のみ対象 (claim は alt 0 で行うため)
    //  - vendor class (0xFF) のインターフェースを優先 (DisplayLink の表示機能。
    //  オートインストール用 Mass Storage (class 08) 等のバルク OUT を誤って掴まないように)
    //  - 途中の 0x5F ベンダーディスクリプタも捕捉 (チップ判別フォールバック)
    h->bulk_ep = 0;
    h->bulk_mps = 0;
    h->vdesc_len = 0;
    uint8_t cur_iface = 0, cur_alt = 0, cur_class = 0;
    bool cur_vendor_if = false;   // 現在の IF が vendor class か
    bool got_vendor_ep = false;   // 採用済み EP が vendor class IF のものか
    const uint8_t *p = scan;
    const uint8_t *end = p + scan_len;
    while (p + 1 < end && p[0] >= 2 && p + p[0] <= end) {
        uint8_t len = p[0], type = p[1];
        if (type == 0x04 && len >= 9) {  // INTERFACE
            cur_iface = p[2];
            cur_alt = p[3];
            cur_class = p[5];
            cur_vendor_if = (cur_class == 0xFF);
            usb_disp_log("[ENUM] if=%u alt=%u class=%02X eps=%u", cur_iface,
                         cur_alt, cur_class, p[4]);
        } else if (type == 0x05 && len >= 7) {  // ENDPOINT
            uint8_t ep_addr = p[2];
            uint8_t attr = p[3] & 0x03;
            uint16_t mps = (uint16_t)(p[4] | (p[5] << 8));
            if (attr == 0x02 && (ep_addr & 0x80) == 0 && cur_alt == 0 &&
                (h->bulk_ep == 0 || (cur_vendor_if && !got_vendor_ep))) {
                h->bulk_ep = ep_addr;
                h->bulk_mps = mps;
                h->iface = cur_iface;
                got_vendor_ep = cur_vendor_if;
            }
        } else if (type == 0x5F && h->vdesc_len == 0) {  // DL vendor desc
            uint8_t n = (len <= sizeof(h->vdesc)) ? len : sizeof(h->vdesc);
            memcpy(h->vdesc, p, n);
            h->vdesc_len = n;
            usb_disp_log("[ENUM] vendor desc (0x5F) in config, len=%u", len);
        }
        p += len;
    }
    if (h->bulk_ep == 0) {
        usb_disp_log("[ENUM] no bulk OUT endpoint");
        // デバイスは掴んだまま
        // (コアが VID を見て FAILED 判定できるように attached にはしない)。切断まで放置。
        return;
    }

    // FS なのに mps>64 を宣言する個体対策: FS のバルクパケット上限は 64。
    // DWC はディスクリプタの mps でパケット化するため、
    // URB を 64B 単位に分割して 1 URB = 1 パケット (<=64B) に抑える
    h->urb_max = USB_DISP_BULK_XFER_SIZE;
    if (full_speed && h->bulk_mps > 64) {
        usb_disp_log("[ENUM] quirk: FS but bulk mps=%u -> 64B URBs",
                     h->bulk_mps);
        h->urb_max = 64;
    }
    if (usb_host_interface_claim(s_client, h->dev, h->iface, 0) != ESP_OK) {
        usb_disp_log("[HAL] interface_claim failed (if=%u)", h->iface);
        return;
    }
    h->iface_claimed = true;

    for (uint8_t i = 0; i < USB_DISP_BULK_XFER_COUNT; i++) {
        if (usb_host_transfer_alloc(USB_DISP_BULK_XFER_SIZE, 0,
                                    &h->bulk_xfer[i]) != ESP_OK) {
            usb_disp_log("[HAL] bulk transfer alloc failed");
            return;
        }
        h->bulk_xfer[i]->device_handle = h->dev;
        h->bulk_xfer[i]->bEndpointAddress = h->bulk_ep;
        h->bulk_xfer[i]->callback = bulk_xfer_cb;
        h->bulk_xfer[i]->context = h;
    }

    h->cur = NULL;
    h->cur_fill = 0;
    h->next_slot = 0;
    h->ep_recover = false;
    h->ep_recover_cnt = 0;
    h->bulk_err = 0;
    h->bulk_short = 0;
    // 空きスロットカウンタを満杯に
    while (xSemaphoreTake(h->bulk_free, 0) == pdTRUE) {}
    for (uint8_t i = 0; i < USB_DISP_BULK_XFER_COUNT; i++)
        xSemaphoreGive(h->bulk_free);

    usb_disp_log("[ENUM] configured. bulk OUT=%02X mps=%u if=%u", h->bulk_ep,
                 h->bulk_mps, h->iface);
    h->probe_reenum_cnt = 0;
    h->attached = true;
}

static void device_teardown(struct usb_disp_hal *h) {
    h->attached = false;
    h->pending_probe = false;
    h->scan_retry_ms = 0;
    if (h->dev == NULL) return;
    // 未完了転送はスタックが DEV_GONE 時にエラー完了させる →
    // コールバックがセマフォを返すので少し待ってから解放する
    vTaskDelay(pdMS_TO_TICKS(50));
    for (uint8_t i = 0; i < USB_DISP_BULK_XFER_COUNT; i++) {
        if (h->bulk_xfer[i]) {
            usb_host_transfer_free(h->bulk_xfer[i]);
            h->bulk_xfer[i] = NULL;
        }
    }
    if (h->ctrl_xfer) {
        usb_host_transfer_free(h->ctrl_xfer);
        h->ctrl_xfer = NULL;
    }
    if (h->iface_claimed) {
        usb_host_interface_release(s_client, h->dev, h->iface);
        h->iface_claimed = false;
    }
    usb_host_device_close(s_client, h->dev);
    h->dev = NULL;
    h->vid = h->pid = 0;
    h->bulk_ep = 0;
    h->bulk_mps = 0;
    h->vdesc_len = 0;
    h->ep_recover = false;
    usb_disp_log("[HAL] device closed");
}

// ---------------------------------------------------------------
// タスク
// ---------------------------------------------------------------

static void client_event_cb(const usb_host_client_event_msg_t *msg,
                            void *arg) {
    struct usb_disp_hal *h = &s_hal[0];  // OTG 1系統 = 単一インスタンス
    (void)arg;
    switch (msg->event) {
    case USB_HOST_CLIENT_EVENT_NEW_DEV:
        // ハブ経由ではハブ自身や同居デバイスの分も飛んでくるので、
        // アドレスは覚えず「走査が必要」フラグだけ立てる
        h->scan_needed = true;
        h->scan_retry_cnt = 8;   // 列挙中デバイスの再走査試行を補充
        break;
    case USB_HOST_CLIENT_EVENT_DEV_GONE:
        // 自分が掴んでいるデバイスの切断のみ扱う
        // (ハブ経由では同居デバイスの抜き差しでも DEV_GONE が来る)
        if (h->dev != NULL && msg->dev_gone.dev_hdl == h->dev) {
            h->gone = true;
        }
        break;
    default:
        break;
    }
}

// バルクエラーで HALT したパイプを復旧する (client_task 内で実行)。
// halt→flush で未完了 URB が CANCELED 完了しコールバックがセマフォを返す。
// clear でパイプ再開+データトグルもリセットされる (エラーでデバイス側の
// トグルと不一致になり得るため、デバイス側にも CLEAR_FEATURE を送る)
static void bulk_ep_recover(struct usb_disp_hal *h) {
    h->ep_recover = false;
    if (h->dev == NULL || h->bulk_ep == 0) return;
    h->ep_recover_cnt = h->ep_recover_cnt + 1;
    esp_err_t e1 = usb_host_endpoint_halt(h->dev, h->bulk_ep);
    esp_err_t e2 = usb_host_endpoint_flush(h->dev, h->bulk_ep);
    esp_err_t e3 = usb_host_endpoint_clear(h->dev, h->bulk_ep);
    if (h->ep_recover_cnt <= 8 || (h->ep_recover_cnt & 0x3F) == 0) {
        usb_disp_log("[HAL] bulk EP recover #%lu (halt=%d flush=%d clear=%d)",
                     (unsigned long)h->ep_recover_cnt, (int)e1, (int)e2,
                     (int)e3);
    }
}

static void client_task(void *arg) {
    (void)arg;
    struct usb_disp_hal *h = &s_hal[0];
    while (true) {
        usb_host_client_handle_events(s_client, pdMS_TO_TICKS(100));
        if (h->gone) {
            h->gone = false;
            device_teardown(h);
            // ハブ経由で他の DisplayLink が残っている可能性 → 再走査
            h->scan_needed = true;
        }
        // 列挙中で開けなかったデバイスの時限再走査 (device_setup 参照)
        if (h->scan_retry_ms && h->dev == NULL &&
            (int32_t)(usb_disp_hal_ms() - h->scan_retry_ms) >= 0) {
            h->scan_retry_ms = 0;
            h->scan_needed = true;
        }
        if (h->scan_needed && h->dev == NULL) {
            h->scan_needed = false;
            scan_devices(h);
        }
        if (h->ep_recover && h->attached) {
            bulk_ep_recover(h);
        }
    }
}

static void daemon_task(void *arg) {
    (void)arg;
    while (true) {
        uint32_t flags;
        usb_host_lib_handle_events(portMAX_DELAY, &flags);
        if (flags & USB_HOST_LIB_EVENT_FLAGS_NO_CLIENTS) {
            usb_host_device_free_all();
        }
    }
}

// ---------------------------------------------------------------
// Hub-port watchdog (Terminus-hub + slow-booting FS device recovery)
//
// Background: IDF's ext_port driver attempts a hub-port reset exactly
// once (EXT_PORT_RESET_ATTEMPTS defaults to 1). A slow-booting
// Full-Speed device (a DisplayLink adapter needs 1-2s after VBUS)
// that stalls the first short-descriptor read leaves the port
// DISABLED forever ("CHECK_SHORT_DEV_DESC FAILED"), and the stack's
// own recycle path cannot recover pre-enumeration failures
// ("Ext hub port recycle error: ESP_ERR_INVALID_ARG"). Linux xHCI
// retries transparently, which is why the same hub+adapter works on
// a PC but wedges on ESP32 until the whole chain is replugged.
//
// This watchdog sweeps every external hub with standard, read-only
// GET_PORT_STATUS requests. Tracking runs on every poll, attached or
// not, so unplugs are observed even mid-display; recovery actions
// (resets, power cycles, escalation) fire only while detached.
// connected-but-unenumerated: up to 3 SET_FEATURE(PORT_RESET)s with
// growing backoff (~4s/~12s/~28s stuck time), then one PORT_POWER
// off/on cycle, then silence until the connection flaps. The resets
// are targeted (VBUS stays up, other ports untouched) and by the time
// they fire the device has finished booting, so re-enumeration
// succeeds; the power cycle is the last resort for a latched port.
// Enabled ports (healthy mouse/display, enumeration in progress) are
// never touched. High-speed ports are never touched either: they carry
// cascaded hubs, and resetting one drops the whole subtree, which the
// IDF enumerator cannot survive (abort in enum.c control_request_string
// on the resulting error cascade). Change bits are NEVER cleared here:
// clearing C_CONNECTION would steal the connect event from IDF's hub
// driver and cause the very silence this fixes.
// Every transition and action is logged ([HUB] lines) with the
// per-port counters, so recovery state is always visible on serial.
// ---------------------------------------------------------------

#define USB_DISP_HUB_MAX_PORTS 8   // ports tracked per hub (Terminus = 4)
#define USB_DISP_HUB_WD_MAX 4      // hubs tracked simultaneously
#define USB_DISP_HUB_WD_GRACE_MS 4000  // episode start -> first reset due
#define USB_DISP_HUB_WD_RESETS 3       // port resets before power cycle
#define USB_DISP_HUB_WD_PC_GRACE_MS 8000  // power cycle -> give-up verdict
#define USB_DISP_HUB_WD_RETRY_MS 4000     // hub comm failure -> retry sweep
#define USB_DISP_HUB_WD_QUIET_MS 15000    // flapped idle port -> one auto-reset
#define USB_DISP_HUB_WD_BUS_SETTLE_MS 10000  // hub first seen -> dues allowed
#define USB_DISP_HUB_WD_DEFER_MS 3000     // bus growth -> push dues out
#define USB_DISP_HUB_WD_SWEEP_MS 1000     // min interval between sweeps
#define USB_DISP_HUB_CTRL_MS 1500         // per-transfer timeout
#define USB_DISP_LSUSB_MAX_DEV 16         // addresses listed by lsusb
#define USB_DISP_HUB_WD_ESCALATE_MAX 3    // auto root cycles per boot

// Wait after reset N (1-based) before the next recovery step. A
// browned-out adapter can need 10-20s, so the tail is long on purpose;
// healthy enumerations finish before the first grace expires and never
// see any of this.
static const uint16_t kHubWdBackoffMs[USB_DISP_HUB_WD_RESETS] = {
    8000, 16000, 8000,
};

// Hub class request constants (USB 2.0 spec, Tables 11-16/17/19)
#define USB_DISP_HUB_DESC_TYPE 0x29
#define USB_DISP_REQ_GET_STATUS 0
#define USB_DISP_REQ_GET_DESCRIPTOR 6
#define USB_DISP_REQ_SET_FEATURE 3
#define USB_DISP_FEAT_PORT_RESET 4
#define USB_DISP_FEAT_PORT_POWER 8
#define USB_DISP_PORT_STAT_CONNECTION 0x0001
#define USB_DISP_PORT_STAT_ENABLE 0x0002
#define USB_DISP_PORT_CHG_CONNECTION 0x0001
#define USB_DISP_PORT_STAT_HIGH_SPEED 0x0400

typedef struct {
    bool occupied;
    uint8_t hub_addr;
    uint8_t nports;  // cached hub-descriptor port count (0 = unknown)
    // Per-port stuck-episode state (index = port - 1)
    uint32_t stuck_since[USB_DISP_HUB_MAX_PORTS];  // episode start ms (0 = none)
    uint32_t next_due[USB_DISP_HUB_MAX_PORTS];     // next action due ms
    uint8_t attempts[USB_DISP_HUB_MAX_PORTS];      // port resets issued
    uint8_t n_at_open[USB_DISP_HUB_MAX_PORTS];     // bus addr count at open
    bool power_cycled[USB_DISP_HUB_MAX_PORTS];     // vbus cycle spent
    bool given_up[USB_DISP_HUB_MAX_PORTS];         // silent until flap
    bool noted[USB_DISP_HUB_MAX_PORTS];            // idle hint logged
    bool preexisting[USB_DISP_HUB_MAX_PORTS];      // idle since before last arm
    bool quiet[USB_DISP_HUB_MAX_PORTS];            // idle auto-reset episode
    bool quiet_done[USB_DISP_HUB_MAX_PORTS];       // idle reset spent
    uint8_t cerr;                                  // consecutive hub failures
    uint8_t backoffs;                              // breaker trips this lifetime
    uint32_t skip_until;                           // breaker backoff deadline
    uint32_t born_ms;                              // first sweep seeing hub
    bool fresh;                                    // needs first-pass marking
} hub_wd_t;

static hub_wd_t s_hub_wd[USB_DISP_HUB_WD_MAX];
static bool s_watchdog_on = true;
static bool s_auto_reset_idle = true;
static uint32_t s_hub_wd_last_ms = 0;
static int s_hub_wd_prev_n = -1;
static uint32_t s_hub_wd_last_growth_ms = 0;
static uint8_t s_escalations = 0;
static bool s_snapshot_idle = false;
static bool s_prev_attached = false;

#define USB_DISP_HUB_PERF_MAX 4
#define USB_DISP_HUB_CTRL_SLOW_MS 500
typedef struct {
    uint8_t addr;
    uint8_t fails;
} hub_perf_t;
static hub_perf_t s_hub_perf[USB_DISP_HUB_PERF_MAX];

static uint32_t hub_timeout_ms(uint8_t hub_addr) {
    for (uint8_t i = 0; i < USB_DISP_HUB_PERF_MAX; i++) {
        if (s_hub_perf[i].addr == hub_addr) {
            return s_hub_perf[i].fails ? USB_DISP_HUB_CTRL_SLOW_MS
                                       : USB_DISP_HUB_CTRL_MS;
        }
    }
    return USB_DISP_HUB_CTRL_MS;
}

static void hub_perf_note(uint8_t hub_addr, bool ok) {
    uint8_t free_idx = USB_DISP_HUB_PERF_MAX;
    for (uint8_t i = 0; i < USB_DISP_HUB_PERF_MAX; i++) {
        if (s_hub_perf[i].addr == hub_addr) {
            s_hub_perf[i].fails = ok ? 0 : (s_hub_perf[i].fails < 255
                                                 ? (uint8_t)(s_hub_perf[i].fails + 1)
                                                 : 255);
            return;
        }
        if (s_hub_perf[i].addr == 0 && free_idx == USB_DISP_HUB_PERF_MAX) {
            free_idx = i;
        }
    }
    if (free_idx < USB_DISP_HUB_PERF_MAX) {
        s_hub_perf[free_idx].addr = hub_addr;
        s_hub_perf[free_idx].fails = ok ? 0 : 1;
    }
}
static SemaphoreHandle_t s_hub_mutex = NULL;
static SemaphoreHandle_t s_hub_done = NULL;

static void hub_xfer_cb(usb_transfer_t *xfer) {
    SemaphoreHandle_t done = (SemaphoreHandle_t)xfer->context;
    xSemaphoreGive(done);
}

// Raw control transfer on an already-open device handle (no open/close,
// no class check). App-task context, serialized by s_hub_mutex.
static bool dev_ctrl_hdl(usb_device_handle_t dev, uint8_t bmRequestType,
                         uint8_t bRequest, uint16_t wValue, uint16_t wIndex,
                         void *data, uint16_t wLength, uint16_t *actual) {
    if (!s_started || s_client == NULL || s_hub_mutex == NULL ||
        s_hub_done == NULL || dev == NULL) {
        return false;
    }
    if (wLength > 128) return false;
    if (xSemaphoreTake(s_hub_mutex, pdMS_TO_TICKS(3000)) != pdTRUE) {
        return false;
    }
    bool ok = false;
    usb_transfer_t *x = NULL;
    if (usb_host_transfer_alloc(8 + 128, 0, &x) != ESP_OK) goto out;
    {
        bool dir_in = (bmRequestType & 0x80) != 0;
        uint8_t *b = x->data_buffer;
        b[0] = bmRequestType;
        b[1] = bRequest;
        b[2] = (uint8_t)wValue;
        b[3] = (uint8_t)(wValue >> 8);
        b[4] = (uint8_t)wIndex;
        b[5] = (uint8_t)(wIndex >> 8);
        b[6] = (uint8_t)wLength;
        b[7] = (uint8_t)(wLength >> 8);
        if (!dir_in && wLength && data) memcpy(b + 8, data, wLength);
        x->num_bytes = 8 + wLength;
        x->device_handle = dev;
        x->bEndpointAddress = 0;
        x->callback = hub_xfer_cb;
        x->context = s_hub_done;
        xSemaphoreTake(s_hub_done, 0);  // clear stale signal
        if (usb_host_transfer_submit_control(s_client, x) != ESP_OK) goto out;
        if (xSemaphoreTake(s_hub_done,
                           pdMS_TO_TICKS(hub_timeout_ms(0))) != pdTRUE) {
            goto out;
        }
        if (x->status != USB_TRANSFER_STATUS_COMPLETED) goto out;
        uint16_t got =
            (x->actual_num_bytes >= 8) ? (uint16_t)(x->actual_num_bytes - 8)
                                       : 0;
        if (dir_in && data && got) {
            if (got > wLength) got = wLength;
            memcpy(data, b + 8, got);
        }
        if (actual) *actual = got;
    }
    ok = true;
out:
    if (x) usb_host_transfer_free(x);
    xSemaphoreGive(s_hub_mutex);
    return ok;
}

// Address of the display device held open by this client, if any.
// Needed because the stack's address list only contains idle devices:
// an opened device leaves the idle tailq and vanishes from
// bus_devices()/lsusb unless re-added here.
bool usb_disp_hal_claimed_addr(uint8_t *addr) {
    struct usb_disp_hal *h = &s_hal[0];
    if (h->dev == NULL || addr == NULL) return false;
    usb_device_info_t info;
    if (usb_host_device_info(h->dev, &info) != ESP_OK || info.dev_addr == 0) {
        return false;
    }
    *addr = info.dev_addr;
    return true;
}

// One hub-class control transfer, app-task context, serialized by
// s_hub_mutex. Opens the hub (verifying class 09), submits on EP0,
// waits, closes. Returns true on COMPLETED.
static bool hub_ctrl(uint8_t hub_addr, uint8_t bmRequestType, uint8_t bRequest,
                     uint16_t wValue, uint16_t wIndex,
                     void *data, uint16_t wLength, uint16_t *actual) {
    if (!s_started || s_client == NULL || s_hub_mutex == NULL ||
        s_hub_done == NULL) {
        return false;
    }
    if (wLength > 32) return false;
    if (xSemaphoreTake(s_hub_mutex, pdMS_TO_TICKS(3000)) != pdTRUE) {
        return false;
    }
    bool ok = false;
    usb_device_handle_t dev = NULL;
    usb_transfer_t *x = NULL;
    if (usb_host_device_open(s_client, hub_addr, &dev) != ESP_OK) {
        goto out;
    }
    {
        const usb_device_desc_t *ddesc = NULL;
        if (usb_host_get_device_descriptor(dev, &ddesc) != ESP_OK ||
            ddesc == NULL || ddesc->bDeviceClass != 0x09) {
            goto out;
        }
    }
    if (usb_host_transfer_alloc(8 + 32, 0, &x) != ESP_OK) goto out;
    {
        bool dir_in = (bmRequestType & 0x80) != 0;
        uint8_t *b = x->data_buffer;
        b[0] = bmRequestType;
        b[1] = bRequest;
        b[2] = (uint8_t)wValue;
        b[3] = (uint8_t)(wValue >> 8);
        b[4] = (uint8_t)wIndex;
        b[5] = (uint8_t)(wIndex >> 8);
        b[6] = (uint8_t)wLength;
        b[7] = (uint8_t)(wLength >> 8);
        if (!dir_in && wLength && data) memcpy(b + 8, data, wLength);
        x->num_bytes = 8 + wLength;
        x->device_handle = dev;
        x->bEndpointAddress = 0;
        x->callback = hub_xfer_cb;
        x->context = s_hub_done;
        xSemaphoreTake(s_hub_done, 0);  // clear stale signal
        if (usb_host_transfer_submit_control(s_client, x) != ESP_OK) goto out;
        if (xSemaphoreTake(s_hub_done, pdMS_TO_TICKS(hub_timeout_ms(hub_addr))) !=
            pdTRUE) {
            goto out;
        }
        if (x->status != USB_TRANSFER_STATUS_COMPLETED) {
            usb_disp_log("[HUB] ctrl error: status=%d (bReq=%02X addr=%u)",
                         (int)x->status, bRequest, hub_addr);
            goto out;
        }
        uint16_t got =
            (x->actual_num_bytes >= 8) ? (uint16_t)(x->actual_num_bytes - 8)
                                       : 0;
        if (dir_in && data && got) {
            if (got > wLength) got = wLength;
            memcpy(data, b + 8, got);
        }
        if (actual) *actual = got;
    }
    ok = true;
out:
    if (x) usb_host_transfer_free(x);
    if (dev) usb_host_device_close(s_client, dev);
    hub_perf_note(hub_addr, ok);
    xSemaphoreGive(s_hub_mutex);
    return ok;
}

static uint8_t hub_port_count(uint8_t hub_addr) {
    uint8_t buf[16] = {0};
    uint16_t actual = 0;
    if (!hub_ctrl(hub_addr, 0xA0, USB_DISP_REQ_GET_DESCRIPTOR,
                  (uint16_t)(USB_DISP_HUB_DESC_TYPE << 8), 0, buf, sizeof(buf),
                  &actual) ||
        actual < 3) {
        return 0;
    }
    uint8_t n = buf[2];
    if (n == 0 || n > USB_DISP_HUB_MAX_PORTS) return 0;
    return n;
}

// Read-only port status. Never clears change bits (see banner above).
static bool hub_port_status(uint8_t hub_addr, uint8_t port, bool *connected,
                            bool *enabled, bool *conn_change,
                            bool *high_speed) {
    uint8_t buf[4] = {0};
    uint16_t actual = 0;
    if (!hub_ctrl(hub_addr, 0xA3, USB_DISP_REQ_GET_STATUS, 0, port, buf, 4,
                  &actual) ||
        actual < 4) {
        return false;
    }
    uint16_t st = (uint16_t)(buf[0] | (buf[1] << 8));
    uint16_t ch = (uint16_t)(buf[2] | (buf[3] << 8));
    *connected = (st & USB_DISP_PORT_STAT_CONNECTION) != 0;
    *enabled = (st & USB_DISP_PORT_STAT_ENABLE) != 0;
    *conn_change = (ch & USB_DISP_PORT_CHG_CONNECTION) != 0;
    *high_speed = (st & USB_DISP_PORT_STAT_HIGH_SPEED) != 0;
    return true;
}

static bool hub_reset_port(uint8_t hub_addr, uint8_t port, bool power_cycle) {
    bool ok;
    if (power_cycle) {
        // VBUS drop: forces a from-scratch connection event through the
        // stack's own path. Ganged-power hubs may drop sibling ports too.
        ok = hub_ctrl(hub_addr, 0x23, 1 /*CLEAR_FEATURE*/,
                      USB_DISP_FEAT_PORT_POWER, port, NULL, 0, NULL);
        if (ok) {
            vTaskDelay(pdMS_TO_TICKS(300));
            ok = hub_ctrl(hub_addr, 0x23, USB_DISP_REQ_SET_FEATURE,
                          USB_DISP_FEAT_PORT_POWER, port, NULL, 0, NULL);
        }
        usb_disp_log("[HUB] addr=%u port=%u power cycle %s", hub_addr, port,
                     ok ? "ok" : "FAIL");
        return ok;
    }
    ok = hub_ctrl(hub_addr, 0x23, USB_DISP_REQ_SET_FEATURE,
                  USB_DISP_FEAT_PORT_RESET, port, NULL, 0, NULL);
    usb_disp_log("[HUB] addr=%u port=%u reset %s", hub_addr, port,
                 ok ? "ok" : "FAIL");
    return ok;
}

static void wd_port_clear(hub_wd_t *slot, uint8_t idx) {
    slot->stuck_since[idx] = 0;
    slot->next_due[idx] = 0;
    slot->attempts[idx] = 0;
    slot->power_cycled[idx] = false;
    slot->given_up[idx] = false;
    slot->n_at_open[idx] = 0;
    slot->noted[idx] = false;
    slot->quiet[idx] = false;
    slot->quiet_done[idx] = false;
    slot->preexisting[idx] = false;
}

static void wd_port_closed(hub_wd_t *slot, uint8_t idx, uint8_t addr,
                           uint8_t port, uint32_t now, const char *why) {
    usb_disp_log("[HUB] addr=%u port=%u %s, episode over (stuck %lus, %u "
                 "resets%s)",
                 addr, port, why,
                 (unsigned long)((now - slot->stuck_since[idx]) / 1000),
                 slot->attempts[idx],
                 slot->power_cycled[idx] ? "+power" : "");
    wd_port_clear(slot, idx);
}

// Last-resort escalation: a dead-silent hub plus stuck ports means the
// chain needs a root power cycle (proven to revive EP0-dead hubs that
// nothing else touches). Only while detached, capped per boot; fresh
// hub addresses after the cycle reset all watchdog state naturally.
static void hub_escalate_maybe(void) {
    bool stuck = false;
    for (uint8_t s = 0; s < USB_DISP_HUB_WD_MAX && !stuck; s++) {
        if (!s_hub_wd[s].occupied) continue;
        for (uint8_t p = 0; p < USB_DISP_HUB_MAX_PORTS; p++) {
            if (s_hub_wd[s].stuck_since[p] || s_hub_wd[s].given_up[p]) {
                stuck = true;
                break;
            }
        }
    }
    if (!stuck) return;
    if (s_escalations < USB_DISP_HUB_WD_ESCALATE_MAX) {
        s_escalations++;
        usb_disp_log("[HUB] escalating: root power cycle (%u/%u this boot)",
                     s_escalations, USB_DISP_HUB_WD_ESCALATE_MAX);
        usb_disp_hal_request_reenum(&s_hal[0]);
    } else {
        usb_disp_log("[HUB] escalation budget spent, manual force_reenum() only");
    }
}

// One watchdog sweep over all hubs on the bus. Tracking (status reads,
// flap arms, episodes, breaker) always runs; recovery actions (resets,
// power cycles, escalation) only run when allow_actions is set, i.e.
// while no display is attached. Open (class-verified) failures skip the
// hub for this round but keep its episode state.
static void hub_watchdog_step(bool allow_actions) {
    uint32_t now = usb_disp_hal_ms();
    if ((int32_t)(now - s_hub_wd_last_ms) < USB_DISP_HUB_WD_SWEEP_MS) return;
    if (s_hub_wd_last_ms != 0 &&
        (uint32_t)(now - s_hub_wd_last_ms) > 3000) {
        usb_disp_log("[HUB] sweep delayed %lus",
                     (unsigned long)((now - s_hub_wd_last_ms) / 1000));
    }
    s_hub_wd_last_ms = now;

    uint8_t addrs[16];
    int n = 0;
    if (usb_host_device_addr_list_fill((int)sizeof(addrs), addrs, &n) !=
        ESP_OK) {
        return;
    }
    if (s_hub_wd_prev_n >= 0 && n > s_hub_wd_prev_n) {
        s_hub_wd_last_growth_ms = now;
    }
    s_hub_wd_prev_n = n;
    bool snap = s_snapshot_idle;
    s_snapshot_idle = false;

    for (int i = 0; i < n; i++) {
        uint8_t addr = addrs[i];
        hub_wd_t *slot = NULL;
        hub_wd_t *free_slot = NULL;
        for (uint8_t s = 0; s < USB_DISP_HUB_WD_MAX; s++) {
            if (s_hub_wd[s].occupied && s_hub_wd[s].hub_addr == addr) {
                slot = &s_hub_wd[s];
                break;
            }
            if (!s_hub_wd[s].occupied && free_slot == NULL) {
                free_slot = &s_hub_wd[s];
            }
        }
        if (slot == NULL) {
            if (free_slot == NULL) continue;  // table full, skip hub
            memset(free_slot, 0, sizeof(*free_slot));
            free_slot->occupied = true;
            free_slot->hub_addr = addr;
            free_slot->born_ms = now;
            free_slot->fresh = true;
            slot = free_slot;
        }
        if (slot->nports == 0) {
            slot->nports = hub_port_count(addr);
            if (slot->nports == 0) continue;  // not a hub (or not yet
                                              // readable); retry next sweep
            usb_disp_log("[HUB] addr=%u ports=%u", addr, slot->nports);
        }
        if (slot->skip_until != 0) {
            if ((int32_t)(now - slot->skip_until) < 0) continue;
            slot->skip_until = 0;
        }
        bool hub_ok = true;
        if (hub_ok) for (uint8_t port = 1; port <= slot->nports; port++) {
            uint8_t idx = (uint8_t)(port - 1);
            bool conn = false, en = false, cchg = false, hs = false;
            if (!hub_port_status(addr, port, &conn, &en, &cchg, &hs)) {
                hub_ok = false;
                continue;
            }
            if (slot->fresh || snap) {
                if (!conn) slot->preexisting[idx] = false;
                else if (en && !cchg) slot->preexisting[idx] = true;
            } else if (!conn) {
                slot->preexisting[idx] = false;
            }
            bool episode = (slot->stuck_since[idx] != 0 ||
                            slot->attempts[idx] != 0 ||
                            slot->power_cycled[idx] || slot->given_up[idx]);
            if (!conn) {
                if (episode) wd_port_closed(slot, idx, addr, port, now, "unplugged");
                else wd_port_clear(slot, idx);
                continue;
            }
            if (hs) {
                if (episode && !slot->given_up[idx]) {
                    slot->given_up[idx] = true;
                    usb_disp_log("[HUB] addr=%u port=%u high-speed device, skipping",
                                 addr, port);
                } else if (!slot->noted[idx]) {
                    slot->noted[idx] = true;
                    usb_disp_log("[HUB] addr=%u port=%u high-speed device, skipping",
                                 addr, port);
                }
                continue;
            }
            if (episode && n != slot->n_at_open[idx]) {
                wd_port_closed(slot, idx, addr, port, now, "enumerated");
                slot->preexisting[idx] = true;
                continue;
            }
            if (en && !cchg && !episode) {
                if (!slot->noted[idx]) {
                    slot->noted[idx] = true;
                    usb_disp_log("[HUB] addr=%u port=%u enabled but idle "
                                 "(reset_port(%u,%u) if stuck)",
                                 addr, port, addr, port);
                }
                if (s_auto_reset_idle && !slot->preexisting[idx] &&
                    !slot->quiet_done[idx]) {
                    slot->stuck_since[idx] = now;
                    slot->n_at_open[idx] = (uint8_t)n;
                    slot->quiet[idx] = true;
                    slot->next_due[idx] = now + USB_DISP_HUB_WD_QUIET_MS;
                    usb_disp_log("[HUB] addr=%u port=%u idle, auto-reset in "
                                 "%us",
                                 addr, port,
                                 USB_DISP_HUB_WD_QUIET_MS / 1000);
                }
                continue;
            }
            if (slot->given_up[idx]) continue;
            if (!episode && en) continue;
            if (slot->stuck_since[idx] == 0) {
                slot->stuck_since[idx] = now;
                slot->attempts[idx] = 0;
                slot->power_cycled[idx] = false;
                slot->n_at_open[idx] = (uint8_t)n;
                slot->next_due[idx] = now + USB_DISP_HUB_WD_GRACE_MS;
                usb_disp_log("[HUB] addr=%u port=%u connected, waiting",
                             addr, port);
                continue;
            }
            if ((int32_t)(now - slot->next_due[idx]) < 0) continue;
            if (!allow_actions) continue;
            if (slot->quiet[idx]) {
                usb_disp_log("[HUB] addr=%u port=%u idle reset (stuck %lus)",
                             addr, port,
                             (unsigned long)((now - slot->stuck_since[idx]) /
                                             1000));
                bool ok = hub_reset_port(addr, port, false);
                wd_port_closed(slot, idx, addr, port, now,
                               ok ? "idle reset done" : "idle reset FAILED");
                slot->quiet_done[idx] = true;
                slot->preexisting[idx] = true;
                continue;
            }
            if ((int32_t)(now - s_hub_wd_last_growth_ms) <
                USB_DISP_HUB_WD_DEFER_MS) {
                slot->next_due[idx] = now + USB_DISP_HUB_WD_DEFER_MS;
                continue;
            }
            if ((int32_t)(now - slot->born_ms) < USB_DISP_HUB_WD_BUS_SETTLE_MS) {
                slot->next_due[idx] =
                    slot->born_ms + USB_DISP_HUB_WD_BUS_SETTLE_MS;
                continue;
            }
            unsigned long stuck_s =
                (unsigned long)((now - slot->stuck_since[idx]) / 1000);
            if (slot->attempts[idx] < USB_DISP_HUB_WD_RESETS) {
                uint8_t att = (uint8_t)(slot->attempts[idx] + 1);
                usb_disp_log("[HUB] addr=%u port=%u reset %u/%u (stuck %lus)",
                             addr, port, att, USB_DISP_HUB_WD_RESETS, stuck_s);
                if (hub_reset_port(addr, port, false)) {
                    slot->attempts[idx] = att;
                    slot->next_due[idx] =
                        now + kHubWdBackoffMs[att - 1];
                } else {
                    slot->next_due[idx] = now + USB_DISP_HUB_WD_RETRY_MS;
                }
            } else if (!slot->power_cycled[idx]) {
                usb_disp_log("[HUB] addr=%u port=%u power cycle (stuck %lus, "
                             "%u resets done)",
                             addr, port, stuck_s, slot->attempts[idx]);
                if (hub_reset_port(addr, port, true)) {
                    slot->power_cycled[idx] = true;
                    slot->next_due[idx] = now + USB_DISP_HUB_WD_PC_GRACE_MS;
                } else {
                    slot->next_due[idx] = now + USB_DISP_HUB_WD_RETRY_MS;
                }
            } else {
                slot->given_up[idx] = true;
                usb_disp_log("[HUB] addr=%u port=%u stuck after %u resets + "
                             "power cycle, giving up until replug",
                             addr, port, slot->attempts[idx]);
            }
        }
        if (hub_ok) {
            if (slot->cerr > 5) {
                usb_disp_log("[HUB] addr=%u responsive again", addr);
            }
            slot->cerr = 0;
            slot->backoffs = 0;
            slot->fresh = false;
        } else {
            if (slot->cerr < 255) slot->cerr++;
            if (slot->cerr > 5 && slot->skip_until == 0 && slot->backoffs < 3) {
                slot->backoffs++;
                uint32_t wait_ms = (slot->backoffs == 1) ? 30000
                    : (slot->backoffs == 2) ? 60000 : 120000;
                slot->skip_until = now + wait_ms;
                usb_disp_log("[HUB] addr=%u errors, backing off %lus", addr,
                             (unsigned long)(wait_ms / 1000));
                if (allow_actions) hub_escalate_maybe();
            } else if (slot->cerr > 5 && slot->skip_until == 0) {
                slot->skip_until = now + 120000;
                usb_disp_log("[HUB] addr=%u still dead, quiet 120s", addr);
                if (allow_actions) hub_escalate_maybe();
            }
        }
    }

    // Age out hubs that left the bus (unplugged chain).
    for (uint8_t s = 0; s < USB_DISP_HUB_WD_MAX; s++) {
        if (!s_hub_wd[s].occupied) continue;
        bool present = false;
        for (int i = 0; i < n; i++) {
            if (addrs[i] == s_hub_wd[s].hub_addr) {
                present = true;
                break;
            }
        }
        if (!present) memset(&s_hub_wd[s], 0, sizeof(s_hub_wd[s]));
    }
}

uint8_t usb_disp_hal_hub_ports(usb_disp_hub_port_t *out, uint8_t max) {
    uint8_t count = 0;
    if (out == NULL || max == 0) return 0;
    uint8_t addrs[16];
    int n = 0;
    if (usb_host_device_addr_list_fill((int)sizeof(addrs), addrs, &n) !=
        ESP_OK) {
        return 0;
    }
    for (int i = 0; i < n && count < max; i++) {
        uint8_t nports = hub_port_count(addrs[i]);
        if (nports == 0) continue;
        for (uint8_t port = 1; port <= nports && count < max; port++) {
            bool conn = false, en = false, cchg = false, hs = false;
            if (!hub_port_status(addrs[i], port, &conn, &en, &cchg, &hs)) continue;
            out[count].hub_addr = addrs[i];
            out[count].port = port;
            out[count].connected = conn;
            out[count].enabled = en;
            out[count].high_speed = hs;
            count++;
        }
    }
    return count;
}

bool usb_disp_hal_reset_hub_port(uint8_t hub_addr, uint8_t port,
                                 bool power_cycle, bool force) {
    if (port == 0 || port > USB_DISP_HUB_MAX_PORTS) return false;
    bool conn = false, en = false, cchg = false, hs = false;
    if (hub_port_status(hub_addr, port, &conn, &en, &cchg, &hs) && hs &&
        !force) {
        usb_disp_log("[HUB] addr=%u port=%u high-speed device, refusing reset",
                     hub_addr, port);
        return false;
    }
    if (force && hs) {
        usb_disp_log("[HUB] addr=%u port=%u FORCED reset", hub_addr, port);
    }
    return hub_reset_port(hub_addr, port, power_cycle);
}

// Raw control transfer to any device address (no class check).
// App-task context, serialized by s_hub_mutex like hub_ctrl.
static bool dev_ctrl(uint8_t dev_addr, uint8_t bmRequestType, uint8_t bRequest,
                     uint16_t wValue, uint16_t wIndex,
                     void *data, uint16_t wLength, uint16_t *actual) {
    if (!s_started || s_client == NULL || s_hub_mutex == NULL ||
        s_hub_done == NULL) {
        return false;
    }
    if (wLength > 128) return false;
    if (xSemaphoreTake(s_hub_mutex, pdMS_TO_TICKS(3000)) != pdTRUE) {
        return false;
    }
    bool ok = false;
    usb_device_handle_t dev = NULL;
    usb_transfer_t *x = NULL;
    if (usb_host_device_open(s_client, dev_addr, &dev) != ESP_OK) {
        goto out;
    }
    if (usb_host_transfer_alloc(8 + 128, 0, &x) != ESP_OK) goto out;
    {
        bool dir_in = (bmRequestType & 0x80) != 0;
        uint8_t *b = x->data_buffer;
        b[0] = bmRequestType;
        b[1] = bRequest;
        b[2] = (uint8_t)wValue;
        b[3] = (uint8_t)(wValue >> 8);
        b[4] = (uint8_t)wIndex;
        b[5] = (uint8_t)(wIndex >> 8);
        b[6] = (uint8_t)wLength;
        b[7] = (uint8_t)(wLength >> 8);
        if (!dir_in && wLength && data) memcpy(b + 8, data, wLength);
        x->num_bytes = 8 + wLength;
        x->device_handle = dev;
        x->bEndpointAddress = 0;
        x->callback = hub_xfer_cb;
        x->context = s_hub_done;
        xSemaphoreTake(s_hub_done, 0);  // clear stale signal
        if (usb_host_transfer_submit_control(s_client, x) != ESP_OK) goto out;
        if (xSemaphoreTake(s_hub_done,
                           pdMS_TO_TICKS(hub_timeout_ms(dev_addr))) != pdTRUE) {
            goto out;
        }
        if (x->status != USB_TRANSFER_STATUS_COMPLETED) goto out;
        uint16_t got =
            (x->actual_num_bytes >= 8) ? (uint16_t)(x->actual_num_bytes - 8)
                                       : 0;
        if (dir_in && data && got) {
            if (got > wLength) got = wLength;
            memcpy(data, b + 8, got);
        }
        if (actual) *actual = got;
    }
    ok = true;
out:
    if (x) usb_host_transfer_free(x);
    if (dev) usb_host_device_close(s_client, dev);
    hub_perf_note(dev_addr, ok);
    xSemaphoreGive(s_hub_mutex);
    return ok;
}

// Control transfer to a device we hold open (hdl) or by address
// (hdl NULL: opened and closed for the call).
static bool lsusb_xfer(usb_device_handle_t hdl, uint8_t addr,
                       uint8_t bmRequestType, uint8_t bRequest,
                       uint16_t wValue, uint16_t wIndex,
                       void *data, uint16_t wLength, uint16_t *actual) {
    if (hdl != NULL) {
        return dev_ctrl_hdl(hdl, bmRequestType, bRequest, wValue, wIndex,
                            data, wLength, actual);
    }
    return dev_ctrl(addr, bmRequestType, bRequest, wValue, wIndex, data,
                    wLength, actual);
}

// One USB string descriptor as NUL-terminated ASCII ('?' for the rest).
static bool lsusb_get_str(usb_device_handle_t hdl, uint8_t dev_addr,
                          uint8_t index, uint16_t langid,
                          char *out, uint8_t cap) {
    if (index == 0 || cap == 0) return false;
    out[0] = 0;
    uint8_t buf[66];
    uint16_t actual = 0;
    if (!lsusb_xfer(hdl, dev_addr, 0x80, 0x06, (uint16_t)(0x0300 | index),
                    langid, buf, sizeof(buf), &actual) ||
        actual < 4 || buf[1] != 0x03) {
        return false;
    }
    uint8_t blen = buf[0];
    if (blen > actual) blen = (uint8_t)actual;
    uint8_t o = 0;
    for (uint8_t i = 2; i + 1 < blen && o + 1 < cap; i += (uint8_t)2) {
        uint16_t c = (uint16_t)(buf[i] | (buf[i + 1] << 8));
        out[o++] = (c >= 0x20 && c < 0x7F) ? (char)c : '?';
    }
    out[o] = 0;
    return o > 0;
}

uint16_t usb_disp_hal_lsusb(char *out, uint16_t maxlen) {
    if (out == NULL || maxlen == 0) return 0;
    out[0] = 0;
    if (!s_started || s_client == NULL) return 0;
    uint8_t addrs[USB_DISP_LSUSB_MAX_DEV];
    int n = 0;
    if (usb_host_device_addr_list_fill((int)sizeof(addrs), addrs, &n) !=
        ESP_OK) {
        return 0;
    }
    for (int i = 1; i < n; i++) {
        uint8_t a = addrs[i];
        int j = i - 1;
        while (j >= 0 && addrs[j] > a) {
            addrs[j + 1] = addrs[j];
            j--;
        }
        addrs[j + 1] = a;
    }
    uint16_t used = 0;
    uint8_t held_addr = 0;
    usb_disp_hal_claimed_addr(&held_addr);
    if (held_addr != 0 && n < USB_DISP_LSUSB_MAX_DEV) {
        bool seen = false;
        for (int k = 0; k < n; k++) {
            if (addrs[k] == held_addr) {
                seen = true;
                break;
            }
        }
        if (!seen) addrs[n++] = held_addr;
    }
    for (int i = 0; i < n; i++) {
        // The display device held open by this client left the stack's
        // idle list, so use our own handle for it (opening it again by
        // address is unreliable while streaming).
        usb_device_handle_t held = NULL;
        if (held_addr != 0 && addrs[i] == held_addr) {
            held = s_hal[0].dev;
        }
        usb_device_handle_t dev = held;
        if (dev == NULL) {
            if (usb_host_device_open(s_client, addrs[i], &dev) != ESP_OK) {
                continue;
            }
        }
        const usb_device_desc_t *dd = NULL;
        bool ok =
            (usb_host_get_device_descriptor(dev, &dd) == ESP_OK && dd != NULL);
        uint16_t vid = 0, pid = 0;
        uint8_t cls = 0, iman = 0, iprod = 0;
        if (ok) {
            vid = dd->idVendor;
            pid = dd->idProduct;
            cls = dd->bDeviceClass;
            iman = dd->iManufacturer;
            iprod = dd->iProduct;
        }
        if (held == NULL) {
            usb_host_device_close(s_client, dev);
        }
        if (!ok) continue;
        char manuf[32] = {0}, prod[48] = {0};
        if (iman || iprod) {
            uint16_t langid = 0x0409;
            uint8_t lt[8];
            uint16_t la = 0;
            if (lsusb_xfer(held, addrs[i], 0x80, 0x06, 0x0300, 0, lt,
                           sizeof(lt), &la) &&
                la >= 4 && lt[1] == 0x03) {
                langid = (uint16_t)(lt[2] | (lt[3] << 8));
            }
            if (iman) {
                lsusb_get_str(held, addrs[i], iman, langid, manuf,
                              sizeof(manuf));
            }
            if (iprod) {
                lsusb_get_str(held, addrs[i], iprod, langid, prod,
                              sizeof(prod));
            }
        }
        char name[80];
        if (manuf[0] && prod[0]) {
            snprintf(name, sizeof(name), "%s %s", manuf, prod);
        } else if (prod[0]) {
            snprintf(name, sizeof(name), "%s", prod);
        } else if (manuf[0]) {
            snprintf(name, sizeof(name), "%s", manuf);
        } else if (cls == 0x09) {
            snprintf(name, sizeof(name), "Hub");
        } else {
            snprintf(name, sizeof(name), "Unknown device");
        }
        int w = snprintf(out + used, maxlen - used,
                         "Bus 001 Device %03d: ID %04x:%04x %s\n", addrs[i],
                         vid, pid, name);
        if (w < 0 || (uint16_t)w >= maxlen - used) break;
        used = (uint16_t)(used + w);
    }
    return used;
}

void usb_disp_hal_set_watchdog(bool on) { s_watchdog_on = on; }

bool usb_disp_hal_watchdog(void) { return s_watchdog_on; }

void usb_disp_hal_set_auto_reset_idle(bool on) { s_auto_reset_idle = on; }

bool usb_disp_hal_auto_reset_idle(void) { return s_auto_reset_idle; }

// ---------------------------------------------------------------
// HAL インターフェース実装
// ---------------------------------------------------------------

usb_disp_hal_t *usb_disp_hal_add(const usb_disp_config_t *cfg) {
    // port は現状 0 のみ (S2/S3 は OTG 1系統。P4 の 2系統目
    // 1 = USB 1.1 OTG FS は現在未対応 - 対応時に cfg->port で選ぶ予定)
    if (!cfg || cfg->port >= 1) {
        usb_disp_log("[HAL] add failed (port %u: only port 0 is supported)",
                     cfg ? cfg->port : 0);
        return NULL;
    }
    if (s_nhal >= USB_DISP_MAX) return NULL;
    struct usb_disp_hal *h = &s_hal[s_nhal++];
    memset(h, 0, sizeof(*h));
    h->in_use = true;
    h->urb_max = USB_DISP_BULK_XFER_SIZE;
    h->ctrl_mutex = xSemaphoreCreateMutex();
    h->ctrl_done = xSemaphoreCreateBinary();
    h->bulk_free = xSemaphoreCreateCounting(USB_DISP_BULK_XFER_COUNT, 0);
    if (s_hub_mutex == NULL) s_hub_mutex = xSemaphoreCreateMutex();
    if (s_hub_done == NULL) s_hub_done = xSemaphoreCreateBinary();
    return h;
}

// 手動サービスモードは Pico 専用の概念 (ESP32 は start と同義 / task は no-op)
void usb_disp_hal_start_manual(void) { usb_disp_hal_start(); }
void usb_disp_hal_task(void) {}

#if CONFIG_USB_HOST_ENABLE_ENUM_FILTER_CALLBACK
// エニュメレーションフィルタ (全デバイス許可)
// コンフィグ番号はスタックが渡してきた既定値のまま使う
static bool enum_filter_cb(const usb_device_desc_t *dev_desc,
                           uint8_t *bConfigurationValue) {
    usb_disp_log("[HAL] enum filter: %04X:%04X (cfg=%u)", dev_desc->idVendor,
                 dev_desc->idProduct, *bConfigurationValue);
    return true;
}
#endif

void usb_disp_hal_start(void) {
    if (s_started || s_nhal == 0) return;
    s_started = true;

    // インストール前に切断期間を置く。
    // マイコンのリブートはバスリセットだけで VBUS が切れないため、
    // DL-1x5 が「ACK はするが映像出力を有効にしない」ウォーム状態
    // (status dword byte1=0x50、フレッシュ時は 0x40) で残る。
    // PHY 未初期化の間はバス無信号 (= デバイスから見て切断相当) なので、
    // インストール自体を遅らせることで毎回挿入直後と同じ状態から始める
    //
    //  ※arduino-esp32 3.3.11 は CONFIG_USB_HOST_ENABLE_ENUM_FILTER_CALLBACK 
    //  を新規有効化しており、enum_filter_cb が NULL のままだと
    //  エニュメレーションが無言でハングする。
    //  下の enum_filter_cb の明示指定が必須。
    vTaskDelay(pdMS_TO_TICKS(USB_DISP_ESP32_SETTLE_MS));

    const usb_host_config_t host_cfg = {
        .skip_phy_setup = false,
        .root_port_unpowered = false,
        .intr_flags = 0,
#if CONFIG_USB_HOST_ENABLE_ENUM_FILTER_CALLBACK
        //  必須: 
        //  この機能が有効なビルド (arduino-esp32 3.3.11 以降のプリビルド等) で
        //  NULL のままにするとエニュメレーションがハングする
        .enum_filter_cb = enum_filter_cb,
#endif
    };
    ESP_ERROR_CHECK(usb_host_install(&host_cfg));

    const usb_host_client_config_t client_cfg = {
        .is_synchronous = false,
        .max_num_event_msg = 8,
        .async = {
            .client_event_callback = client_event_cb,
            .callback_arg = NULL,
        },
    };
    ESP_ERROR_CHECK(usb_host_client_register(&client_cfg, &s_client));

    xTaskCreate(daemon_task, "usbd_daemon", 4096, NULL, 4, NULL);
    xTaskCreate(client_task, "usbd_client", 4096, NULL, 5, NULL);
}

void usb_disp_hal_poll(usb_disp_hal_t *h) {
    // ほぼイベント駆動 (クライアントタスクが処理)。ここでの仕事は
    // 他コンフィグ探索の継続のみ (コントロール転送の完了イベントを
    // 処理する client_task からはブロック転送できないため)
    if (h->pending_probe && h->dev != NULL && !h->gone) {
        h->pending_probe = false;
        probe_and_finish(h);
    }
    // Hub-port watchdog: tracking always runs (so unplugs are observed
    // even while attached); recovery actions only fire while detached.
    // On the attached->detached edge, snapshot idle ports as preexisting
    // (uplinks and steady residents); fresh replugs unmark themselves.
    if (s_watchdog_on) {
        if (s_prev_attached && !h->attached) s_snapshot_idle = true;
        s_prev_attached = h->attached;
        hub_watchdog_step(!h->attached);
    } else {
        s_prev_attached = h->attached;
    }
}

bool usb_disp_hal_attached(usb_disp_hal_t *h) { return h->attached; }
uint16_t usb_disp_hal_vid(usb_disp_hal_t *h) { return h->vid; }
uint16_t usb_disp_hal_pid(usb_disp_hal_t *h) { return h->pid; }

bool usb_disp_hal_ctrl(usb_disp_hal_t *h, const uint8_t setup[8], void *data,
                       uint16_t *actual) {
    if (!h->attached) return false;
    return ctrl_common(h, setup, data, actual);
}

// 書き込み中スロットをサブミットする (呼び出し側で cur != NULL を保証)。
// パイプがエラーで HALT 中 (ESP_ERR_INVALID_STATE) は client_task の
// 復旧を待って再試行する (最大 ~500ms)
static bool submit_cur(struct usb_disp_hal *h) {
    h->cur->num_bytes = (int)h->cur_fill;
    esp_err_t err = ESP_FAIL;
    for (uint8_t tries = 0; tries < 50; tries++) {
        err = usb_host_transfer_submit(h->cur);
        if (err == ESP_OK || !h->attached) break;
        vTaskDelay(pdMS_TO_TICKS(10));  // EP 復旧待ち
    }
    bool ok = (err == ESP_OK);
    if (ok) h->stat_bytes += h->cur_fill;
    if (!ok) {
        // スロットは消費されなかった: 空きカウンタとラウンドロビンを戻す
        h->next_slot = (uint8_t)((h->next_slot + USB_DISP_BULK_XFER_COUNT -
                                  1) % USB_DISP_BULK_XFER_COUNT);
        xSemaphoreGive(h->bulk_free);
    }
    h->cur = NULL;
    h->cur_fill = 0;
    return ok;
}

uint32_t usb_disp_hal_bulk_write(usb_disp_hal_t *h, const void *data,
                                 uint32_t len) {
    if (!h->attached) return 0;
    const uint8_t *src = (const uint8_t *)data;
    uint32_t written = 0;
    while (written < len) {
        if (h->cur == NULL) {
            if (xSemaphoreTake(h->bulk_free, pdMS_TO_TICKS(1000)) != pdTRUE)
                break;  // タイムアウト (デバイス消失等)
            if (!h->attached) break;
            // 投入順 = 完了順なのでラウンドロビンで空きスロットが決まる
            h->cur = h->bulk_xfer[h->next_slot];
            h->next_slot = (uint8_t)((h->next_slot + 1) %
                                     USB_DISP_BULK_XFER_COUNT);
            h->cur->flags = 0;  // 前回の ZERO_PACK が残らないように
            h->cur_fill = 0;
        }
        uint32_t n = h->urb_max - h->cur_fill;
        if (n > len - written) n = len - written;
        memcpy(h->cur->data_buffer + h->cur_fill, src + written, n);
        h->cur_fill += n;
        written += n;
        if (h->cur_fill == h->urb_max) {
            if (!submit_cur(h)) break;
        }
    }
    return written;
}

bool usb_disp_hal_bulk_split(usb_disp_hal_t *h) {
    if (!h->attached) return false;
    if (h->cur && h->cur_fill) return submit_cur(h);
    return true;  // 保留なし = 既に境界
}

bool usb_disp_hal_bulk_zlp(usb_disp_hal_t *h) {
    if (!h->attached) return false;
    if (h->cur && h->cur_fill) {
        // 書き込み中スロットに ZERO_PACK を立てて送出 → フレーム末尾が
        // mps の倍数なら DWC が ZLP を後置する
        h->cur->flags |= USB_TRANSFER_FLAG_ZERO_PACK;
        return submit_cur(h);
    }
    // 保留データなし: 長さ0の転送で ZLP を送る
    if (xSemaphoreTake(h->bulk_free, pdMS_TO_TICKS(1000)) != pdTRUE)
        return false;
    if (!h->attached) {
        xSemaphoreGive(h->bulk_free);
        return false;
    }
    h->cur = h->bulk_xfer[h->next_slot];
    h->next_slot = (uint8_t)((h->next_slot + 1) % USB_DISP_BULK_XFER_COUNT);
    h->cur->flags = 0;
    h->cur_fill = 0;
    return submit_cur(h);  // num_bytes=0 で送信
}

bool usb_disp_hal_bulk_flush(usb_disp_hal_t *h, uint32_t timeout_ms) {
    if (!h->attached) return false;
    if (h->cur && h->cur_fill) {
        if (!submit_cur(h)) return false;
    }
    // 全スロットが空きに戻るまで待つ
    TickType_t deadline = xTaskGetTickCount() + pdMS_TO_TICKS(timeout_ms);
    uint8_t got = 0;
    while (got < USB_DISP_BULK_XFER_COUNT) {
        TickType_t now = xTaskGetTickCount();
        TickType_t remain = (deadline > now) ? (deadline - now) : 0;
        if (xSemaphoreTake(h->bulk_free, remain) != pdTRUE) break;
        got++;
    }
    for (uint8_t i = 0; i < got; i++) xSemaphoreGive(h->bulk_free);
    return got == USB_DISP_BULK_XFER_COUNT;
}

// ---- 大容量FBメモリ = PSRAM (合計使用量を上限管理) ----
// 上限はコンパイル時に -DUSB_DISP_PSRAM_LIMIT_KB=<KB> で指定 (0=無制限)
// PSRAM 非搭載 (または PSRAM 無効ビルド) では heap_caps_malloc が NULL を返す
#ifndef USB_DISP_PSRAM_LIMIT_KB
#define USB_DISP_PSRAM_LIMIT_KB 0
#endif

static uint32_t s_fb_used = 0;

void *usb_disp_hal_fb_alloc(uint32_t size) {
#if USB_DISP_PSRAM_LIMIT_KB > 0
    if (s_fb_used + size > (uint32_t)USB_DISP_PSRAM_LIMIT_KB * 1024u) {
        usb_disp_log("[HAL] fb_alloc %lu KB rejected (limit %u KB, used %lu KB)",
                     (unsigned long)(size / 1024), USB_DISP_PSRAM_LIMIT_KB,
                     (unsigned long)(s_fb_used / 1024));
        return NULL;
    }
#endif
    void *p = heap_caps_malloc(size, MALLOC_CAP_SPIRAM);
    if (p) s_fb_used += size;
    return p;
}

void usb_disp_hal_fb_free(void *p, uint32_t size) {
    if (!p) return;
    heap_caps_free(p);
    s_fb_used = (s_fb_used >= size) ? s_fb_used - size : 0;
}

uint32_t usb_disp_hal_fb_used(void) { return s_fb_used; }

uint64_t usb_disp_hal_stat_bytes(usb_disp_hal_t *h) { return h->stat_bytes; }

uint16_t usb_disp_hal_vendor_desc(usb_disp_hal_t *h, void *buf,
                                  uint16_t maxlen) {
    uint16_t n = h->vdesc_len;
    if (n == 0) return 0;
    if (n > maxlen) n = maxlen;
    memcpy(buf, h->vdesc, n);
    return n;
}

void usb_disp_hal_request_reenum(usb_disp_hal_t *h) {
    // ルートポートの電源 (バス信号) を落として入れ直す = 仮想的な抜き差し。
    // DEV_GONE → client_task の teardown → スタックが再エニュメレーション。
    // 注意: devkit の VBUS は通常 5V 直結なのでデバイスの実電源は切れない
    // (信号レベルの切断のみ)
    (void)h;
    if (!s_started) return;
    usb_disp_log("[HAL] root port power cycle");
    usb_host_lib_set_root_port_power(false);
    vTaskDelay(pdMS_TO_TICKS(200));
    usb_host_lib_set_root_port_power(true);
}

#endif  // USB_DISP_PORT_ESP32

