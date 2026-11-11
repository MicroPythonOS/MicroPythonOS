// SPDX-License-Identifier: MIT
//
// buzzer - PCM audio playback on a passive piezo buzzer (ESP32 family).
//
// A piezo disc is not a speaker: it has no coil and no cone, it bends when a
// voltage is applied. Its deflection follows the *average* pin voltage, so it
// can reproduce an arbitrary waveform if the pin is switched fast enough that
// the disc only sees the average. That is exactly what a PWM (LEDC) channel
// does: the carrier runs at the sample rate (at least 16 kHz, so it is not
// audible on its own) and its duty cycle sets the average level.
//
// The audio sample rate is therefore the rate at which the duty cycle has to be
// rewritten. Doing that from Python is far too slow and too jittery (GC, the
// GIL, the 2 ms LVGL timer all live there), so this module keeps a ring buffer
// of int16 samples in internal RAM and a hardware timer interrupt pops one
// sample per period and writes it straight into the LEDC duty register. The
// design follows the two implementations known to work on this exact hardware:
// retro-go's drivers/audio/buzzer.c (fri3d 2024/2026 badges) and Espressif's
// esp-iot-solution pwm_audio component.
//
// Resources taken:
//   - LEDC timer 3, channel 7, low speed mode. MicroPython's machine.PWM keeps
//     its own bookkeeping and allocates from channel/timer 0 upwards, so the
//     highest indices are the ones it reaches last.
//   - Timer group 0, timer 1 (that is machine.Timer(1)). machine.Timer(0) is
//     the LVGL task handler and machine.Timer(3) is the WAVStream warm-output
//     timer, both of which must keep working; timer 1 is the one nobody uses.
//     The legacy timer driver is used on purpose: the new gptimer driver picks
//     a group by itself and resets its registers when it takes it over, which
//     would silently kill the task handler timer in group 0.
//   - One CPU interrupt vector, held from reserve() (called at boot, when the
//     board registers its buzzer output) until the chip resets. By the time an
//     app plays a file, the rest of the firmware has taken every free
//     low/medium vector and esp_intr_alloc() returns ESP_ERR_NOT_FOUND.
//
// If the timer ISR finds the ring buffer empty for a full second it pauses
// itself. That keeps a soft reset (which abandons the Python writer but does
// not run any deinit) from leaving a 78 kHz interrupt running forever; the
// next write() restarts the timer.

#include <string.h>

#include "py/obj.h"
#include "py/runtime.h"
#include "py/mpthread.h"
#include "py/mphal.h"

#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"

#include "driver/ledc.h"
#include "driver/gpio.h"
#include "esp_clk_tree.h"
#include "driver/timer.h"
#include "esp_intr_alloc.h"
#include "soc/timer_periph.h"

#include "esp_heap_caps.h"
#include "soc/ledc_struct.h"
#include "soc/ledc_periph.h"
#include "soc/soc_caps.h"
#include "hal/timer_ll.h"

#define BUZZER_LEDC_SPEED       LEDC_LOW_SPEED_MODE
#define BUZZER_LEDC_TIMER       LEDC_TIMER_3
#define BUZZER_LEDC_CHANNEL     LEDC_CHANNEL_7

#define BUZZER_TIMER_GROUP      TIMER_GROUP_0
#define BUZZER_TIMER_INDEX      TIMER_1
// The timer counter runs at 80 MHz / 2 = 40 MHz. The divider cannot be 1, and
// a high tick rate keeps the sampling period accurate (44100 Hz becomes 44101
// Hz instead of 44642 Hz at the 5 MHz used by esp-iot-solution).
#define BUZZER_TIMER_SRC_HZ     80000000
#define BUZZER_TIMER_DIVIDER    2
#define BUZZER_TIMER_TICK_HZ    (BUZZER_TIMER_SRC_HZ / BUZZER_TIMER_DIVIDER)

// Samples per call to write() are copied in chunks of at most this many to keep
// a single GIL section short even when the caller hands over a huge buffer.
#define BUZZER_WRITE_CHUNK      512

// Pause the ISR after this many consecutive samples with an empty buffer
// (~1 s at 22 kHz). This is the soft-reset safety net described above.
#define BUZZER_IDLE_PAUSE_SAMPLES 32768

#define BUZZER_DEFAULT_RATE     22050
#define BUZZER_DEFAULT_BITS     10
#define BUZZER_DEFAULT_BUFSIZE  4096
// machine.Timer(1) is the one nobody else uses: Timer(0) is the LVGL task
// handler and WAVStream's warm-output timer takes 3 on ESP32.
#define BUZZER_DEFAULT_TIMER    1

typedef struct {
    bool initialized;
    bool active;                // the caller wants the timer to run
    volatile bool isr_paused;   // the ISR paused itself after an idle period
    bool writer_waiting;        // a write() is sleeping on the semaphore
    volatile bool stop_flag;

    int gpio;
    ledc_timer_bit_t bits;
    int shift;                  // 16 - bits, how far to drop the sample
    uint32_t rate;
    uint32_t src_hz;            // LEDC clock source frequency
    uint32_t carrier_hz;        // PWM carrier frequency

    timer_group_t tg;           // timer group, 0 or 1
    timer_idx_t ti;             // timer inside the group, 0 or 1
    uint8_t timer_id;           // machine.Timer number
    bool shared_intr;           // allocated with ESP_INTR_FLAG_SHARED
    bool hw_acquired;           // timer configured and interrupt held
    intr_handle_t intr;         // timer interrupt handle

    uint16_t *buf;              // mono int16 samples, internal RAM
    uint32_t size;              // power of two
    uint32_t mask;
    volatile uint32_t head;
    volatile uint32_t tail;

    volatile uint32_t underruns;
    uint32_t idle_samples;
    volatile int writers;       // threads currently inside write()
    SemaphoreHandle_t sem;
} buzzer_state_t;

static buzzer_state_t buzzer;

// Direct LEDC register write, as in esp-iot-solution's pwm_audio: the duty
// register holds four fractional bits, and setting sig_out_en + the update bit
// in conf0 latches the new value, duty_start (conf1 bit 31) pushes it out at
// the next PWM period. This has to be a raw write: ledc_set_duty() takes a
// non-ISR spinlock, so it cannot be used from the sample clock.
static inline void IRAM_ATTR buzzer_ledc_set_duty(uint32_t duty) {
#if defined(CONFIG_IDF_TARGET_ESP32P4) || defined(CONFIG_IDF_TARGET_ESP32C5) || defined(CONFIG_IDF_TARGET_ESP32C61)
    volatile ledc_chn_reg_t *ch = &LEDC.channel_group[BUZZER_LEDC_SPEED].channel[BUZZER_LEDC_CHANNEL];
    ch->duty_init.val = duty << 4;
#else
    LEDC.channel_group[BUZZER_LEDC_SPEED].channel[BUZZER_LEDC_CHANNEL].duty.val = duty << 4;
#endif
    // sig_out_en (bit 2) + the "update" bit (bit 4, called low_speed_update on
    // Xtensa, para_up on P4) enable the output and latch a new duty cycle.
    LEDC.channel_group[BUZZER_LEDC_SPEED].channel[BUZZER_LEDC_CHANNEL].conf0.val |= 0x00000014;
    LEDC.channel_group[BUZZER_LEDC_SPEED].channel[BUZZER_LEDC_CHANNEL].conf1.val |= 0x80000000;
}

// The interrupt is allocated with plain esp_intr_alloc() instead of
// timer_isr_callback_add(), because the legacy driver's status-register
// variant cannot be shared with anything and fails with ESP_ERR_NOT_FOUND once
// the low/medium vectors are in use. The price is that the peripheral's alarm
// bit has to be acknowledged here.
static void IRAM_ATTR buzzer_timer_isr(void *arg) {
    timer_ll_clear_intr_status(TIMER_LL_GET_HW(buzzer.tg), TIMER_LL_EVENT_ALARM(buzzer.ti));
    // The alarm enable bit is cleared when the alarm fires; without this the
    // sample clock would tick exactly once.
    timer_ll_enable_alarm(TIMER_LL_GET_HW(buzzer.tg), buzzer.ti, true);

    uint32_t tail = buzzer.tail;
    int32_t sample;

    if (tail != buzzer.head) {
        sample = (int16_t)buzzer.buf[tail];
        tail = (tail + 1) & buzzer.mask;
        buzzer.tail = tail;
        buzzer.idle_samples = 0;
    } else {
        // Silence is a 50% duty cycle: no voltage across the disc.
        sample = 0;
        buzzer.underruns++;
        if (++buzzer.idle_samples > BUZZER_IDLE_PAUSE_SAMPLES) {
            buzzer.idle_samples = 0;
            buzzer.isr_paused = true;
            timer_ll_enable_counter(TIMER_LL_GET_HW(buzzer.tg), buzzer.ti, false);
        }
    }

    buzzer_ledc_set_duty((uint32_t)(sample + 32768) >> buzzer.shift);

    BaseType_t woken = pdFALSE;
    if (buzzer.writer_waiting) {
        uint32_t used = (buzzer.head - tail) & buzzer.mask;
        if (buzzer.size - 1 - used >= buzzer.size / 2) {
            buzzer.writer_waiting = false;
            xSemaphoreGiveFromISR(buzzer.sem, &woken);
        }
    }
    // No portYIELD_FROM_ISR() here: its trace hook is not defined in this
    // build. The woken writer only has to run before the ring runs dry, which
    // is ~90 ms away, so waiting for the next scheduler tick is fine.
    (void)woken;
}

static void buzzer_timer_start(void) {
    timer_set_counter_value(buzzer.tg, buzzer.ti, 0);
    timer_start(buzzer.tg, buzzer.ti);
}

static void buzzer_timer_pause(void) {
    timer_pause(buzzer.tg, buzzer.ti);
}

static void buzzer_set_duty_raw(uint32_t duty) {
    ledc_set_duty(BUZZER_LEDC_SPEED, BUZZER_LEDC_CHANNEL, duty);
    ledc_update_duty(BUZZER_LEDC_SPEED, BUZZER_LEDC_CHANNEL);
}

// Give the ring buffer, the semaphore and the pin back, but keep the timer and
// its interrupt: they are the scarce resources (the low/medium CPU interrupt
// vectors run out once the rest of the firmware is up) and reusing them makes
// the next clip unable to fail.
static void buzzer_teardown(void) {
    bool was_initialized = buzzer.initialized;
    buzzer.active = false;
    buzzer.stop_flag = true;
    buzzer.initialized = false;
    if (buzzer.hw_acquired) {
        buzzer_timer_pause();
    }
    if (was_initialized) {
        ledc_stop(BUZZER_LEDC_SPEED, BUZZER_LEDC_CHANNEL, 0);
        gpio_set_direction(buzzer.gpio, GPIO_MODE_INPUT);
    }

    // Let a writer that is blocked inside write() notice stop_flag and leave
    // before the semaphore and the ring go away. The GIL must be released
    // while waiting or that thread could never finish its call.
    if (buzzer.sem) {
        buzzer.writer_waiting = false;
        xSemaphoreGive(buzzer.sem);
        for (int i = 0; i < 250 && buzzer.writers > 0; i++) {
            MP_THREAD_GIL_EXIT();
            mp_hal_delay_ms(1);
            MP_THREAD_GIL_ENTER();
        }
        vSemaphoreDelete(buzzer.sem);
        buzzer.sem = NULL;
    }
    if (buzzer.buf) {
        heap_caps_free(buzzer.buf);
        buzzer.buf = NULL;
    }
    buzzer.isr_paused = false;
}

static void buzzer_hw_release(void) {
    if (!buzzer.hw_acquired) {
        return;
    }
    buzzer_timer_pause();
    timer_disable_intr(buzzer.tg, buzzer.ti);
    if (buzzer.intr) {
        esp_intr_free(buzzer.intr);
        buzzer.intr = NULL;
    }
    timer_deinit(buzzer.tg, buzzer.ti);
    buzzer.hw_acquired = false;
}

static esp_err_t buzzer_hw_acquire(int timer_id) {
    if (buzzer.hw_acquired && buzzer.timer_id == (uint8_t)timer_id) {
        return ESP_OK;
    }
    buzzer_hw_release();

    // Use the same numbering as machine.Timer: 0/1 are in group 0, 2/3 in
    // group 1 when a group holds two timers.
    #if SOC_TIMER_GROUP_TIMERS_PER_GROUP == 1
    buzzer.tg = (timer_group_t)(timer_id & 1);
    buzzer.ti = TIMER_0;
    #else
    buzzer.tg = (timer_group_t)((timer_id >> 1) & 1);
    buzzer.ti = (timer_idx_t)(timer_id & 1);
    #endif
    buzzer.timer_id = (uint8_t)timer_id;

    timer_config_t timer_conf = {
        .divider = BUZZER_TIMER_DIVIDER,
        .counter_dir = TIMER_COUNT_UP,
        .counter_en = TIMER_PAUSE,
        .alarm_en = TIMER_ALARM_EN,
        .auto_reload = TIMER_AUTORELOAD_EN,
    };
    esp_err_t err = timer_init(buzzer.tg, buzzer.ti, &timer_conf);
    if (err != ESP_OK) {
        return err;
    }
    buzzer.hw_acquired = true;

    int irq_source = timer_group_periph_signals.groups[buzzer.tg].timer_irq_id[buzzer.ti];
    buzzer.shared_intr = false;
    err = esp_intr_alloc(irq_source, 0, buzzer_timer_isr, NULL, &buzzer.intr);
    if (err != ESP_OK) {
        // Every low/medium vector can already be taken by the time an app
        // plays audio. A status-bit handler is exactly what a shared vector is
        // for, so try that before giving up.
        err = esp_intr_alloc(irq_source, ESP_INTR_FLAG_SHARED,
                             buzzer_timer_isr, NULL, &buzzer.intr);
        buzzer.shared_intr = (err == ESP_OK);
    }
    if (err != ESP_OK) {
        buzzer_hw_release();
        return err;
    }
    timer_disable_intr(buzzer.tg, buzzer.ti);
    timer_set_counter_value(buzzer.tg, buzzer.ti, 0);
    timer_enable_intr(buzzer.tg, buzzer.ti);
    return ESP_OK;
}

static void buzzer_configure_rate(uint32_t rate) {
    uint64_t alarm = BUZZER_TIMER_TICK_HZ / rate;
    if (alarm < 2) {
        alarm = 2;
    }
    timer_set_alarm_value(buzzer.tg, buzzer.ti, alarm);
    buzzer.rate = rate;
}

static void buzzer_init_raise(int gpio, uint32_t rate, int bits, uint32_t bufsize, int timer_id) {
    if (gpio < 0) {
        mp_raise_ValueError(MP_ERROR_TEXT("pin must be a GPIO number"));
    }
    if (rate < 2000 || rate > 96000) {
        mp_raise_ValueError(MP_ERROR_TEXT("sample rate must be 2000..96000 Hz"));
    }
    if (bits < 8 || bits > 13) {
        mp_raise_ValueError(MP_ERROR_TEXT("duty resolution must be 8..13 bits"));
    }
    if (bufsize < 256 || bufsize > 32768 || (bufsize & (bufsize - 1)) != 0) {
        mp_raise_ValueError(MP_ERROR_TEXT("buffer size must be a power of two, 256..32768"));
    }
    if (timer_id < 0 || timer_id >= SOC_TIMER_GROUP_TOTAL_TIMERS) {
        mp_raise_ValueError(MP_ERROR_TEXT("timer must be a machine.Timer number"));
    }

    buzzer_teardown();

    esp_err_t err = buzzer_hw_acquire(timer_id);
    if (err != ESP_OK) {
        buzzer_teardown();
        mp_raise_msg_varg(&mp_type_RuntimeError,
                          MP_ERROR_TEXT("esp_intr_alloc: %d (timer %d)"), err, timer_id);
    }

    // The carrier has to be fast enough to stand in for the sample clock;
    // when the target's LEDC clock is slow (ESP32-P4 runs it from XTAL), drop
    // duty resolution instead of under-sampling the audio.
    #if SOC_LEDC_SUPPORT_APB_CLOCK
    ledc_clk_cfg_t clk_cfg = LEDC_USE_APB_CLK;
    #elif SOC_LEDC_SUPPORT_PLL_DIV_CLOCK
    ledc_clk_cfg_t clk_cfg = LEDC_USE_PLL_DIV_CLK;
    #elif SOC_LEDC_SUPPORT_XTAL_CLOCK
    ledc_clk_cfg_t clk_cfg = LEDC_USE_XTAL_CLK;
    #else
    ledc_clk_cfg_t clk_cfg = LEDC_AUTO_CLK;
    #endif
    uint32_t src_hz = 0;
    esp_clk_tree_src_get_freq_hz((soc_module_clk_t)clk_cfg,
                                 ESP_CLK_TREE_SRC_FREQ_PRECISION_APPROX, &src_hz);
    // Carrier frequency: at least 16 kHz so it is inaudible, and otherwise
    // equal to the sample rate. Going higher (78 kHz with a 10-bit duty) looks
    // better on paper but the buzzer's drive circuit cannot follow it, and the
    // audio came out silent on the fri3d 2026. retro-go uses the same rule.
    uint32_t carrier = rate < 16000 ? 16000 : rate;
    int duty_bits = bits;
    while (duty_bits > 8 && (uint64_t)carrier * (1u << duty_bits) > src_hz) {
        duty_bits--;
    }

    buzzer.src_hz = src_hz;
    buzzer.carrier_hz = carrier;
    buzzer.gpio = gpio;
    buzzer.bits = (ledc_timer_bit_t)duty_bits;
    buzzer.shift = 16 - duty_bits;
    buzzer.size = bufsize;
    buzzer.mask = bufsize - 1;
    buzzer.head = 0;
    buzzer.tail = 0;
    buzzer.underruns = 0;
    buzzer.idle_samples = 0;
    buzzer.isr_paused = false;
    buzzer.stop_flag = false;
    buzzer.writer_waiting = false;

    buzzer.buf = (uint16_t *)heap_caps_malloc(bufsize * sizeof(uint16_t),
                                              MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
    if (buzzer.buf == NULL) {
        mp_raise_msg(&mp_type_MemoryError, MP_ERROR_TEXT("buzzer buffer allocation failed"));
    }
    memset(buzzer.buf, 0, bufsize * sizeof(uint16_t));

    buzzer.sem = xSemaphoreCreateBinary();
    if (buzzer.sem == NULL) {
        heap_caps_free(buzzer.buf);
        buzzer.buf = NULL;
        mp_raise_msg(&mp_type_MemoryError, MP_ERROR_TEXT("buzzer semaphore allocation failed"));
    }

    // Highest carrier that still fits the chosen resolution.
    ledc_timer_config_t timer_conf = {
        .speed_mode = BUZZER_LEDC_SPEED,
        .duty_resolution = buzzer.bits,
        .timer_num = BUZZER_LEDC_TIMER,
        .freq_hz = carrier,
        .clk_cfg = clk_cfg,
    };
    err = ledc_timer_config(&timer_conf);
    if (err != ESP_OK) {
        buzzer_teardown();
        mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("ledc_timer_config: %d"), err);
    }

    // The pad output driver is not enabled by ledc_channel_config(): it only
    // connects the LEDC signal through the GPIO matrix. Boards that played an
    // RTTTL jingle before (or a previous clip's deinit) leave the pin as an
    // input, and then the PWM never reaches the buzzer.
    gpio_set_direction(gpio, GPIO_MODE_OUTPUT);

    ledc_channel_config_t chan_conf = {
        .gpio_num = gpio,
        .speed_mode = BUZZER_LEDC_SPEED,
        .channel = BUZZER_LEDC_CHANNEL,
        .intr_type = LEDC_INTR_DISABLE,
        .timer_sel = BUZZER_LEDC_TIMER,
        .duty = 0,
        .hpoint = 0,
    };
    err = ledc_channel_config(&chan_conf);
    if (err != ESP_OK) {
        buzzer_teardown();
        mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("ledc_channel_config: %d"), err);
    }

    buzzer_configure_rate(rate);

    buzzer.initialized = true;
    buzzer.active = true;
    buzzer_timer_start();
}

static mp_obj_t buzzer_init(size_t n_args, const mp_obj_t *pos_args, mp_map_t *kw_args) {
    enum { ARG_pin, ARG_rate, ARG_bits, ARG_bufsize, ARG_timer };
    static const mp_arg_t allowed_args[] = {
        { MP_QSTR_pin, MP_ARG_REQUIRED | MP_ARG_INT, {.u_int = -1} },
        { MP_QSTR_rate, MP_ARG_INT, {.u_int = BUZZER_DEFAULT_RATE} },
        { MP_QSTR_bits, MP_ARG_INT, {.u_int = BUZZER_DEFAULT_BITS} },
        { MP_QSTR_bufsize, MP_ARG_INT, {.u_int = BUZZER_DEFAULT_BUFSIZE} },
        { MP_QSTR_timer, MP_ARG_INT, {.u_int = BUZZER_DEFAULT_TIMER} },
    };
    mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
    mp_arg_parse_all(n_args, pos_args, kw_args, MP_ARRAY_SIZE(allowed_args), allowed_args, args);

    buzzer_init_raise(args[ARG_pin].u_int,
                      (uint32_t)args[ARG_rate].u_int,
                      args[ARG_bits].u_int,
                      (uint32_t)args[ARG_bufsize].u_int,
                      args[ARG_timer].u_int);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_KW(buzzer_init_obj, 0, buzzer_init);

// Reserve the timer and its interrupt now instead of when the first clip
// starts. Called at boot (the board registers a buzzer output there) because
// by the time an app plays something, other drivers may have taken every free
// low/medium interrupt vector.
static mp_obj_t buzzer_reserve(size_t n_args, const mp_obj_t *pos_args, mp_map_t *kw_args) {
    enum { ARG_timer };
    static const mp_arg_t allowed_args[] = {
        { MP_QSTR_timer, MP_ARG_INT, {.u_int = BUZZER_DEFAULT_TIMER} },
    };
    mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
    mp_arg_parse_all(n_args, pos_args, kw_args, MP_ARRAY_SIZE(allowed_args), allowed_args, args);

    int timer_id = args[ARG_timer].u_int;
    if (timer_id < 0 || timer_id >= SOC_TIMER_GROUP_TOTAL_TIMERS) {
        mp_raise_ValueError(MP_ERROR_TEXT("timer must be a machine.Timer number"));
    }
    esp_err_t err = buzzer_hw_acquire(timer_id);
    if (err != ESP_OK) {
        mp_raise_msg_varg(&mp_type_RuntimeError,
                          MP_ERROR_TEXT("esp_intr_alloc: %d (timer %d)"), err, timer_id);
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_KW(buzzer_reserve_obj, 0, buzzer_reserve);

static mp_obj_t buzzer_deinit(void) {
    buzzer_teardown();
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(buzzer_deinit_obj, buzzer_deinit);

static mp_obj_t buzzer_active(void) {
    return mp_obj_new_bool(buzzer.initialized && buzzer.active && !buzzer.isr_paused);
}
static MP_DEFINE_CONST_FUN_OBJ_0(buzzer_active_obj, buzzer_active);

static mp_obj_t buzzer_deinit_require(void) {
    if (!buzzer.initialized) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("buzzer not initialized"));
    }
    return mp_const_none;
}

static mp_obj_t buzzer_set_rate(mp_obj_t rate_in) {
    buzzer_deinit_require();
    uint32_t rate = (uint32_t)mp_obj_get_int(rate_in);
    if (rate < 2000 || rate > 96000) {
        mp_raise_ValueError(MP_ERROR_TEXT("sample rate must be 2000..96000 Hz"));
    }
    bool was_running = buzzer.active;
    buzzer_timer_pause();
    buzzer_configure_rate(rate);
    if (was_running) {
        buzzer.isr_paused = false;
        buzzer_timer_start();
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(buzzer_set_rate_obj, buzzer_set_rate);

static size_t buzzer_ring_free(void) {
    // One slot is always kept empty: with a power-of-two mask a completely
    // full ring is indistinguishable from an empty one.
    uint32_t used = (buzzer.head - buzzer.tail) & buzzer.mask;
    return buzzer.size - 1 - used;
}

// Copy up to `samples` samples into the ring, downmixing and attenuating.
static size_t buzzer_ring_push(const uint8_t *src, size_t samples, int channels, int shift) {
    size_t free_samples = buzzer_ring_free();
    if (samples > free_samples) {
        samples = free_samples;
    }
    if (samples == 0) {
        return 0;
    }
    bool was_empty = (buzzer.head == buzzer.tail);
    uint32_t head = buzzer.head;
    uint32_t mask = buzzer.mask;
    const int16_t *in = (const int16_t *)src;
    uint16_t *out = buzzer.buf;

    if (channels == 2) {
        for (size_t i = 0; i < samples; i++) {
            int32_t mixed = ((int32_t)in[i * 2] + (int32_t)in[i * 2 + 1]) >> 1;
            if (shift > 0) {
                mixed >>= shift;
            }
            out[head] = (uint16_t)(int16_t)mixed;
            head = (head + 1) & mask;
        }
    } else {
        for (size_t i = 0; i < samples; i++) {
            int32_t value = in[i];
            if (shift > 0) {
                value >>= shift;
            }
            out[head] = (uint16_t)(int16_t)value;
            head = (head + 1) & mask;
        }
    }

    portMEMORY_BARRIER();
    buzzer.head = head;
    if (was_empty) {
        // A new clip starts: forget the underruns counted while idle.
        buzzer.underruns = 0;
    }

    if (buzzer.isr_paused) {
        // The ISR paused itself after an idle period (or a soft reset left it
        // running with nobody feeding it): resume on the next buffer.
        buzzer.isr_paused = false;
        buzzer_timer_start();
    }
    return samples;
}

static mp_obj_t buzzer_write(size_t n_args, const mp_obj_t *pos_args, mp_map_t *kw_args) {
    enum { ARG_buf, ARG_channels, ARG_shift };
    static const mp_arg_t allowed_args[] = {
        { MP_QSTR_buf, MP_ARG_REQUIRED | MP_ARG_OBJ, {.u_rom_obj = MP_ROM_NONE} },
        { MP_QSTR_channels, MP_ARG_INT, {.u_int = 1} },
        { MP_QSTR_shift, MP_ARG_INT, {.u_int = 0} },
    };
    mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
    mp_arg_parse_all(n_args, pos_args, kw_args, MP_ARRAY_SIZE(allowed_args), allowed_args, args);

    int channels = args[ARG_channels].u_int;
    int shift = args[ARG_shift].u_int;
    if (channels != 1 && channels != 2) {
        mp_raise_ValueError(MP_ERROR_TEXT("channels must be 1 or 2"));
    }
    if (shift < 0 || shift > 16) {
        mp_raise_ValueError(MP_ERROR_TEXT("shift must be 0..16"));
    }

    buzzer.writers++;
    if (!buzzer.initialized || buzzer.buf == NULL || buzzer.sem == NULL) {
        buzzer.writers--;
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("buzzer not initialized"));
    }

    // Anything that touches the same pin (a machine.PWM ringtone, a
    // notification sound, AudioManager's Pin(pin, IN) after an RTTTL clip)
    // reroutes the GPIO matrix and disables the pad driver, which leaves the
    // LEDC running but silent. Put the signal back before feeding samples.
    esp_rom_gpio_connect_out_signal(buzzer.gpio,
                                    ledc_periph_signal[BUZZER_LEDC_SPEED].sig_out0_idx + BUZZER_LEDC_CHANNEL,
                                    false, false);
    gpio_set_direction(buzzer.gpio, GPIO_MODE_OUTPUT);

    mp_buffer_info_t bufinfo;
    mp_get_buffer_raise(args[ARG_buf].u_obj, &bufinfo, MP_BUFFER_READ);

    size_t frame_bytes = 2 * channels;
    size_t total_frames = bufinfo.len / frame_bytes;
    size_t done_frames = 0;
    const uint8_t *src = (const uint8_t *)bufinfo.buf;

    while (done_frames < total_frames) {
        if (buzzer.stop_flag || !buzzer.active) {
            // Discard whatever is left instead of reporting a short write:
            // callers treat a short write as "retry", which would spin
            // forever on a stopped output.
            buzzer.writers--;
            return mp_obj_new_int_from_uint(bufinfo.len);
        }
        size_t chunk = total_frames - done_frames;
        if (chunk > BUZZER_WRITE_CHUNK) {
            chunk = BUZZER_WRITE_CHUNK;
        }
        size_t pushed = buzzer_ring_push(src + done_frames * frame_bytes, chunk, channels, shift);
        done_frames += pushed;
        if (done_frames >= total_frames) {
            break;
        }
        if (pushed == 0) {
            // Ring full: sleep until the ISR has drained half of it. The GIL
            // has to be released or the UI thread would be blocked with us.
            buzzer.writer_waiting = true;
            MP_THREAD_GIL_EXIT();
            xSemaphoreTake(buzzer.sem, pdMS_TO_TICKS(100));
            MP_THREAD_GIL_ENTER();
            buzzer.writer_waiting = false;
        }
    }

    buzzer.writers--;
    return mp_obj_new_int_from_uint(done_frames * frame_bytes);
}
static MP_DEFINE_CONST_FUN_OBJ_KW(buzzer_write_obj, 1, buzzer_write);

static mp_obj_t buzzer_stop(void) {
    if (!buzzer.initialized) {
        return mp_const_none;
    }
    buzzer.stop_flag = true;
    buzzer.active = false;
    buzzer_timer_pause();
    buzzer.head = 0;
    buzzer.tail = 0;
    buzzer.isr_paused = false;
    buzzer.underruns = 0;
    buzzer_set_duty_raw(0);
    if (buzzer.sem) {
        xSemaphoreGive(buzzer.sem);
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(buzzer_stop_obj, buzzer_stop);

static mp_obj_t buzzer_start(void) {
    buzzer_deinit_require();
    buzzer.stop_flag = false;
    buzzer.active = true;
    buzzer.isr_paused = false;
    buzzer_timer_start();
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(buzzer_start_obj, buzzer_start);

// Right-shift 16-bit samples in place, the same attenuation machine.I2S.shift()
// applies for the I2S path. Kept in C because the WAV loop calls it for every
// chunk and a Python loop over thousands of samples is too expensive.
static mp_obj_t buzzer_attenuate(size_t n_args, const mp_obj_t *pos_args, mp_map_t *kw_args) {
    enum { ARG_buf, ARG_shift };
    static const mp_arg_t allowed_args[] = {
        { MP_QSTR_buf, MP_ARG_REQUIRED | MP_ARG_OBJ, {.u_rom_obj = MP_ROM_NONE} },
        { MP_QSTR_shift, MP_ARG_INT, {.u_int = 0} },
    };
    mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
    mp_arg_parse_all(n_args, pos_args, kw_args, MP_ARRAY_SIZE(allowed_args), allowed_args, args);

    int shift = args[ARG_shift].u_int;
    if (shift <= 0) {
        return mp_const_none;
    }
    mp_buffer_info_t bufinfo;
    mp_get_buffer_raise(args[ARG_buf].u_obj, &bufinfo, MP_BUFFER_WRITE);

    int16_t *samples = (int16_t *)bufinfo.buf;
    size_t count = bufinfo.len / sizeof(int16_t);
    // MicroPython buffers are 2-byte aligned for bytearray, so this is safe to
    // walk as int16 on all supported targets.
    for (size_t i = 0; i < count; i++) {
        samples[i] >>= shift;
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_KW(buzzer_attenuate_obj, 1, buzzer_attenuate);

static mp_obj_t buzzer_stats(void) {
    if (!buzzer.initialized) {
        return mp_obj_new_tuple(3, (mp_obj_t[]){mp_obj_new_int(0), mp_obj_new_int(0), mp_obj_new_int(0)});
    }
    uint32_t used = (buzzer.head - buzzer.tail) & buzzer.mask;
    mp_obj_t items[3] = {
        mp_obj_new_int_from_uint(buzzer.underruns),
        mp_obj_new_int_from_uint(used),
        mp_obj_new_int_from_uint(buzzer.rate),
    };
    return mp_obj_new_tuple(3, items);
}
static MP_DEFINE_CONST_FUN_OBJ_0(buzzer_stats_obj, buzzer_stats);

// (machine.Timer number, rate, duty bits, interrupt held, LEDC clock, carrier)
static mp_obj_t buzzer_info(void) {
    mp_obj_t items[6] = {
        mp_obj_new_int(buzzer.timer_id),
        mp_obj_new_int_from_uint(buzzer.rate),
        mp_obj_new_int(buzzer.bits),
        mp_obj_new_bool(buzzer.intr != NULL),
        mp_obj_new_int_from_uint(buzzer.src_hz),
        mp_obj_new_int_from_uint(buzzer.carrier_hz),
    };
    return mp_obj_new_tuple(6, items);
}
static MP_DEFINE_CONST_FUN_OBJ_0(buzzer_info_obj, buzzer_info);

static const mp_rom_map_elem_t buzzer_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_buzzer) },
    { MP_ROM_QSTR(MP_QSTR_init), MP_ROM_PTR(&buzzer_init_obj) },
    { MP_ROM_QSTR(MP_QSTR_reserve), MP_ROM_PTR(&buzzer_reserve_obj) },
    { MP_ROM_QSTR(MP_QSTR_deinit), MP_ROM_PTR(&buzzer_deinit_obj) },
    { MP_ROM_QSTR(MP_QSTR_start), MP_ROM_PTR(&buzzer_start_obj) },
    { MP_ROM_QSTR(MP_QSTR_stop), MP_ROM_PTR(&buzzer_stop_obj) },
    { MP_ROM_QSTR(MP_QSTR_active), MP_ROM_PTR(&buzzer_active_obj) },
    { MP_ROM_QSTR(MP_QSTR_set_rate), MP_ROM_PTR(&buzzer_set_rate_obj) },
    { MP_ROM_QSTR(MP_QSTR_write), MP_ROM_PTR(&buzzer_write_obj) },
    { MP_ROM_QSTR(MP_QSTR_attenuate), MP_ROM_PTR(&buzzer_attenuate_obj) },
    { MP_ROM_QSTR(MP_QSTR_stats), MP_ROM_PTR(&buzzer_stats_obj) },
    { MP_ROM_QSTR(MP_QSTR_info), MP_ROM_PTR(&buzzer_info_obj) },
};
static MP_DEFINE_CONST_DICT(buzzer_module_globals, buzzer_module_globals_table);

const mp_obj_module_t buzzer_user_cmodule = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&buzzer_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR_buzzer, buzzer_user_cmodule);
