// hosted: access to the ESP-Hosted link on boards whose Wi-Fi/Bluetooth radio is a
// separate co-processor (ESP32-P4 + ESP32-C6). Compiled only where esp_hosted is
// enabled; elsewhere this file is empty.
//
//   hosted.host_version()         -> (major, minor, patch) of the esp_hosted host driver
//   hosted.coprocessor_version()  -> (major, minor, patch) reported by the co-processor
//   hosted.ota_begin(), hosted.ota_write(buf), hosted.ota_end(), hosted.ota_activate()
//                                 -> update the co-processor firmware over the link;
//                                    activate reboots the co-processor into it

#include "sdkconfig.h"

#if defined(CONFIG_ESP_HOSTED_ENABLED)

#include "py/obj.h"
#include "py/runtime.h"
#include "esp_err.h"
#include "esp_hosted.h"
#include "esp_hosted_ota.h"
#include "esp_hosted_api_types.h"
#include "esp_hosted_host_fw_ver.h"

static void hosted_check(esp_err_t err, const char *what) {
    if (err != ESP_OK) {
        mp_raise_msg_varg(&mp_type_OSError, MP_ERROR_TEXT("%s failed: %s (0x%x)"), what, esp_err_to_name(err), err);
    }
}

static mp_obj_t hosted_host_version(void) {
    mp_obj_t items[3] = {
        MP_OBJ_NEW_SMALL_INT(ESP_HOSTED_VERSION_MAJOR_1),
        MP_OBJ_NEW_SMALL_INT(ESP_HOSTED_VERSION_MINOR_1),
        MP_OBJ_NEW_SMALL_INT(ESP_HOSTED_VERSION_PATCH_1),
    };
    return mp_obj_new_tuple(3, items);
}
static MP_DEFINE_CONST_FUN_OBJ_0(hosted_host_version_obj, hosted_host_version);

static mp_obj_t hosted_coprocessor_version(void) {
    esp_hosted_coprocessor_fwver_t ver = { 0 };
    hosted_check(esp_hosted_get_coprocessor_fwversion(&ver), "esp_hosted_get_coprocessor_fwversion");
    mp_obj_t items[3] = {
        mp_obj_new_int_from_uint(ver.major1),
        mp_obj_new_int_from_uint(ver.minor1),
        mp_obj_new_int_from_uint(ver.patch1),
    };
    return mp_obj_new_tuple(3, items);
}
static MP_DEFINE_CONST_FUN_OBJ_0(hosted_coprocessor_version_obj, hosted_coprocessor_version);

static mp_obj_t hosted_ota_begin(void) {
    hosted_check(esp_hosted_slave_ota_begin(), "esp_hosted_slave_ota_begin");
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(hosted_ota_begin_obj, hosted_ota_begin);

static mp_obj_t hosted_ota_write(mp_obj_t buf_in) {
    mp_buffer_info_t buf;
    mp_get_buffer_raise(buf_in, &buf, MP_BUFFER_READ);
    hosted_check(esp_hosted_slave_ota_write((uint8_t *)buf.buf, (uint32_t)buf.len), "esp_hosted_slave_ota_write");
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(hosted_ota_write_obj, hosted_ota_write);

static mp_obj_t hosted_ota_end(void) {
    hosted_check(esp_hosted_slave_ota_end(), "esp_hosted_slave_ota_end");
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(hosted_ota_end_obj, hosted_ota_end);

static mp_obj_t hosted_ota_activate(void) {
    hosted_check(esp_hosted_slave_ota_activate(), "esp_hosted_slave_ota_activate");
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(hosted_ota_activate_obj, hosted_ota_activate);

static const mp_rom_map_elem_t hosted_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__),            MP_ROM_QSTR(MP_QSTR_hosted) },
    { MP_ROM_QSTR(MP_QSTR_host_version),        MP_ROM_PTR(&hosted_host_version_obj) },
    { MP_ROM_QSTR(MP_QSTR_coprocessor_version), MP_ROM_PTR(&hosted_coprocessor_version_obj) },
    { MP_ROM_QSTR(MP_QSTR_ota_begin),           MP_ROM_PTR(&hosted_ota_begin_obj) },
    { MP_ROM_QSTR(MP_QSTR_ota_write),           MP_ROM_PTR(&hosted_ota_write_obj) },
    { MP_ROM_QSTR(MP_QSTR_ota_end),             MP_ROM_PTR(&hosted_ota_end_obj) },
    { MP_ROM_QSTR(MP_QSTR_ota_activate),        MP_ROM_PTR(&hosted_ota_activate_obj) },
};
static MP_DEFINE_CONST_DICT(hosted_module_globals, hosted_module_globals_table);

const mp_obj_module_t hosted_user_cmodule = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&hosted_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR_hosted, hosted_user_cmodule);

#endif // CONFIG_ESP_HOSTED_ENABLED
