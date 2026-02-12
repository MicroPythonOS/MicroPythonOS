#include "py/obj.h"
#include "py/runtime.h"
#include "py/mphal.h"
#include "esp_heap_caps.h"
#include "esp_codec_dev.h"  // Include for esp_codec_dev_*
#include "adc_mic.h"  // Include for audio_codec_adc_cfg_t, audio_codec_new_adc_data, etc.
#include "sdkconfig.h" // for CONFIG_ADC_MIC_TASK_CORE
#include <errno.h>   // For ENOMEM
#include "esp_task_wdt.h"  // watchdog
#include "freertos/FreeRTOS.h"
#include "freertos/task.h" // to add a delay

#define ADC_MIC_DEBUG_PRINT(...) mp_printf(&mp_plat_print, __VA_ARGS__)

static mp_obj_t adc_mic_read(void) {
    ADC_MIC_DEBUG_PRINT("Starting adc_mic_read...\n");
    ADC_MIC_DEBUG_PRINT("CONFIG_ADC_MIC_TASK_CORE: %d\n", CONFIG_ADC_MIC_TASK_CORE);

    // Configuration (your current manual setup with 2.5 dB atten)
    audio_codec_adc_cfg_t cfg = {
        .handle = NULL,
        .max_store_buf_size = 1024 * 2,
        .conv_frame_size = 1024,
        .unit_id = ADC_UNIT_1,
        .adc_channel_list = ((uint8_t[]){ADC_CHANNEL_0}),
        .adc_channel_num = 1,
        .sample_rate_hz = 16000,
        //.atten = ADC_ATTEN_DB_2_5,
        .atten = ADC_ATTEN_DB_11,
    };
    ADC_MIC_DEBUG_PRINT("Config created for channel %d, sample rate %d, atten %d\n",
                        ADC_CHANNEL_0, 16000, cfg.atten);

    // ────────────────────────────────────────────────
    // Initialization (same as before)
    // ────────────────────────────────────────────────
    const audio_codec_data_if_t *adc_if = audio_codec_new_adc_data(&cfg);
    if (adc_if == NULL) {
        ADC_MIC_DEBUG_PRINT("Failed to initialize ADC data interface\n");
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("Failed to init ADC interface"));
    }

    esp_codec_dev_cfg_t codec_dev_cfg = {
        .dev_type = ESP_CODEC_DEV_TYPE_IN,
        .data_if = adc_if,
    };
    esp_codec_dev_handle_t dev = esp_codec_dev_new(&codec_dev_cfg);
    if (dev == NULL) {
        audio_codec_delete_data_if(adc_if);
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("Failed to create codec dev"));
    }

    esp_codec_dev_sample_info_t fs = {
        .sample_rate = 16000,
        .channel = 1,
        .bits_per_sample = 16,
    };
    esp_err_t open_ret = esp_codec_dev_open(dev, &fs);
    if (open_ret != ESP_OK) {
        esp_codec_dev_delete(dev);
        audio_codec_delete_data_if(adc_if);
        mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("esp_codec_dev_open failed: %d"), open_ret);
    }

    // ────────────────────────────────────────────────
    // Small reusable buffer + tracking variables
    // ────────────────────────────────────────────────
    const size_t chunk_samples = 512;
    const size_t buf_size = chunk_samples * sizeof(int16_t);
    //int16_t *audio_buffer = heap_caps_malloc(buf_size, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
    int16_t *audio_buffer = heap_caps_malloc_prefer(buf_size, MALLOC_CAP_DEFAULT | MALLOC_CAP_SPIRAM, MALLOC_CAP_DEFAULT);
    if (audio_buffer == NULL) {
        esp_codec_dev_close(dev);
        esp_codec_dev_delete(dev);
        audio_codec_delete_data_if(adc_if);
        mp_raise_OSError(ENOMEM);
    }

    // How many chunks to read (adjust as needed)
    const int N = 1;  // e.g. 50 × 512 = ~1.5 seconds @ 16 kHz

    int16_t global_min = 32767;
    int16_t global_max = -32768;

    ADC_MIC_DEBUG_PRINT("Reading %d chunks of %zu samples each (total %d samples)...\n",
                        N, chunk_samples, N * chunk_samples);

    mp_obj_t last_buf_obj = mp_const_none;

    for (int chunk = 0; chunk < N; chunk++) {
        esp_task_wdt_reset();  // "I'm alive"
        int ret = esp_codec_dev_read(dev, audio_buffer, buf_size);
        if (ret < 0) {
            ADC_MIC_DEBUG_PRINT("Read failed at chunk %d: %d\n", chunk, ret);
            break;
        }
        vTaskDelay(pdMS_TO_TICKS(1));  // 1 ms yield
        //if (ret != (int)buf_size) {
        //    ADC_MIC_DEBUG_PRINT("Partial read at chunk %d: got %d bytes (expected %zu)\n",
        //                        chunk, ret, buf_size);
        //}

        // Update global min/max
        for (size_t i = 0; i < chunk_samples; i++) {
            int16_t s = audio_buffer[i];
            if (s < global_min) global_min = s;
            if (s > global_max) global_max = s;
        }

        // Optional: print first few chunks for debug (comment out after testing)
        if (chunk < 3) {
            ADC_MIC_DEBUG_PRINT("Chunk %d first 16 samples:\n", chunk);
            for (size_t i = 0; i < 16; i++) {
                ADC_MIC_DEBUG_PRINT("%6d ", audio_buffer[i]);
                if ((i + 1) % 8 == 0) ADC_MIC_DEBUG_PRINT("\n");
            }
            ADC_MIC_DEBUG_PRINT("\n");
        }

        // Keep only the last chunk to return
        if (chunk == N - 1) {
            last_buf_obj = mp_obj_new_bytes((const byte *)audio_buffer, buf_size);
        }
    }

    // ────────────────────────────────────────────────
    // Report results
    // ────────────────────────────────────────────────
    ADC_MIC_DEBUG_PRINT("\nAfter %d chunks:\n", N);
    ADC_MIC_DEBUG_PRINT("Global min: %d\n", global_min);
    ADC_MIC_DEBUG_PRINT("Global max: %d\n", global_max);
    ADC_MIC_DEBUG_PRINT("Range:     %d\n", global_max - global_min);

    // Cleanup
    heap_caps_free(audio_buffer);
    esp_codec_dev_close(dev);
    esp_codec_dev_delete(dev);
    audio_codec_delete_data_if(adc_if);

    ADC_MIC_DEBUG_PRINT("adc_mic_read completed\n");

    return last_buf_obj ? last_buf_obj : mp_obj_new_bytes(NULL, 0);
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