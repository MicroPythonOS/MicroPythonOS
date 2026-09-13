// MicroPython binding for Pico_USB_Disp (DisplayLink USB display adapters).
// ESP32-only PoC. Single display use is expected (USB_DISP_MAX == 1 on ESP32)
// but the type supports handles generally.
//
// Pins are fixed on ESP32 (native USB OTG, GPIO19/20), so only the port
// number is needed. Resolution 0x0 means EDID automatic selection.

#include <stdarg.h>
#include <stdio.h>
#include <string.h>

#include "py/obj.h"
#include "py/runtime.h"

#include "usb/usb_host.h"
#include "usb_disp.h"
#include "usb_disp_hal.h"
#include "usb_hid.h"

// Upstream's default usb_disp_log is a no-op outside Arduino. Route all
// library logs to the console (UART REPL during USB-host PoC) instead.
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

typedef struct _mp_obj_usbdisp_t {
    mp_obj_base_t base;
    usb_disp_t *disp;
} mp_obj_usbdisp_t;

static const mp_obj_type_t mp_type_usbdisp;

static mp_obj_t usbdisp_force_reenum(mp_obj_t self_in);

static bool s_usb_disp_inited = false;

static mp_obj_usbdisp_t *usbdisp_get_self(mp_obj_t self_in) {
    mp_obj_usbdisp_t *self = MP_OBJ_TO_PTR(self_in);
    if (self->disp == NULL) {
        mp_raise_ValueError(MP_ERROR_TEXT("display not added"));
    }
    return self;
}

// USBDisp(port=0, width=0, height=0, ignore_edid=False)
static mp_obj_t usbdisp_make_new(const mp_obj_type_t *type, size_t n_args, size_t n_kw, const mp_obj_t *args) {
    enum { ARG_port, ARG_width, ARG_height, ARG_ignore_edid };
    static const mp_arg_t allowed_args[] = {
        { MP_QSTR_port, MP_ARG_INT, {.u_int = 0} },
        { MP_QSTR_width, MP_ARG_INT, {.u_int = 0} },
        { MP_QSTR_height, MP_ARG_INT, {.u_int = 0} },
        { MP_QSTR_ignore_edid, MP_ARG_BOOL, {.u_bool = false} },
    };
    mp_arg_val_t parsed[MP_ARRAY_SIZE(allowed_args)];
    mp_arg_parse_all_kw_array(n_args, n_kw, args, MP_ARRAY_SIZE(allowed_args), allowed_args, parsed);

    if (!s_usb_disp_inited) {
        usb_disp_init();
        s_usb_disp_inited = true;
    }

    // Upstream has no remove API and ESP32 allows a single display, so a
    // slot once added is taken forever. Reuse it: this makes REPL retries
    // after a boot-time timeout and repeated constructions work. The
    // original width/height config is kept; use set_mode() to change it.
    usb_disp_t *d;
    if (usb_disp_count() > 0) {
        d = usb_disp_at(0);
    } else {
        d = usb_disp_add(
            (uint8_t)parsed[ARG_port].u_int,
            0, 0,
            (uint16_t)parsed[ARG_width].u_int,
            (uint16_t)parsed[ARG_height].u_int,
            parsed[ARG_ignore_edid].u_bool);
    }
    if (d == NULL) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("usb_disp_add failed"));
    }

    mp_obj_usbdisp_t *self = mp_obj_malloc(mp_obj_usbdisp_t, type);
    self->disp = d;
    return MP_OBJ_FROM_PTR(self);
}

// start() - start the USB host for all registered ports (call once)
static mp_obj_t usbdisp_start(mp_obj_t self_in) {
    (void)self_in;
    usb_disp_start();
    return mp_const_none;
}

// poll() - drive enumeration/mode setup; True on READY/disconnect/mode change
static mp_obj_t usbdisp_poll(mp_obj_t self_in) {
    mp_obj_usbdisp_t *self = usbdisp_get_self(self_in);
    return mp_obj_new_bool(usb_disp_poll(self->disp));
}

static mp_obj_t usbdisp_ready(mp_obj_t self_in) {
    mp_obj_usbdisp_t *self = usbdisp_get_self(self_in);
    return mp_obj_new_bool(usb_disp_ready(self->disp));
}

static mp_obj_t usbdisp_width(mp_obj_t self_in) {
    mp_obj_usbdisp_t *self = usbdisp_get_self(self_in);
    return mp_obj_new_int(usb_disp_width(self->disp));
}

static mp_obj_t usbdisp_height(mp_obj_t self_in) {
    mp_obj_usbdisp_t *self = usbdisp_get_self(self_in);
    return mp_obj_new_int(usb_disp_height(self->disp));
}

// update_565(x, y, w, h, buf) - queue an RGB565 rectangle; pixels are copied
// synchronously into the bulk ring, buf may be reused right after return.
static mp_obj_t usbdisp_update_565(size_t n_args, const mp_obj_t *args) {
    mp_obj_usbdisp_t *self = usbdisp_get_self(args[0]);
    uint16_t x = (uint16_t)mp_obj_get_int(args[1]);
    uint16_t y = (uint16_t)mp_obj_get_int(args[2]);
    uint16_t w = (uint16_t)mp_obj_get_int(args[3]);
    uint16_t h = (uint16_t)mp_obj_get_int(args[4]);
    mp_buffer_info_t bufinfo;
    mp_get_buffer_raise(args[5], &bufinfo, MP_BUFFER_READ);
    if (bufinfo.len < (size_t)w * h * 2) {
        mp_raise_ValueError(MP_ERROR_TEXT("buffer too small"));
    }
    bool ok = usb_disp_update_565(self->disp, x, y, w, h, (const uint16_t *)bufinfo.buf, w);
    return mp_obj_new_bool(ok);
}

// fill(x, y, w, h, color) - solid RGB565 fill
static mp_obj_t usbdisp_fill(size_t n_args, const mp_obj_t *args) {
    mp_obj_usbdisp_t *self = usbdisp_get_self(args[0]);
    bool ok = usb_disp_fill(self->disp,
        (uint16_t)mp_obj_get_int(args[1]),
        (uint16_t)mp_obj_get_int(args[2]),
        (uint16_t)mp_obj_get_int(args[3]),
        (uint16_t)mp_obj_get_int(args[4]),
        (uint16_t)mp_obj_get_int(args[5]));
    (void)n_args;
    return mp_obj_new_bool(ok);
}

// flush(timeout_ms=100) - submit queued data and wait for completion
static mp_obj_t usbdisp_flush(size_t n_args, const mp_obj_t *args) {
    mp_obj_usbdisp_t *self = usbdisp_get_self(args[0]);
    uint32_t timeout = 100;
    if (n_args > 1) {
        timeout = (uint32_t)mp_obj_get_int(args[1]);
    }
    return mp_obj_new_bool(usb_disp_flush(self->disp, timeout));
}

// set_mode(width, height) - change resolution at 60Hz (redraw required)
static mp_obj_t usbdisp_set_mode(mp_obj_t self_in, mp_obj_t w_in, mp_obj_t h_in) {
    mp_obj_usbdisp_t *self = usbdisp_get_self(self_in);
    bool ok = usb_disp_set_mode(self->disp, (uint16_t)mp_obj_get_int(w_in), (uint16_t)mp_obj_get_int(h_in));
    return mp_obj_new_bool(ok);
}

static mp_obj_t usbdisp_chip_name(mp_obj_t self_in) {
    mp_obj_usbdisp_t *self = usbdisp_get_self(self_in);
    const char *name = usb_disp_chip_name(self->disp);
    if (name == NULL) {
        return mp_const_none;
    }
    return mp_obj_new_str(name, strlen(name));
}

static MP_DEFINE_CONST_FUN_OBJ_1(usbdisp_start_obj, usbdisp_start);
static MP_DEFINE_CONST_FUN_OBJ_1(usbdisp_poll_obj, usbdisp_poll);
static MP_DEFINE_CONST_FUN_OBJ_1(usbdisp_ready_obj, usbdisp_ready);
static MP_DEFINE_CONST_FUN_OBJ_1(usbdisp_width_obj, usbdisp_width);
static MP_DEFINE_CONST_FUN_OBJ_1(usbdisp_height_obj, usbdisp_height);
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(usbdisp_update_565_obj, 6, 6, usbdisp_update_565);
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(usbdisp_fill_obj, 6, 6, usbdisp_fill);
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(usbdisp_flush_obj, 1, 2, usbdisp_flush);
static MP_DEFINE_CONST_FUN_OBJ_3(usbdisp_set_mode_obj, usbdisp_set_mode);
static MP_DEFINE_CONST_FUN_OBJ_1(usbdisp_chip_name_obj, usbdisp_chip_name);

static MP_DEFINE_CONST_FUN_OBJ_1(usbdisp_force_reenum_obj, usbdisp_force_reenum);

static const mp_rom_map_elem_t usbdisp_locals_table[] = {
    { MP_ROM_QSTR(MP_QSTR_start), MP_ROM_PTR(&usbdisp_start_obj) },
    { MP_ROM_QSTR(MP_QSTR_poll), MP_ROM_PTR(&usbdisp_poll_obj) },
    { MP_ROM_QSTR(MP_QSTR_ready), MP_ROM_PTR(&usbdisp_ready_obj) },
    { MP_ROM_QSTR(MP_QSTR_width), MP_ROM_PTR(&usbdisp_width_obj) },
    { MP_ROM_QSTR(MP_QSTR_height), MP_ROM_PTR(&usbdisp_height_obj) },
    { MP_ROM_QSTR(MP_QSTR_update_565), MP_ROM_PTR(&usbdisp_update_565_obj) },
    { MP_ROM_QSTR(MP_QSTR_fill), MP_ROM_PTR(&usbdisp_fill_obj) },
    { MP_ROM_QSTR(MP_QSTR_flush), MP_ROM_PTR(&usbdisp_flush_obj) },
    { MP_ROM_QSTR(MP_QSTR_force_reenum), MP_ROM_PTR(&usbdisp_force_reenum_obj) },
    { MP_ROM_QSTR(MP_QSTR_set_mode), MP_ROM_PTR(&usbdisp_set_mode_obj) },
    { MP_ROM_QSTR(MP_QSTR_chip_name), MP_ROM_PTR(&usbdisp_chip_name_obj) },
};

static MP_DEFINE_CONST_DICT(usbdisp_locals_dict, usbdisp_locals_table);

static MP_DEFINE_CONST_OBJ_TYPE(
    mp_type_usbdisp,
    MP_QSTR_USBDisp,
    MP_TYPE_FLAG_NONE,
    make_new, usbdisp_make_new,
    locals_dict, &usbdisp_locals_dict
);

static mp_obj_t mp_usb_disp_set_log(mp_obj_t on_in) {
    s_usb_disp_log_on = mp_obj_is_true(on_in);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(mp_usb_disp_set_log_obj, mp_usb_disp_set_log);

// bus_devices() - list of USB device addresses currently seen by the host
// stack. Hubs and the adapter show up here once enumerated, whether or not
// our display claimed them (a claimed adapter leaves the stack's idle
// list, so it is re-added here explicitly). Empty list = nothing sensed
// (cable/power/stack). Safe to call from any thread; never raises.
static mp_obj_t mp_usb_disp_bus_devices(void) {
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
static MP_DEFINE_CONST_FUN_OBJ_0(mp_usb_disp_bus_devices_obj, mp_usb_disp_bus_devices);

// force_reenum() - root-port power cycle: virtual replug of the whole USB
// subtree. Recovers wedged adapters and stack-disabled ports, and
// re-triggers enumeration (e.g. after the adapter finished booting).
static mp_obj_t usbdisp_force_reenum(mp_obj_t self_in) {
    mp_obj_usbdisp_t *self = usbdisp_get_self(self_in);
    usb_disp_force_reenum(self->disp);
    return mp_const_none;
}

// hub_ports() - [(hub_addr, port, connected, enabled, high_speed), ...]
// for every external-hub port on the bus. Read-only standard hub
// requests; safe to call any time. A port stuck at (connected=True,
// enabled=False) is one the IDF stack gave up on (single-shot
// enumeration of a still-booting device) - reset_port() it or wait
// for the watchdog. high_speed ports (hub-to-hub uplinks) are never
// auto-reset: resetting one drops the whole subtree and crashes the
// IDF enumerator (abort in enum.c control_request_string).
static mp_obj_t mp_usb_disp_hub_ports_fn(void) {
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
static MP_DEFINE_CONST_FUN_OBJ_0(mp_usb_disp_hub_ports_obj, mp_usb_disp_hub_ports_fn);

// reset_port(hub_addr, port, power_cycle=False, force=False) - re-enumerate
// one hub port without touching the rest of the chain. PORT_RESET
// (default) keeps VBUS up, so an already-booted device enumerates
// immediately; power_cycle=True drops VBUS for ~300ms first (stronger,
// but slow and may drop sibling ports on ganged-power hubs).
// High-speed ports (hub-to-hub uplinks) are refused unless force=True:
// resetting one drops the whole subtree and crashes the IDF enumerator.
// Manual recovery for a wedged port.
static mp_obj_t mp_usb_disp_reset_port_fn(size_t n_args, const mp_obj_t *args) {
    uint8_t hub_addr = (uint8_t)mp_obj_get_int(args[0]);
    uint8_t port = (uint8_t)mp_obj_get_int(args[1]);
    bool power_cycle = (n_args > 2) && mp_obj_is_true(args[2]);
    bool force = (n_args > 3) && mp_obj_is_true(args[3]);
    return mp_obj_new_bool(usb_disp_hal_reset_hub_port(hub_addr, port, power_cycle, force));
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(mp_usb_disp_reset_port_obj, 2, 4, mp_usb_disp_reset_port_fn);

// lsusb() - Linux-style USB listing ("Bus 001 Device 002: ID 17e9:028f
// DisplayLink ..."). Bus is always 001 (single OTG controller); no
// root-hub line. Read-only, safe any time.
static char s_lsusb_buf[2048];
static mp_obj_t mp_usb_disp_lsusb_fn(void) {
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
static MP_DEFINE_CONST_FUN_OBJ_0(mp_usb_disp_lsusb_obj, mp_usb_disp_lsusb_fn);

// set_watchdog(on) - enable/disable the hub-port watchdog (default on).
// The watchdog only acts while no display is attached; healthy ports
// are never touched.
static mp_obj_t mp_usb_disp_set_watchdog_fn(mp_obj_t on_in) {
    usb_disp_hal_set_watchdog(mp_obj_is_true(on_in));
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(mp_usb_disp_set_watchdog_obj, mp_usb_disp_set_watchdog_fn);

// set_auto_reset_idle([on]) - with no args, return the toggle state;
// with an arg, toggle automatic single PORT_RESET of idle ports that
// are not marked preexisting (default on). Marks are set for idle ports
// seen at boot, hub plug, and display-unplug snapshots, and cleared by
// any observed disconnect, so healthy uplinks are never selected while
// replugged adapters heal without hands. One shot per mark cycle.
static mp_obj_t mp_usb_disp_set_auto_reset_idle_fn(size_t n_args, const mp_obj_t *args) {
    if (n_args == 0) {
        return mp_obj_new_bool(usb_disp_hal_auto_reset_idle());
    }
    usb_disp_hal_set_auto_reset_idle(mp_obj_is_true(args[0]));
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(mp_usb_disp_set_auto_reset_idle_obj, 0, 1, mp_usb_disp_set_auto_reset_idle_fn);

// hid_start() - register the HID client (own task) on the shared host
// stack. False when the stack is not up yet (arm_usb_display runs first);
// idempotent, safe to retry from the 1s poll timer.
static mp_obj_t mp_usb_hid_start_fn(void) {
    return mp_obj_new_bool(usb_hid_start());
}
static MP_DEFINE_CONST_FUN_OBJ_0(mp_usb_hid_start_obj, mp_usb_hid_start_fn);

// hid_poll() - pump staged HID setups and claim health checks. True on
// device-set change (connect/disconnect), like USBDisp.poll().
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

// hid_state() - [(addr, kind, vid, pid), ...] for streaming HID devices.
// kind is "mouse" or "keyboard".
static mp_obj_t mp_usb_hid_state_fn(void) {
    usb_hid_state_t st[4];
    uint8_t n = usb_hid_state(st, 4);
    mp_obj_t list = mp_obj_new_list(0, NULL);
    for (uint8_t i = 0; i < n; i++) {
        mp_obj_t t[4];
        t[0] = mp_obj_new_int(st[i].addr);
        const char *kind = st[i].protocol == 2 ? "mouse" : "keyboard";
        t[1] = mp_obj_new_str(kind, strlen(kind));
        t[2] = mp_obj_new_int(st[i].vid);
        t[3] = mp_obj_new_int(st[i].pid);
        mp_obj_list_append(list, mp_obj_new_tuple(4, t));
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

static const mp_rom_map_elem_t usb_disp_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_usb_disp) },
    { MP_ROM_QSTR(MP_QSTR_USBDisp), MP_ROM_PTR(&mp_type_usbdisp) },
    { MP_ROM_QSTR(MP_QSTR_set_log), MP_ROM_PTR(&mp_usb_disp_set_log_obj) },
    { MP_ROM_QSTR(MP_QSTR_bus_devices), MP_ROM_PTR(&mp_usb_disp_bus_devices_obj) },
    { MP_ROM_QSTR(MP_QSTR_lsusb), MP_ROM_PTR(&mp_usb_disp_lsusb_obj) },
    { MP_ROM_QSTR(MP_QSTR_hub_ports), MP_ROM_PTR(&mp_usb_disp_hub_ports_obj) },
    { MP_ROM_QSTR(MP_QSTR_reset_port), MP_ROM_PTR(&mp_usb_disp_reset_port_obj) },
    { MP_ROM_QSTR(MP_QSTR_set_watchdog), MP_ROM_PTR(&mp_usb_disp_set_watchdog_obj) },
    { MP_ROM_QSTR(MP_QSTR_auto_reset_idle), MP_ROM_PTR(&mp_usb_disp_set_auto_reset_idle_obj) },
    { MP_ROM_QSTR(MP_QSTR_hid_start), MP_ROM_PTR(&mp_usb_hid_start_obj) },
    { MP_ROM_QSTR(MP_QSTR_hid_poll), MP_ROM_PTR(&mp_usb_hid_poll_obj) },
    { MP_ROM_QSTR(MP_QSTR_hid_drain), MP_ROM_PTR(&mp_usb_hid_drain_obj) },
    { MP_ROM_QSTR(MP_QSTR_hid_state), MP_ROM_PTR(&mp_usb_hid_state_obj) },
    { MP_ROM_QSTR(MP_QSTR_hid_claimed_addrs), MP_ROM_PTR(&mp_usb_hid_claimed_addrs_obj) },
};

static MP_DEFINE_CONST_DICT(usb_disp_module_globals, usb_disp_module_globals_table);

const mp_obj_module_t usb_disp_user_cmodule = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&usb_disp_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR_usb_disp, usb_disp_user_cmodule);
