// `usb` module: USB host support for ESP32 (DisplayLink display adapters
// plus a minimal HID host transport for boot-protocol mice + keyboards).
// Display-class code lives in usb_display_mpy.c; HID transport in
// usb_hid.c. This file owns module-level host/hub/watchdog/HID functions.

#include <stdarg.h>
#include <stdio.h>
#include <string.h>

#include "py/obj.h"
#include "py/runtime.h"

#include "usb/usb_host.h"
#include "usb_disp.h"
#include "usb_disp_hal.h"
#include "usb_hid.h"

extern const mp_obj_type_t mp_type_usb_display;

// Upstream's default usb_disp_log is a no-op outside Arduino. Route all
// library logs to the console (UART REPL during USB-host bringup) instead.
// (The name is upstream's: usb_disp.h declares it, usb_hid.c calls it.)
static bool s_usb_disp_log_on = true;

void usb_disp_log(const char *fmt, ...) {
    if (!s_usb_disp_log_on) {
        return;
    }
    char buf[192];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(buf, sizeof(buf), fmt, ap);
    va_end(ap);
    printf("%s\n", buf);
}

static mp_obj_t mp_usb_set_log(mp_obj_t on_in) {
    s_usb_disp_log_on = mp_obj_is_true(on_in);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(mp_usb_set_log_obj, mp_usb_set_log);

// bus_devices() - list of USB device addresses currently seen by the host
// stack. Hubs and the adapter show up here once enumerated, whether or not
// our display claimed them (a claimed adapter leaves the stack's idle
// list, so it is re-added here explicitly). Empty list = nothing sensed
// (cable/power/stack). Safe to call from any thread; never raises.
static mp_obj_t mp_usb_bus_devices(void) {
    uint8_t addrs[16];
    int n = 0;
    mp_obj_t list = mp_obj_new_list(0, NULL);
    if (usb_host_device_addr_list_fill((int)sizeof(addrs), addrs, &n) != ESP_OK) {
        return list;
    }
    uint8_t claimed = 0;
    bool have_claimed = usb_disp_hal_claimed_addr(&claimed);
    uint8_t hid_addrs[8];
    uint8_t n_hid = usb_hid_claimed_addrs(hid_addrs, (uint8_t)sizeof(hid_addrs));
    for (int i = 0; i < n; i++) {
        mp_obj_list_append(list, mp_obj_new_int(addrs[i]));
    }
    // Claimed devices (display + HID) left the stack's idle list, so
    // re-add any that bus_devices() did not report.
    uint8_t extra[9];
    uint8_t n_extra = 0;
    if (have_claimed) {
        extra[n_extra++] = claimed;
    }
    for (uint8_t i = 0; i < n_hid && n_extra < (uint8_t)sizeof(extra); i++) {
        extra[n_extra++] = hid_addrs[i];
    }
    for (uint8_t i = 0; i < n_extra; i++) {
        bool seen = false;
        for (int k = 0; k < n; k++) {
            if (addrs[k] == extra[i]) {
                seen = true;
                break;
            }
        }
        if (!seen) {
            mp_obj_list_append(list, mp_obj_new_int(extra[i]));
        }
    }
    return list;
}
static MP_DEFINE_CONST_FUN_OBJ_0(mp_usb_bus_devices_obj, mp_usb_bus_devices);

// hub_ports() - [(hub_addr, port, connected, enabled, high_speed), ...]
// for every external-hub port on the bus. Read-only standard hub
// requests; safe to call any time. A port stuck at (connected=True,
// enabled=False) is one the IDF stack gave up on (single-shot
// enumeration of a still-booting device) - reset_port() it or wait
// for the watchdog. high_speed ports (hub-to-hub uplinks) are never
// auto-reset: resetting one drops the whole subtree and crashes the
// IDF enumerator (abort in enum.c control_request_string).
static mp_obj_t mp_usb_hub_ports_fn(void) {
    usb_disp_hub_port_t ports[32];
    uint8_t n = usb_disp_hal_hub_ports(ports, (uint8_t)sizeof(ports) / sizeof(ports[0]));
    mp_obj_t list = mp_obj_new_list(0, NULL);
    for (uint8_t i = 0; i < n; i++) {
        mp_obj_t t[5];
        t[0] = mp_obj_new_int(ports[i].hub_addr);
        t[1] = mp_obj_new_int(ports[i].port);
        t[2] = mp_obj_new_bool(ports[i].connected);
        t[3] = mp_obj_new_bool(ports[i].enabled);
        t[4] = mp_obj_new_bool(ports[i].high_speed);
        mp_obj_list_append(list, mp_obj_new_tuple(5, t));
    }
    return list;
}
static MP_DEFINE_CONST_FUN_OBJ_0(mp_usb_hub_ports_obj, mp_usb_hub_ports_fn);

// reset_port(hub_addr, port, power_cycle=False, force=False) - re-enumerate
// one hub port without touching the rest of the chain. PORT_RESET
// (default) keeps VBUS up, so an already-booted device enumerates
// immediately; power_cycle=True drops VBUS for ~300ms first (stronger,
// but slow and may drop sibling ports on ganged-power hubs).
// High-speed ports (hub-to-hub uplinks) are refused unless force=True:
// resetting one drops the whole subtree and crashes the IDF enumerator.
// Manual recovery for a wedged port.
static mp_obj_t mp_usb_reset_port_fn(size_t n_args, const mp_obj_t *args) {
    uint8_t hub_addr = (uint8_t)mp_obj_get_int(args[0]);
    uint8_t port = (uint8_t)mp_obj_get_int(args[1]);
    bool power_cycle = (n_args > 2) && mp_obj_is_true(args[2]);
    bool force = (n_args > 3) && mp_obj_is_true(args[3]);
    return mp_obj_new_bool(usb_disp_hal_reset_hub_port(hub_addr, port, power_cycle, force));
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(mp_usb_reset_port_obj, 2, 4, mp_usb_reset_port_fn);

// lsusb() - Linux-style USB listing ("Bus 001 Device 002: ID 17e9:028f
// DisplayLink ..."). Bus is always 001 (single OTG controller); no
// root-hub line. Read-only, safe any time.
static char s_lsusb_buf[2048];
static mp_obj_t mp_usb_lsusb_fn(void) {
    uint16_t used = usb_disp_hal_lsusb(s_lsusb_buf, sizeof(s_lsusb_buf));
    // HID-held devices usually stay in the stack's idle list, so the HAL
    // pass above already printed them with full string descriptors
    // ("PixArt Lenovo USB Optical Mouse" beats "HID mouse"). Append a
    // generic line only for held devices the HAL pass skipped (same
    // reason bus_devices() re-adds held addresses: a claimed device can
    // drop out of the idle list, like the streaming display does).
    uint8_t addrs[16];
    int n = 0;
    bool have_list = (usb_host_device_addr_list_fill((int)sizeof(addrs), addrs, &n) == ESP_OK);
    usb_hid_state_t st[4];
    uint8_t n_hid = usb_hid_state(st, 4);
    for (uint8_t i = 0; i < n_hid && used + 64 < sizeof(s_lsusb_buf); i++) {
        bool seen = false;
        if (have_list) {
            for (int k = 0; k < n; k++) {
                if (addrs[k] == st[i].addr) {
                    seen = true;
                    break;
                }
            }
        }
        if (seen) {
            continue;
        }
        const char *kind = st[i].protocol == 2 ? "mouse" : "keyboard";
        int w = snprintf(s_lsusb_buf + used, sizeof(s_lsusb_buf) - used,
                         "Bus 001 Device %03d: ID %04x:%04x HID %s\n",
                         st[i].addr, st[i].vid, st[i].pid, kind);
        if (w < 0 || (uint16_t)w >= sizeof(s_lsusb_buf) - used) {
            break;
        }
        used = (uint16_t)(used + w);
    }
    return mp_obj_new_str(s_lsusb_buf, used);
}
static MP_DEFINE_CONST_FUN_OBJ_0(mp_usb_lsusb_obj, mp_usb_lsusb_fn);

// set_watchdog(on) - enable/disable the hub-port watchdog (default on).
// The watchdog only acts while no display is attached; healthy ports
// are never touched.
static mp_obj_t mp_usb_set_watchdog_fn(mp_obj_t on_in) {
    usb_disp_hal_set_watchdog(mp_obj_is_true(on_in));
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(mp_usb_set_watchdog_obj, mp_usb_set_watchdog_fn);

// set_auto_reset_idle([on]) - with no args, return the toggle state;
// with an arg, toggle automatic single PORT_RESET of idle ports that
// are not marked preexisting (default on). Marks are set for idle ports
// seen at boot, hub plug, and display-unplug snapshots, and cleared by
// any observed disconnect, so healthy uplinks are never selected while
// replugged adapters heal without hands. One shot per mark cycle.
static mp_obj_t mp_usb_set_auto_reset_idle_fn(size_t n_args, const mp_obj_t *args) {
    if (n_args == 0) {
        return mp_obj_new_bool(usb_disp_hal_auto_reset_idle());
    }
    usb_disp_hal_set_auto_reset_idle(mp_obj_is_true(args[0]));
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(mp_usb_set_auto_reset_idle_obj, 0, 1, mp_usb_set_auto_reset_idle_fn);

// hid_start() - register the HID client (own task) on the shared host
// stack. False when the stack is not up yet (USBManager.arm_display runs
// first); idempotent, safe to retry from the 1s poll timer.
static mp_obj_t mp_usb_hid_start_fn(void) {
    return mp_obj_new_bool(usb_hid_start());
}
static MP_DEFINE_CONST_FUN_OBJ_0(mp_usb_hid_start_obj, mp_usb_hid_start_fn);

// hid_poll() - pump staged HID setups and claim health checks. True on
// device-set change (connect/disconnect), like Display.poll().
static uint32_t s_hid_last_gen = 0;
static mp_obj_t mp_usb_hid_poll_fn(void) {
    usb_hid_poll();
    uint32_t gen = usb_hid_change_gen();
    bool changed = (gen != s_hid_last_gen);
    s_hid_last_gen = gen;
    return mp_obj_new_bool(changed);
}
static MP_DEFINE_CONST_FUN_OBJ_0(mp_usb_hid_poll_obj, mp_usb_hid_poll_fn);

// hid_drain() - [(addr, subclass, protocol, bytes), ...] input reports
// since the last call. Raw boot reports; parsing is Python-side so new
// device kinds never need C changes.
static mp_obj_t mp_usb_hid_drain_fn(void) {
    usb_hid_event_t ev[16];
    uint8_t n = usb_hid_drain(ev, (uint8_t)(sizeof(ev) / sizeof(ev[0])));
    mp_obj_t list = mp_obj_new_list(0, NULL);
    for (uint8_t i = 0; i < n; i++) {
        mp_obj_t t[4];
        t[0] = mp_obj_new_int(ev[i].addr);
        t[1] = mp_obj_new_int(ev[i].subclass);
        t[2] = mp_obj_new_int(ev[i].protocol);
        t[3] = mp_obj_new_bytes(ev[i].data, ev[i].len);
        mp_obj_list_append(list, mp_obj_new_tuple(4, t));
    }
    return list;
}
static MP_DEFINE_CONST_FUN_OBJ_0(mp_usb_hid_drain_obj, mp_usb_hid_drain_fn);

// hid_state() - [(addr, kind, vid, pid, speed), ...] for streaming HID
// devices. kind is "mouse" or "keyboard"; speed is 0=low, 1=full,
// 2=high (low-speed devices behind a hub need split transactions).
static mp_obj_t mp_usb_hid_state_fn(void) {
    usb_hid_state_t st[4];
    uint8_t n = usb_hid_state(st, 4);
    mp_obj_t list = mp_obj_new_list(0, NULL);
    for (uint8_t i = 0; i < n; i++) {
        mp_obj_t t[5];
        t[0] = mp_obj_new_int(st[i].addr);
        const char *kind = st[i].protocol == 2 ? "mouse" : "keyboard";
        t[1] = mp_obj_new_str(kind, strlen(kind));
        t[2] = mp_obj_new_int(st[i].vid);
        t[3] = mp_obj_new_int(st[i].pid);
        t[4] = mp_obj_new_int(st[i].speed);
        mp_obj_list_append(list, mp_obj_new_tuple(5, t));
    }
    return list;
}
static MP_DEFINE_CONST_FUN_OBJ_0(mp_usb_hid_state_obj, mp_usb_hid_state_fn);

// hid_claimed_addrs() - [addr, ...] held open by the HID client. The hub
// watchdog's idle auto-reset must skip these (a healthy mouse reads
// exactly like a wedged adapter: connected + enabled, no bus growth);
// bus_devices()/lsusb re-add them for the same reason as the display.
static mp_obj_t mp_usb_hid_claimed_addrs_fn(void) {
    uint8_t addrs[8];
    uint8_t n = usb_hid_claimed_addrs(addrs, (uint8_t)sizeof(addrs));
    mp_obj_t list = mp_obj_new_list(0, NULL);
    for (uint8_t i = 0; i < n; i++) {
        mp_obj_list_append(list, mp_obj_new_int(addrs[i]));
    }
    return list;
}
static MP_DEFINE_CONST_FUN_OBJ_0(mp_usb_hid_claimed_addrs_obj, mp_usb_hid_claimed_addrs_fn);

// hid_parked() - [(vid, pid, kind, fails), ...] devices whose setup keeps
// failing and are parked (fails=255) or cooling down. Parked devices stay
// silent until a bus topology change or hid_retry().
static mp_obj_t mp_usb_hid_parked_fn(void) {
    usb_hid_parked_t p[4];
    uint8_t n = usb_hid_parked(p, 4);
    mp_obj_t list = mp_obj_new_list(0, NULL);
    for (uint8_t i = 0; i < n; i++) {
        mp_obj_t t[4];
        t[0] = mp_obj_new_int(p[i].vid);
        t[1] = mp_obj_new_int(p[i].pid);
        const char *kind = p[i].protocol == 2 ? "mouse" : "keyboard";
        t[2] = mp_obj_new_str(kind, strlen(kind));
        t[3] = mp_obj_new_int(p[i].fails);
        mp_obj_list_append(list, mp_obj_new_tuple(4, t));
    }
    return list;
}
static MP_DEFINE_CONST_FUN_OBJ_0(mp_usb_hid_parked_obj, mp_usb_hid_parked_fn);

// hid_retry() - clear the parked/cooldown list and rescan now. Topology
// changes (plug/unplug) re-arm automatically; this is the manual version.
static mp_obj_t mp_usb_hid_retry_fn(void) {
    usb_hid_retry();
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(mp_usb_hid_retry_obj, mp_usb_hid_retry_fn);

// hid_poll_stats() - [(addr, kind, polls, ch_fails), ...] for live
// transiently-polled keyboards. Sample twice and diff polls for the
// effective poll rate; ch_fails counts channel-exhaustion ticks.
static mp_obj_t mp_usb_hid_poll_stats_fn(void) {
    usb_hid_poll_stat_t ps[4];
    uint8_t n = usb_hid_poll_stats(ps, 4);
    mp_obj_t list = mp_obj_new_list(0, NULL);
    for (uint8_t i = 0; i < n; i++) {
        mp_obj_t t[4];
        t[0] = mp_obj_new_int(ps[i].addr);
        const char *kind = ps[i].protocol == 2 ? "mouse" : "keyboard";
        t[1] = mp_obj_new_str(kind, strlen(kind));
        t[2] = mp_obj_new_int(ps[i].polls);
        t[3] = mp_obj_new_int(ps[i].ch_fails);
        mp_obj_list_append(list, mp_obj_new_tuple(4, t));
    }
    return list;
}
static MP_DEFINE_CONST_FUN_OBJ_0(mp_usb_hid_poll_stats_obj, mp_usb_hid_poll_stats_fn);

// hid_loop_lag() - ms since the HID client task last pumped stack
// events. Reads ~100 in steady state; seconds indicate event delivery
// (completions, teardowns, rescans) is stalled.
static mp_obj_t mp_usb_hid_loop_lag_fn(void) {
    return mp_obj_new_int((mp_int_t)usb_hid_loop_lag_ms());
}
static MP_DEFINE_CONST_FUN_OBJ_0(mp_usb_hid_loop_lag_obj, mp_usb_hid_loop_lag_fn);

// hid_set_kbd_transient([on]) - keyboard transport mode experiment.
// Default (persistent, False): keyboards claim like mice. True selects
// transient per-tick polling (needed under display channel pressure).
// Bare call reads back. Live keyboards re-stage on flip.
static mp_obj_t mp_usb_hid_set_kbd_transient_fn(size_t n_args, const mp_obj_t *args) {
    if (n_args == 0) {
        return mp_obj_new_bool(usb_hid_kbd_transient());
    }
    usb_hid_set_kbd_transient(mp_obj_is_true(args[0]));
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(mp_usb_hid_set_kbd_transient_obj, 0, 1,
                                           mp_usb_hid_set_kbd_transient_fn);

// hid_verbose([on]) - with no args, return the per-tick debug flag;
// with an arg, set it. Off by default; when on, each transient tick
// logs [HID][V] claim/submit/wait outcomes (only useful while actively
// debugging input, ~100 lines/s otherwise).
static mp_obj_t mp_usb_hid_verbose_fn(size_t n_args, const mp_obj_t *args) {
    if (n_args == 0) {
        return mp_obj_new_bool(usb_hid_verbose());
    }
    usb_hid_set_verbose(mp_obj_is_true(args[0]));
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(mp_usb_hid_verbose_obj, 0, 1, mp_usb_hid_verbose_fn);

static const mp_rom_map_elem_t usb_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_usb) },
    { MP_ROM_QSTR(MP_QSTR_Display), MP_ROM_PTR(&mp_type_usb_display) },
    { MP_ROM_QSTR(MP_QSTR_set_log), MP_ROM_PTR(&mp_usb_set_log_obj) },
    { MP_ROM_QSTR(MP_QSTR_bus_devices), MP_ROM_PTR(&mp_usb_bus_devices_obj) },
    { MP_ROM_QSTR(MP_QSTR_lsusb), MP_ROM_PTR(&mp_usb_lsusb_obj) },
    { MP_ROM_QSTR(MP_QSTR_hub_ports), MP_ROM_PTR(&mp_usb_hub_ports_obj) },
    { MP_ROM_QSTR(MP_QSTR_reset_port), MP_ROM_PTR(&mp_usb_reset_port_obj) },
    { MP_ROM_QSTR(MP_QSTR_set_watchdog), MP_ROM_PTR(&mp_usb_set_watchdog_obj) },
    { MP_ROM_QSTR(MP_QSTR_auto_reset_idle), MP_ROM_PTR(&mp_usb_set_auto_reset_idle_obj) },
    { MP_ROM_QSTR(MP_QSTR_hid_start), MP_ROM_PTR(&mp_usb_hid_start_obj) },
    { MP_ROM_QSTR(MP_QSTR_hid_poll), MP_ROM_PTR(&mp_usb_hid_poll_obj) },
    { MP_ROM_QSTR(MP_QSTR_hid_drain), MP_ROM_PTR(&mp_usb_hid_drain_obj) },
    { MP_ROM_QSTR(MP_QSTR_hid_state), MP_ROM_PTR(&mp_usb_hid_state_obj) },
    { MP_ROM_QSTR(MP_QSTR_hid_claimed_addrs), MP_ROM_PTR(&mp_usb_hid_claimed_addrs_obj) },
    { MP_ROM_QSTR(MP_QSTR_hid_parked), MP_ROM_PTR(&mp_usb_hid_parked_obj) },
    { MP_ROM_QSTR(MP_QSTR_hid_retry), MP_ROM_PTR(&mp_usb_hid_retry_obj) },
    { MP_ROM_QSTR(MP_QSTR_hid_poll_stats), MP_ROM_PTR(&mp_usb_hid_poll_stats_obj) },
    { MP_ROM_QSTR(MP_QSTR_hid_verbose), MP_ROM_PTR(&mp_usb_hid_verbose_obj) },
    { MP_ROM_QSTR(MP_QSTR_hid_loop_lag), MP_ROM_PTR(&mp_usb_hid_loop_lag_obj) },
    { MP_ROM_QSTR(MP_QSTR_hid_set_kbd_transient), MP_ROM_PTR(&mp_usb_hid_set_kbd_transient_obj) },
};

static MP_DEFINE_CONST_DICT(usb_module_globals, usb_module_globals_table);

const mp_obj_module_t usb_user_cmodule = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&usb_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR_usb, usb_user_cmodule);
