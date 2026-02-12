#include "py/obj.h"
#include "py/runtime.h"
#include "py/mphal.h"
#include "esp_heap_caps.h"
#include "esp_codec_dev.h"  // Include for esp_codec_dev_*
#include "adc_mic.h"  // Include for audio_codec_adc_cfg_t, audio_codec_new_adc_data, etc.
#include <errno.h>   // For ENOMEM

#define ADC_MIC_DEBUG_PRINT(...) mp_printf(&mp_plat_print, __VA_ARGS__)

static mp_obj_t adc_mic_read(void) {
    ADC_MIC_DEBUG_PRINT("Starting adc_mic_read...\n");

    // Configure for mono ADC on GPIO1 (ADC1_CHANNEL_0) at 16kHz
    audio_codec_adc_cfg_t cfg = DEFAULT_AUDIO_CODEC_ADC_MONO_CFG(ADC_CHANNEL_0, 16000);
    ADC_MIC_DEBUG_PRINT("Config created for channel %d, sample rate %d\n", ADC_CHANNEL_0, 16000);

    ADC_MIC_DEBUG_PRINT("Creating ADC data interface...\n");
    const audio_codec_data_if_t *adc_if = audio_codec_new_adc_data(&cfg);
    if (adc_if == NULL) {
        ADC_MIC_DEBUG_PRINT("Failed to initialize ADC data interface\n");
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("Failed to initialize ADC data interface"));
    }
    ADC_MIC_DEBUG_PRINT("ADC data interface created successfully\n");

    // Create codec device for input
    esp_codec_dev_cfg_t codec_dev_cfg = {
        .dev_type = ESP_CODEC_DEV_TYPE_IN,
        .data_if = adc_if,
    };
    ADC_MIC_DEBUG_PRINT("Creating codec device...\n");
    esp_codec_dev_handle_t dev = esp_codec_dev_new(&codec_dev_cfg);
    if (dev == NULL) {
        ADC_MIC_DEBUG_PRINT("Failed to create codec device\n");
        audio_codec_delete_data_if(adc_if);
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("Failed to create codec device"));
    }
    ADC_MIC_DEBUG_PRINT("Codec device created successfully\n");

    // Set sample info: 16kHz, mono, 16-bit
    esp_codec_dev_sample_info_t fs = {
        .sample_rate = 16000,
        .channel = 1,
        .bits_per_sample = 16,
    };
    ADC_MIC_DEBUG_PRINT("Opening codec device with sample rate %d, channels %d, bits %d...\n", fs.sample_rate, fs.channel, fs.bits_per_sample);
    esp_err_t open_ret = esp_codec_dev_open(dev, &fs);
    if (open_ret != ESP_OK) {
        ADC_MIC_DEBUG_PRINT("Failed to open codec device: error %d\n", open_ret);
        esp_codec_dev_delete(dev);
        audio_codec_delete_data_if(adc_if);
        mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("Failed to open codec device: %d"), open_ret);
    }
    ADC_MIC_DEBUG_PRINT("Codec device opened successfully\n");

    // Allocate buffer for 16000 samples (16-bit, so 32000 bytes)
    const size_t buf_size = 16000 * sizeof(int16_t);
    ADC_MIC_DEBUG_PRINT("Allocating buffer of size %zu bytes...\n", buf_size);
    int16_t *audio_buffer = (int16_t *)heap_caps_malloc(buf_size, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
    if (audio_buffer == NULL) {
        ADC_MIC_DEBUG_PRINT("Failed to allocate buffer\n");
        esp_codec_dev_close(dev);
        esp_codec_dev_delete(dev);
        audio_codec_delete_data_if(adc_if);
        mp_raise_OSError(ENOMEM);
    }
    ADC_MIC_DEBUG_PRINT("Buffer allocated successfully\n");

    // Read the data (blocking until buffer is filled)
    ADC_MIC_DEBUG_PRINT("Starting esp_codec_dev_read for %zu bytes...\n", buf_size);
    int ret = esp_codec_dev_read(dev, audio_buffer, buf_size);
    ADC_MIC_DEBUG_PRINT("esp_codec_dev_read completed, returned %d\n", ret);
    if (ret < 0) {
        ADC_MIC_DEBUG_PRINT("Failed to read audio data: %d\n", ret);
        heap_caps_free(audio_buffer);
        esp_codec_dev_close(dev);
        esp_codec_dev_delete(dev);
        audio_codec_delete_data_if(adc_if);
        mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("Failed to read audio data: %d"), ret);
    }

    // Create MicroPython bytes object from the buffer
    ADC_MIC_DEBUG_PRINT("Creating bytes object from buffer...\n");
    mp_obj_t buf_obj = mp_obj_new_bytes((const byte *)audio_buffer, ret);

    // Cleanup
    ADC_MIC_DEBUG_PRINT("Cleaning up...\n");
    heap_caps_free(audio_buffer);
    esp_codec_dev_close(dev);
    esp_codec_dev_delete(dev);
    audio_codec_delete_data_if(adc_if);

    ADC_MIC_DEBUG_PRINT("adc_mic_read completed\n");
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