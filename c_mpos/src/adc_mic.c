#include "py/obj.h"
#include "py/runtime.h"
#include "py/mphal.h"
#include "esp_heap_caps.h"
#include "esp_codec_dev.h"
#include "adc_mic.h"  // Include for audio_codec_adc_cfg_t, audio_codec_new_adc_data, etc.

static mp_obj_t adc_mic_read(void) {
    // Configure for mono ADC on GPIO1 (ADC1_CHANNEL_0) at 16kHz
    audio_codec_adc_cfg_t cfg = DEFAULT_AUDIO_CODEC_ADC_MONO_CFG(ADC_CHANNEL_0, 16000);
    const audio_codec_data_if_t *adc_if = audio_codec_new_adc_data(&cfg);
    if (adc_if == NULL) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("Failed to initialize ADC data interface"));
    }

    // Create codec device for input
    esp_codec_dev_cfg_t codec_dev_cfg = {
        .dev_type = ESP_CODEC_DEV_TYPE_IN,
        .data_if = adc_if,
    };
    esp_codec_dev_handle_t dev = esp_codec_dev_new(&codec_dev_cfg);
    if (dev == NULL) {
        audio_codec_delete_adc_data(adc_if);
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("Failed to create codec device"));
    }

    // Set sample info: 16kHz, mono, 16-bit
    esp_codec_dev_sample_info_t fs = {
        .sample_rate = 16000,
        .channel = 1,
        .bits_per_sample = 16,
    };
    if (esp_codec_dev_open(dev, &fs) != ESP_OK) {
        esp_codec_dev_del(dev);
        audio_codec_delete_adc_data(adc_if);
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("Failed to open codec device"));
    }

    // Allocate buffer for 16000 samples (16-bit, so 32000 bytes)
    const size_t buf_size = 16000 * sizeof(uint16_t);
    uint8_t *audio_buffer = (uint8_t *)heap_caps_malloc(buf_size, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
    if (audio_buffer == NULL) {
        esp_codec_dev_close(dev);
        esp_codec_dev_del(dev);
        audio_codec_delete_adc_data(adc_if);
        mp_raise_OSError(MP_ENOMEM);
    }

    // Read the data (blocking until buffer is filled)
    int ret = esp_codec_dev_read(dev, audio_buffer, buf_size);
    if (ret < 0) {
        heap_caps_free(audio_buffer);
        esp_codec_dev_close(dev);
        esp_codec_dev_del(dev);
        audio_codec_delete_adc_data(adc_if);
        mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("Failed to read audio data: %d"), ret);
    }

    // Create MicroPython bytes object from the buffer
    mp_obj_t buf_obj = mp_obj_new_bytes(audio_buffer, ret);

    // Cleanup
    heap_caps_free(audio_buffer);
    esp_codec_dev_close(dev);
    esp_codec_dev_del(dev);
    audio_codec_delete_adc_data(adc_if);

    return buf_obj;
}
MP_DEFINE_CONST_FUN_OBJ_0(adc_mic_read_obj, adc_mic_read);

static const mp_rom_map_elem_t adc_mic_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_adc_mic) },
    { MP_ROM_QSTR(MP_QSTR_read), MP_ROM_PTR(&adc_mic_read_obj) },
};
static MP_DEFINE_CONST_DICT(adc_mic_module_globals, adc_mic_module_globals_table);

const mp_obj_module_t adc_mic_user_cmodule = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&adc_mic_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR_adc_mic, adc_mic_user_cmodule);
