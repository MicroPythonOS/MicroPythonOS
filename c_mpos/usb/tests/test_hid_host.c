// Host tests for the real ../src/usb_hid.c (compiled in below): claim
// policy, park/backoff, topology re-arm, retire ordering, kbd tick,
// accessors. Single-threaded against fake_usb_host.c: tasks never run,
// the fake clock jumps instead of sleeping.
//
// Build: make -C c_mpos/usb/tests  (or `make usb-host-tests` at repo root)
// Run: ./c_mpos/usb/tests/test_hid_host
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "fake_usb_host.h"

#include "../src/usb_hid.c"

static int s_checks = 0;
static int s_fails = 0;

#define CHECK(cond)                                                            \
    do {                                                                       \
        s_checks++;                                                            \
        if (!(cond)) {                                                         \
            s_fails++;                                                         \
            printf("FAIL %d: %s\n", __LINE__, #cond);                          \
        }                                                                      \
    } while (0)

// Reset production statics (visible: same TU via #include) + fake.
// Autocomplete defaults OFF: with it on, setup-time submits complete
// inline while the slot is already STREAMING, and the completion callback
// resubmits synchronously forever (stack overflow). Production never does
// this (completions are async). Cases opt into autocomplete explicitly.
static void test_reset(void) {
    fake_reset();
    fake_set_autocomplete(false);
    memset(s_slots, 0, sizeof(s_slots));
    memset(s_ring, 0, sizeof(s_ring));
    s_ring_head = 0;
    s_ring_tail = 0;
    s_dropped = 0;
    s_hid_client = NULL;
    s_hid_started = false;
    s_scan_needed = false;
    s_hid_ctrl_mutex = NULL;
    s_hid_ctrl_done = NULL;
    s_kbd_done = NULL;
    s_kbd_poll_task = NULL;
    s_kbd_tick_active = false;
    s_change_gen = 0;
    memset(s_defer, 0, sizeof(s_defer));
    memset(s_topo_addrs, 0, sizeof(s_topo_addrs));
    s_topo_n = -1;
    s_client_last_pump_ms = 0;
    s_kbd_total_polls = 0;
    s_kbd_total_ch = 0;
    s_kbd_transient = false;
    s_hid_verbose = false;
}

// Mirror the client-task loop body: deliver events, scan, per-slot work.
static void pump_client(void) {
    fake_deliver_events();
    if (s_scan_needed) {
        s_scan_needed = false;
        hid_scan();
    }
    for (uint8_t i = 0; i < USB_HID_MAX_DEV; i++) {
        hid_client_task_slot(&s_slots[i]);
    }
}

// Raw config descriptor bytes: config header + one boot-HID iface + one IN EP.
static int build_hid_cfg(uint8_t *b, uint8_t iface, uint8_t sub, uint8_t proto,
                         uint8_t ep, uint16_t mps, uint8_t iv) {
    uint8_t *p = b;
    *p++ = 9;
    *p++ = 2;
    *p++ = 25;
    *p++ = 0;
    *p++ = 1;
    *p++ = 1;
    *p++ = 0;
    *p++ = 0x80;
    *p++ = 50;
    *p++ = 9;
    *p++ = 4;
    *p++ = iface;
    *p++ = 0;
    *p++ = 1;
    *p++ = 0x03;
    *p++ = sub;
    *p++ = proto;
    *p++ = 0;
    *p++ = 7;
    *p++ = 5;
    *p++ = ep;
    *p++ = 0x03;
    *p++ = (uint8_t)mps;
    *p++ = (uint8_t)(mps >> 8);
    *p++ = iv;
    return (int)(p - b);
}

static void plug_mouse(uint8_t addr) {
    uint8_t cfg[32];
    int len = build_hid_cfg(cfg, 0, 1, 2, 0x81, 8, 10);
    fake_plug(addr, 0x17EF, 0x608D, 0x00, USB_SPEED_LOW, cfg, (uint16_t)len);
}

static void plug_keyboard(uint8_t addr) {
    uint8_t cfg[32];
    int len = build_hid_cfg(cfg, 0, 1, 1, 0x81, 8, 10);
    fake_plug(addr, 0x046D, 0xC31C, 0x00, USB_SPEED_LOW, cfg, (uint16_t)len);
}

static void plug_hub(uint8_t addr) {
    fake_plug(addr, 0x1A40, 0x0101, 0x09, USB_SPEED_HIGH, NULL, 0);
}

static hid_slot_t *find_slot(uint8_t addr) {
    for (uint8_t i = 0; i < USB_HID_MAX_DEV; i++) {
        if (s_slots[i].state != HID_SLOT_EMPTY && s_slots[i].addr == addr) {
            return &s_slots[i];
        }
    }
    return NULL;
}

// Stage + set up one mouse and one keyboard; both streaming on return.
static void bringup_mouse_kbd(void) {
    CHECK(usb_hid_start());
    plug_mouse(5);
    plug_keyboard(6);
    fake_queue_new_dev(5);
    fake_queue_new_dev(6);
    pump_client();
    CHECK(usb_hid_poll());
    CHECK(find_slot(5) != NULL && find_slot(5)->state == HID_SLOT_STREAMING);
    CHECK(find_slot(6) != NULL && find_slot(6)->state == HID_SLOT_STREAMING);
}

static void case_start(void) {
    test_reset();
    CHECK(!usb_hid_poll());
    fake_set_register_err(ESP_ERR_INVALID_STATE);
    CHECK(!usb_hid_start());
    test_reset();
    CHECK(usb_hid_start());
    CHECK(fake_client_cb() != NULL);
    CHECK(fake_task_count() == 1);
    CHECK(fake_log_has("client started"));
    CHECK(usb_hid_start());
    CHECK(fake_task_count() == 1);
}

static void case_desc_walk(void) {
    test_reset();
    uint8_t cfg[32];
    uint8_t iface = 0, sub = 0, proto = 0, ep = 0, iv = 0;
    uint16_t mps = 0;
    int len = build_hid_cfg(cfg, 0, 1, 2, 0x81, 8, 10);
    CHECK(hid_find_boot_iface(cfg, (uint16_t)len, &iface, &sub, &proto, &ep, &mps, &iv));
    CHECK(iface == 0 && sub == 1 && proto == 2 && ep == 0x81 && mps == 8);
    CHECK(iv == 50);
    len = build_hid_cfg(cfg, 0, 1, 1, 0x81, 8, 10);
    CHECK(hid_find_boot_iface(cfg, (uint16_t)len, &iface, &sub, &proto, &ep, &mps, &iv));
    CHECK(proto == 1);
    len = build_hid_cfg(cfg, 0, 1, 2, 0x81, 8, 200);
    CHECK(hid_find_boot_iface(cfg, (uint16_t)len, &iface, &sub, &proto, &ep, &mps, &iv));
    CHECK(iv == 100);
    len = build_hid_cfg(cfg, 0, 1, 2, 0x81, 8, 60);
    CHECK(hid_find_boot_iface(cfg, (uint16_t)len, &iface, &sub, &proto, &ep, &mps, &iv));
    CHECK(iv == 60);
    len = build_hid_cfg(cfg, 0, 1, 2, 0x81, 0, 10);
    CHECK(hid_find_boot_iface(cfg, (uint16_t)len, &iface, &sub, &proto, &ep, &mps, &iv));
    CHECK(mps == 64);
    len = build_hid_cfg(cfg, 0, 1, 2, 0x81, 1000, 10);
    CHECK(hid_find_boot_iface(cfg, (uint16_t)len, &iface, &sub, &proto, &ep, &mps, &iv));
    CHECK(mps == 64);
    // Mass-storage iface (class 0x08): not boot HID.
    uint8_t ms[] = {9, 2, 16, 0, 1, 1, 0, 0x80, 50, 9, 4, 0, 0, 1, 0x08,
                    0x06, 0x50, 0};
    CHECK(!hid_find_boot_iface(ms, sizeof(ms), &iface, &sub, &proto, &ep, &mps, &iv));
    // Boot subclass, proto 0 (none): rejected.
    len = build_hid_cfg(cfg, 0, 1, 0, 0x81, 8, 10);
    CHECK(!hid_find_boot_iface(cfg, (uint16_t)len, &iface, &sub, &proto, &ep, &mps, &iv));
    // OUT endpoint only: rejected.
    len = build_hid_cfg(cfg, 0, 1, 2, 0x01, 8, 10);
    CHECK(!hid_find_boot_iface(cfg, (uint16_t)len, &iface, &sub, &proto, &ep, &mps, &iv));
    // Truncated blob: rejected, never over-reads.
    len = build_hid_cfg(cfg, 0, 1, 2, 0x81, 8, 10);
    CHECK(!hid_find_boot_iface(cfg, 10, &iface, &sub, &proto, &ep, &mps, &iv));
}

static void case_scan(void) {
    test_reset();
    CHECK(usb_hid_start());
    plug_hub(1);
    plug_mouse(2);
    uint8_t cfg[32];
    int len = build_hid_cfg(cfg, 0, 0xFF, 0xFF, 0x81, 8, 10);
    fake_plug(3, 0x1234, 0x5678, 0x00, USB_SPEED_FULL, cfg, (uint16_t)len);
    fake_plug(4, 0x1234, 0x5679, 0x00, USB_SPEED_FULL, NULL, 0);
    fake_queue_new_dev(1);
    fake_queue_new_dev(2);
    fake_queue_new_dev(3);
    fake_queue_new_dev(4);
    pump_client();
    CHECK(find_slot(2) != NULL && find_slot(2)->state == HID_SLOT_STAGED);
    CHECK(find_slot(1) == NULL);
    CHECK(find_slot(3) == NULL);
    CHECK(find_slot(4) == NULL);
    hid_slot_t *m = find_slot(2);
    CHECK(m->vid == 0x17EF && m->pid == 0x608D);
    CHECK(m->protocol == 2 && m->ep_in == 0x81 && m->mps == 8);
    CHECK(m->speed == USB_SPEED_LOW && m->interval_ms == 50);
    // Open failure: skipped with a line, never staged.
    test_reset();
    CHECK(usb_hid_start());
    plug_mouse(7);
    fake_set_open_err(7, ESP_ERR_INVALID_STATE);
    fake_queue_new_dev(7);
    pump_client();
    CHECK(find_slot(7) == NULL);
    CHECK(fake_log_has("device_open failed"));
    // Rescan picks it up once the error clears (next NEW_DEV).
    fake_set_open_err(7, ESP_OK);
    fake_queue_new_dev(7);
    pump_client();
    CHECK(find_slot(7) != NULL);
    // No free slot: extra device ignored.
    test_reset();
    CHECK(usb_hid_start());
    for (uint8_t a = 10; a < 10 + USB_HID_MAX_DEV; a++) {
        plug_mouse(a);
        fake_queue_new_dev(a);
    }
    pump_client();
    plug_mouse(30);
    fake_queue_new_dev(30);
    pump_client();
    CHECK(find_slot(30) == NULL);
}

static void case_setup_order(void) {
    test_reset();
    CHECK(usb_hid_start());
    // One global claim: the mouse must win it over the keyboard.
    fake_set_claim_allow(1);
    plug_mouse(5);
    plug_keyboard(6);
    fake_queue_new_dev(5);
    fake_queue_new_dev(6);
    pump_client();
    CHECK(usb_hid_poll());
    CHECK(find_slot(5) != NULL && find_slot(5)->state == HID_SLOT_STREAMING);
    hid_slot_t *k = find_slot(6);
    CHECK(k == NULL);
    usb_hid_parked_t p[4];
    CHECK(usb_hid_parked(p, 4) == 1);
    CHECK(p[0].vid == 0x046D && p[0].fails == 255);
    CHECK(fake_log_has("parked: no HCD channels"));
    // SET_PROTOCOL + SET_IDLE ran for both setups (2 control submits each;
    // the keyboard runs them before failing at claim).
    int ctrls = 0;
    for (int i = 0; i < fake_call_count(); i++) {
        ctrls += (fake_call(i) == FC_SUBMIT_CTRL);
    }
    CHECK(ctrls == 4);
    CHECK(fake_log_has("streaming"));
    // hid_state / claimed_addrs reflect reality.
    usb_hid_state_t st[4];
    CHECK(usb_hid_state(st, 4) == 1);
    CHECK(st[0].addr == 5 && st[0].vid == 0x17EF);
    uint8_t addrs[8];
    CHECK(usb_hid_claimed_addrs(addrs, 8) == 1 && addrs[0] == 5);
    // Retry re-arms the parked keyboard once channels free up (retry clears
    // the defer table; the client-task rescan re-stages; poll sets up).
    fake_set_claim_allow(-1);
    fake_set_claim_err(6, ESP_OK);
    usb_hid_retry();
    pump_client();
    CHECK(usb_hid_poll());
    CHECK(find_slot(6) != NULL && find_slot(6)->state == HID_SLOT_STREAMING);
    CHECK(usb_hid_state(st, 4) == 2);
}

static void case_backoff(void) {
    test_reset();
    CHECK(usb_hid_start());
    plug_keyboard(6);
    fake_set_claim_err(6, ESP_FAIL);
    fake_queue_new_dev(6);
    pump_client();
    CHECK(usb_hid_poll());
    usb_hid_parked_t p[4];
    CHECK(usb_hid_parked(p, 4) == 1 && p[0].fails == 1);
    int claims = 0;
    for (int i = 0; i < fake_call_count(); i++) {
        claims += (fake_call(i) == FC_CLAIM);
    }
    CHECK(claims == 1);
    // Teardown requests a rescan, but the retry only runs once the client
    // task re-stages the slot: every poll below is preceded by a pump,
    // mirroring the production task loop. A retry tears down (gen change,
    // poll true); a skip changes nothing (poll false).
    // Before the 4s due: silent skip, no new claim.
    pump_client();
    CHECK(!usb_hid_poll());
    claims = 0;
    for (int i = 0; i < fake_call_count(); i++) {
        claims += (fake_call(i) == FC_CLAIM);
    }
    CHECK(claims == 1);
    fake_advance_ms(3999);
    pump_client();
    CHECK(!usb_hid_poll());
    claims = 0;
    for (int i = 0; i < fake_call_count(); i++) {
        claims += (fake_call(i) == FC_CLAIM);
    }
    CHECK(claims == 1);
    // Due: second failure, 12s backoff.
    fake_advance_ms(1);
    pump_client();
    CHECK(usb_hid_poll());
    CHECK(usb_hid_parked(p, 4) == 1 && p[0].fails == 2);
    fake_advance_ms(12000);
    pump_client();
    CHECK(usb_hid_poll());
    CHECK(usb_hid_parked(p, 4) == 1 && p[0].fails == 3);
    // Fourth failure parks until replug/retry (fails sticks at 4 with the
    // parked flag set; only the no-channels path uses fails=255).
    fake_advance_ms(28000);
    pump_client();
    CHECK(usb_hid_poll());
    CHECK(usb_hid_parked(p, 4) == 1 && p[0].fails == 4);
    CHECK(fake_log_has("giving up"));
    claims = 0;
    for (int i = 0; i < fake_call_count(); i++) {
        claims += (fake_call(i) == FC_CLAIM);
    }
    fake_advance_ms(60000);
    pump_client();
    CHECK(!usb_hid_poll());
    int claims2 = 0;
    for (int i = 0; i < fake_call_count(); i++) {
        claims2 += (fake_call(i) == FC_CLAIM);
    }
    CHECK(claims2 == claims);
}

static void case_unplug_clears(void) {
    test_reset();
    CHECK(usb_hid_start());
    plug_keyboard(6);
    fake_set_claim_err(6, ESP_ERR_NOT_SUPPORTED);
    fake_queue_new_dev(6);
    pump_client();
    CHECK(usb_hid_poll());
    usb_hid_parked_t p[4];
    CHECK(usb_hid_parked(p, 4) == 1);
    // Physical unplug: DEV_GONE + topology change clears history. Nothing
    // changes during the poll itself (the teardown already ran in pump).
    fake_unplug(6);
    pump_client();
    CHECK(!usb_hid_poll());
    CHECK(usb_hid_parked(p, 4) == 0);
    // Replug starts fresh and streams.
    fake_set_claim_err(6, ESP_OK);
    plug_keyboard(6);
    fake_queue_new_dev(6);
    pump_client();
    CHECK(usb_hid_poll());
    CHECK(find_slot(6) != NULL && find_slot(6)->state == HID_SLOT_STREAMING);
    CHECK(usb_hid_parked(p, 4) == 0);
}

static void case_topo_rearm(void) {
    test_reset();
    CHECK(usb_hid_start());
    plug_keyboard(6);
    fake_set_claim_err(6, ESP_ERR_NOT_SUPPORTED);
    fake_queue_new_dev(6);
    pump_client();
    CHECK(usb_hid_poll());
    usb_hid_parked_t p[4];
    CHECK(usb_hid_parked(p, 4) == 1);
    // An unrelated plug changes the topology: parked retries re-arm.
    fake_set_claim_err(6, ESP_OK);
    plug_mouse(7);
    fake_queue_new_dev(7);
    pump_client();
    CHECK(usb_hid_poll());
    CHECK(usb_hid_parked(p, 4) == 0);
    CHECK(find_slot(6) != NULL && find_slot(6)->state == HID_SLOT_STREAMING);
    CHECK(find_slot(7) != NULL && find_slot(7)->state == HID_SLOT_STREAMING);
    CHECK(fake_log_has("re-armed"));
}

// Index of call c at/after position from; -1 if absent.
static int call_after(fake_call_t c, int from) {
    for (int i = from; i < fake_call_count(); i++) {
        if (fake_call(i) == c) {
            return i;
        }
    }
    return -1;
}

static void case_retire_fast(void) {
    test_reset();
    bringup_mouse_kbd();
    hid_slot_t *m = find_slot(5);
    CHECK(m != NULL);
    // Precondition for the wart: standing URBs in flight, never completing
    // (mouse + keyboard, 2 each).
    CHECK(fake_pending_count() == 2 * USB_HID_XFER_PER_DEV);
    CHECK(m->inflight == USB_HID_XFER_PER_DEV);
    fake_call_clear();
    fake_log_clear();
    m->retire = true;
    int64_t t0 = fake_now_us;
    CHECK(usb_hid_poll());
    CHECK(find_slot(5) == NULL);
    int halt = call_after(FC_HALT, 0);
    int flush = call_after(FC_FLUSH, 0);
    int clear = call_after(FC_CLEAR, 0);
    int release = call_after(FC_RELEASE, 0);
    int close = call_after(FC_CLOSE, 0);
    CHECK(halt >= 0 && flush > halt && clear > flush);
    CHECK(release > clear && close > release);
    CHECK(fake_log_has("retired"));
    CHECK(!fake_log_has("forced"));
    // The wart fix: halt-first reaps promptly instead of burning 3000ms.
    CHECK(fake_now_us - t0 <= 100 * 1000);
    // Only the retired mouse was freed; the keyboard still streams.
    CHECK(fake_live_xfers() == USB_HID_XFER_PER_DEV);
    // Keyboard untouched.
    CHECK(find_slot(6) != NULL && find_slot(6)->state == HID_SLOT_STREAMING);
}

static void case_retire_forced(void) {
    test_reset();
    CHECK(usb_hid_start());
    fake_set_autocomplete(false);
    plug_mouse(5);
    fake_queue_new_dev(5);
    pump_client();
    CHECK(usb_hid_poll());
    hid_slot_t *m = find_slot(5);
    CHECK(m != NULL && m->state == HID_SLOT_STREAMING);
    CHECK(fake_pending_count() == USB_HID_XFER_PER_DEV);
    // Wedged pipe: halt completes nothing, so the bound must burn.
    fake_set_nowedge(true);
    fake_call_clear();
    fake_log_clear();
    m->retire = true;
    int64_t t0 = fake_now_us;
    CHECK(usb_hid_poll());
    CHECK(find_slot(5) == NULL);
    CHECK(fake_log_has("forced"));
    CHECK(fake_now_us - t0 == (3000 + 50) * 1000);
    CHECK(fake_live_xfers() == 0);
}

static void case_ownership(void) {
    test_reset();
    bringup_mouse_kbd();
    hid_slot_t *m = find_slot(5);
    m->retire = true;
    fake_call_clear();
    // The client task must not touch retiring slots (no double teardown).
    pump_client();
    CHECK(find_slot(5) != NULL && find_slot(5)->state == HID_SLOT_STREAMING);
    CHECK(call_after(FC_CLOSE, 0) < 0);
    // The app-thread poll owns them.
    CHECK(usb_hid_poll());
    CHECK(find_slot(5) == NULL);
    // Toggle flip retires live keyboards only, never the mouse.
    usb_hid_set_kbd_transient(true);
    hid_slot_t *k = find_slot(6);
    m = find_slot(5);
    CHECK(m == NULL); // torn down above; re-check via fresh bringup below
    (void)k;
    test_reset();
    bringup_mouse_kbd();
    usb_hid_set_kbd_transient(true);
    m = find_slot(5);
    k = find_slot(6);
    CHECK(m != NULL && !m->retire);
    CHECK(k != NULL && k->retire);
}

static void case_toggle(void) {
    test_reset();
    bringup_mouse_kbd();
    CHECK(!usb_hid_kbd_transient());
    usb_hid_set_kbd_transient(true);
    CHECK(usb_hid_kbd_transient());
    CHECK(usb_hid_poll());
    pump_client();
    CHECK(usb_hid_poll());
    hid_slot_t *k = find_slot(6);
    CHECK(k != NULL && k->state == HID_SLOT_POLLED);
    CHECK(fake_log_has("polled every"));
    bool kbd_task = false;
    for (int i = 0; i < fake_task_count(); i++) {
        kbd_task |= (fake_task_fn(i) != NULL);
    }
    CHECK(kbd_task && fake_task_count() == 2);
    usb_hid_poll_stat_t ps[4];
    CHECK(usb_hid_poll_stats(ps, 4) == 1 && ps[0].addr == 6);
    // Flip back: re-stage as persistent streaming.
    usb_hid_set_kbd_transient(false);
    CHECK(usb_hid_poll());
    pump_client();
    CHECK(usb_hid_poll());
    k = find_slot(6);
    CHECK(k != NULL && k->state == HID_SLOT_STREAMING);
    // Same value twice: no-op, no new log line.
    int nlog = fake_log_count();
    usb_hid_set_kbd_transient(false);
    CHECK(fake_log_count() == nlog);
}

static void case_tick(void) {
    test_reset();
    bringup_mouse_kbd();
    usb_hid_set_kbd_transient(true);
    CHECK(usb_hid_poll());
    pump_client();
    CHECK(usb_hid_poll());
    hid_slot_t *k = find_slot(6);
    CHECK(k != NULL && k->state == HID_SLOT_POLLED);
    uint32_t now = (uint32_t)(fake_now_us / 1000);
    // Not due yet: silent.
    fake_call_clear();
    hid_kbd_tick(now);
    CHECK(call_after(FC_CLAIM, 0) < 0);
    // Due with data: report lands in the ring.
    fake_advance_ms(50);
    now = (uint32_t)(fake_now_us / 1000);
    fake_set_autocomplete(true);
    uint8_t keys[] = {0x00, 0x00, 0x04, 0x00, 0x00, 0x00, 0x00, 0x00};
    fake_set_autocomplete_data(keys, sizeof(keys));
    hid_kbd_tick(now);
    usb_hid_event_t ev[4];
    CHECK(usb_hid_drain(ev, 4) == 1);
    CHECK(ev[0].addr == 6 && ev[0].protocol == 1 && ev[0].len == 8);
    CHECK(ev[0].data[2] == 0x04);
    usb_hid_poll_stat_t ps[4];
    CHECK(usb_hid_poll_stats(ps, 4) == 1 && ps[0].polls == 1);
    // Idle timeout: neutral (no failure), reap clean. Only the 30ms wait
    // burns; the halt completes inline so the 50ms reap Take succeeds.
    fake_set_autocomplete(false);
    fake_advance_ms(50);
    now = (uint32_t)(fake_now_us / 1000);
    int64_t t0 = fake_now_us;
    hid_kbd_tick(now);
    CHECK(usb_hid_drain(ev, 4) == 0);
    CHECK(usb_hid_poll_stats(ps, 4) == 1 && ps[0].polls == 2);
    CHECK(fake_now_us - t0 == 30 * 1000);
    k = find_slot(6);
    CHECK(k != NULL && k->state == HID_SLOT_POLLED);
    // Slow answer between timeout and halt: kept, not dropped.
    fake_advance_ms(50);
    now = (uint32_t)(fake_now_us / 1000);
    fake_set_reap_data(keys, sizeof(keys));
    hid_kbd_tick(now);
    CHECK(usb_hid_drain(ev, 4) == 1 && ev[0].data[2] == 0x04);
    // 50 consecutive channel failures park the keyboard.
    fake_set_autocomplete(true);
    fake_set_claim_err(6, ESP_ERR_NOT_SUPPORTED);
    for (int i = 0; i < 50; i++) {
        fake_advance_ms(50);
        hid_kbd_tick((uint32_t)(fake_now_us / 1000));
    }
    CHECK(find_slot(6) == NULL);
    CHECK(usb_hid_poll_stats(ps, 4) == 0);
    usb_hid_parked_t p[4];
    CHECK(usb_hid_parked(p, 4) == 1 && p[0].fails == 255);
    CHECK(fake_log_has("parking: no channels"));
    // Other failures feed the defer table instead (fails=1, not parked).
    test_reset();
    bringup_mouse_kbd();
    usb_hid_set_kbd_transient(true);
    CHECK(usb_hid_poll());
    pump_client();
    CHECK(usb_hid_poll());
    fake_set_claim_err(6, ESP_FAIL);
    fake_advance_ms(50);
    hid_kbd_tick((uint32_t)(fake_now_us / 1000));
    CHECK(find_slot(6) == NULL);
    CHECK(usb_hid_parked(p, 4) == 1 && p[0].fails == 1);
    // Gone device: teardown clears history.
    test_reset();
    bringup_mouse_kbd();
    usb_hid_set_kbd_transient(true);
    CHECK(usb_hid_poll());
    pump_client();
    CHECK(usb_hid_poll());
    fake_unplug(6);
    fake_deliver_events();
    k = find_slot(6);
    CHECK(k != NULL && k->gone);
    hid_kbd_tick((uint32_t)(fake_now_us / 1000));
    CHECK(find_slot(6) == NULL);
    CHECK(usb_hid_parked(p, 4) == 0);
}

static void case_accessors(void) {
    test_reset();
    CHECK(usb_hid_drain(NULL, 0) == 0);
    usb_hid_state_t st[4];
    CHECK(usb_hid_state(NULL, 0) == 0);
    uint8_t addrs[8];
    CHECK(usb_hid_claimed_addrs(NULL, 0) == 0);
    usb_hid_parked_t p[4];
    CHECK(usb_hid_parked(NULL, 0) == 0);
    usb_hid_poll_stat_t ps[4];
    CHECK(usb_hid_poll_stats(NULL, 0) == 0);
    (void)st;
    (void)addrs;
    (void)p;
    (void)ps;
    // Ring overflow: 70 reports into a 64-slot ring (63 usable: head+1 ==
    // tail means full) drops 7, loudly, once.
    bringup_mouse_kbd();
    usb_hid_set_kbd_transient(true);
    CHECK(usb_hid_poll());
    pump_client();
    CHECK(usb_hid_poll());
    fake_set_autocomplete(true);
    uint8_t keys[] = {0x00, 0x00, 0x04, 0x00, 0x00, 0x00, 0x00, 0x00};
    fake_set_autocomplete_data(keys, sizeof(keys));
    for (int i = 0; i < 70; i++) {
        fake_advance_ms(50);
        hid_kbd_tick((uint32_t)(fake_now_us / 1000));
    }
    usb_hid_event_t ev[64];
    CHECK(usb_hid_drain(ev, 64) == 63);
    CHECK(usb_hid_drain(ev, 64) == 0);
    CHECK(fake_log_has("dropped 7"));
    // Second drain: counter reset, no repeat.
    fake_log_clear();
    CHECK(usb_hid_drain(ev, 64) == 0);
    CHECK(!fake_log_has("dropped"));
}

static void case_owns_idle_port(void) {
    test_reset();
    CHECK(usb_hid_start());
    plug_hub(1);
    plug_mouse(2);
    plug_keyboard(3);
    fake_set_parent(2, 1, 1);
    fake_set_parent(3, 1, 4);
    fake_queue_new_dev(1);
    fake_queue_new_dev(2);
    fake_queue_new_dev(3);
    pump_client();
    CHECK(usb_hid_poll());
    CHECK(find_slot(2) != NULL && find_slot(2)->state == HID_SLOT_STREAMING);
    CHECK(find_slot(3) != NULL && find_slot(3)->state == HID_SLOT_STREAMING);
    CHECK(usb_hid_owns_idle_port(1, 1));
    CHECK(usb_hid_owns_idle_port(1, 4));
    CHECK(!usb_hid_owns_idle_port(1, 2));
    CHECK(!usb_hid_owns_idle_port(1, 3));
    CHECK(!usb_hid_owns_idle_port(9, 1));
    CHECK(!usb_hid_owns_idle_port(1, 0));
    // Unreadable device info fails safe (no match, never a wrong match).
    fake_set_info_err(2, ESP_FAIL);
    CHECK(!usb_hid_owns_idle_port(1, 1));
    CHECK(usb_hid_owns_idle_port(1, 4));
    fake_set_info_err(2, ESP_OK);
    CHECK(usb_hid_owns_idle_port(1, 1));
    // A staged (not yet set up) slot already counts: open handle, ours.
    test_reset();
    CHECK(usb_hid_start());
    plug_hub(1);
    plug_mouse(2);
    fake_set_parent(2, 1, 1);
    fake_queue_new_dev(1);
    fake_queue_new_dev(2);
    pump_client();
    CHECK(find_slot(2) != NULL && find_slot(2)->state == HID_SLOT_STAGED);
    CHECK(usb_hid_owns_idle_port(1, 1));
    // Torn-down slots stop matching once the handle closes.
    fake_unplug(2);
    pump_client();
    CHECK(usb_hid_poll());
    CHECK(find_slot(2) == NULL);
    CHECK(!usb_hid_owns_idle_port(1, 1));
}

static void case_lag_gen(void) {    test_reset();
    CHECK(usb_hid_start());
    uint32_t a = usb_hid_loop_lag_ms();
    fake_advance_ms(500);
    CHECK(usb_hid_loop_lag_ms() == a + 500);
    uint32_t gen = usb_hid_change_gen();
    CHECK(!usb_hid_poll());
    CHECK(usb_hid_change_gen() == gen);
    plug_mouse(5);
    fake_queue_new_dev(5);
    pump_client();
    CHECK(usb_hid_poll());
    CHECK(usb_hid_change_gen() != gen);
}

int main(void) {
    case_start();
    case_desc_walk();
    case_scan();
    case_setup_order();
    case_backoff();
    case_unplug_clears();
    case_topo_rearm();
    case_retire_fast();
    case_retire_forced();
    case_ownership();
    case_toggle();
    case_tick();
    case_accessors();
    case_owns_idle_port();
    case_lag_gen();
    printf("hid-host: %d checks, %d failures\n", s_checks, s_fails);
    return s_fails != 0;
}
