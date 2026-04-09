#include "py/runtime.h"
#include "py/obj.h"
#include "py/binary.h"
#include "py/mphal.h"

#include "driver/i2s_pdm.h"
#include "driver/gpio.h"
#include "esp_err.h"
#include "esp_log.h"

#define TAG "pdm_mic"

typedef struct {
    mp_obj_base_t base;
    i2s_chan_handle_t rx_handle;
    uint32_t sample_rate;
    uint32_t buffer_size;   // in bytes
    bool running;
} pdm_mic_obj_t;

static const mp_obj_type_t pdm_mic_type;

// Initialize hardware (fixed for current ESP-IDF)
static esp_err_t pdm_mic_init_hw(pdm_mic_obj_t *self,
                                 gpio_num_t clk_pin, gpio_num_t data_pin,
                                 uint32_t sample_rate) {

    // Channel config
    i2s_chan_config_t chan_cfg = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_AUTO, I2S_ROLE_MASTER);

    ESP_ERROR_CHECK(i2s_new_channel(&chan_cfg, NULL, &self->rx_handle));

    // PDM RX config
    i2s_pdm_rx_config_t pdm_rx_cfg = {
        .clk_cfg = I2S_PDM_RX_CLK_DEFAULT_CONFIG(sample_rate),
        .slot_cfg = I2S_PDM_RX_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_MONO),
        .gpio_cfg = {
            .clk = clk_pin,
            .din = data_pin,
            .invert_flags = {
                .clk_inv = false,
            },
        },
    };

    ESP_ERROR_CHECK(i2s_channel_init_pdm_rx_mode(self->rx_handle, &pdm_rx_cfg));

    self->sample_rate = sample_rate;
    self->running = false;
    return ESP_OK;
}

// Constructor
static mp_obj_t pdm_mic_make_new(const mp_obj_type_t *type, size_t n_args, size_t n_kw, const mp_obj_t *all_args) {
    enum { ARG_clk, ARG_data, ARG_rate, ARG_bufsize };
    static const mp_arg_t allowed_args[] = {
        { MP_QSTR_clk,      MP_ARG_REQUIRED | MP_ARG_OBJ },
        { MP_QSTR_data,     MP_ARG_REQUIRED | MP_ARG_OBJ },
        { MP_QSTR_rate,     MP_ARG_INT, {.u_int = 16000} },
        { MP_QSTR_bufsize,  MP_ARG_INT, {.u_int = 4096} },
    };

    mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
    mp_arg_parse_all_kw_array(n_args, n_kw, all_args, MP_ARRAY_SIZE(allowed_args), allowed_args, args);

    pdm_mic_obj_t *self = mp_obj_malloc(pdm_mic_obj_t, &pdm_mic_type);

    gpio_num_t clk_pin  = (gpio_num_t)mp_hal_get_pin_obj(args[ARG_clk].u_obj);
    gpio_num_t data_pin = (gpio_num_t)mp_hal_get_pin_obj(args[ARG_data].u_obj);

    self->buffer_size = args[ARG_bufsize].u_int;

    esp_err_t ret = pdm_mic_init_hw(self, clk_pin, data_pin, args[ARG_rate].u_int);
    if (ret != ESP_OK) {
        mp_raise_msg_varg(&mp_type_OSError, MP_ERROR_TEXT("PDM init failed: %d"), ret);
    }

    return MP_OBJ_FROM_PTR(self);
}

// .start()
static mp_obj_t pdm_mic_start(mp_obj_t self_in) {
    pdm_mic_obj_t *self = MP_OBJ_TO_PTR(self_in);
    if (!self->running) {
        ESP_ERROR_CHECK(i2s_channel_enable(self->rx_handle));
        self->running = true;
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(pdm_mic_start_obj, pdm_mic_start);

// .stop()
static mp_obj_t pdm_mic_stop(mp_obj_t self_in) {
    pdm_mic_obj_t *self = MP_OBJ_TO_PTR(self_in);
    if (self->running) {
        ESP_ERROR_CHECK(i2s_channel_disable(self->rx_handle));
        self->running = false;
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(pdm_mic_stop_obj, pdm_mic_stop);

// .readinto(buffer) → returns bytes read
static mp_obj_t pdm_mic_readinto(mp_obj_t self_in, mp_obj_t buf_in) {
    pdm_mic_obj_t *self = MP_OBJ_TO_PTR(self_in);

    mp_buffer_info_t bufinfo;
    mp_get_buffer_raise(buf_in, &bufinfo, MP_BUFFER_WRITE);

    if (bufinfo.len < self->buffer_size) {
        mp_raise_ValueError(MP_ERROR_TEXT("buffer too small"));
    }

    size_t bytes_read = 0;
    esp_err_t ret = i2s_channel_read(self->rx_handle, bufinfo.buf, bufinfo.len, &bytes_read, pdMS_TO_TICKS(1000));

    if (ret != ESP_OK && ret != ESP_ERR_TIMEOUT) {
        mp_raise_msg_varg(&mp_type_OSError, MP_ERROR_TEXT("read failed: %d"), ret);
    }

    return MP_OBJ_NEW_SMALL_INT(bytes_read);
}
static MP_DEFINE_CONST_FUN_OBJ_2(pdm_mic_readinto_obj, pdm_mic_readinto);

// .deinit()
static mp_obj_t pdm_mic_deinit(mp_obj_t self_in) {
    pdm_mic_obj_t *self = MP_OBJ_TO_PTR(self_in);
    pdm_mic_stop(self_in);
    if (self->rx_handle) {
        i2s_del_channel(self->rx_handle);
        self->rx_handle = NULL;
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(pdm_mic_deinit_obj, pdm_mic_deinit);

static const mp_rom_map_elem_t pdm_mic_locals_dict_table[] = {
    { MP_ROM_QSTR(MP_QSTR_start),    MP_ROM_PTR(&pdm_mic_start_obj) },
    { MP_ROM_QSTR(MP_QSTR_stop),     MP_ROM_PTR(&pdm_mic_stop_obj) },
    { MP_ROM_QSTR(MP_QSTR_readinto), MP_ROM_PTR(&pdm_mic_readinto_obj) },
    { MP_ROM_QSTR(MP_QSTR_deinit),   MP_ROM_PTR(&pdm_mic_deinit_obj) },
    { MP_ROM_QSTR(MP_QSTR___del__),  MP_ROM_PTR(&pdm_mic_deinit_obj) },
};

static MP_DEFINE_CONST_DICT(pdm_mic_locals_dict, pdm_mic_locals_dict_table);

static MP_DEFINE_CONST_OBJ_TYPE(
    pdm_mic_type,
    MP_QSTR_PDM_Mic,
    MP_TYPE_FLAG_NONE,
    make_new, pdm_mic_make_new,
    locals_dict, &pdm_mic_locals_dict
);

// Module definition
static const mp_rom_map_elem_t pdm_mic_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_pdm_mic) },
    { MP_ROM_QSTR(MP_QSTR_PDM_Mic),  MP_ROM_PTR(&pdm_mic_type) },
};

static MP_DEFINE_CONST_DICT(pdm_mic_module_globals, pdm_mic_module_globals_table);

const mp_obj_module_t pdm_mic_module = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t*)&pdm_mic_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR_pdm_mic, pdm_mic_module);
