# D-Shell ESP32-S3 N16R8

This board profile targets the D-Shell with 16 MB Flash, 8 MB octal PSRAM, a 240 × 320 ST7789V SPI display and GT911 touch.

## Building

Initialize the repository's pinned submodules and activate the matching ESP-IDF environment, then run from the repository root:

```sh
bash scripts/d_shell/build.sh
```

The wrapper uses the normal `esp32s3` build target (`ESP32_GENERIC_S3`, `SPIRAM_OCT`, 16 MB Flash). It generates a startup file in `tmp/d_shell_boot/` and selects it with `MPOS_BOOT_DIR`. Startup sets the hardware ID before importing `mpos.main`, while preserving an existing explicit hardware ID. The standard startup source remains unchanged.

The ordinary `bash scripts/build_mpos.sh esp32s3` command retains automatic detection. The D-Shell probe requires both the GT911 product ID and QMI8658 identity, and releases the probed pins afterwards. The dedicated startup profile avoids probing unrelated boards' pin assignments.

Follow the normal ESP32 installation procedure with the resulting image. Flash offsets depend on whether the file is a merged image or an application image and on the installed partition table.

## Hardware

| Function | Configuration |
| --- | --- |
| Display | ST7789V, 240 × 320, RGB565/BGR with byte swapping; two internal DMA buffers of 38,400 bytes each |
| SPI | Host 1 at 40 MHz; SCK 39, MOSI 38, CS 48, DC 45, reset 40, backlight 47 |
| Touch | GT911 on I2C 0, SCL 41, SDA 42; reset 1, interrupt 2; reset selects address `0x5D` |
| Keys | GPIO 9 and 3, active low with pull-ups; PREV and NEXT, both held gives ENTER; 20 ms debounce |
| LEDs | Eight WS2812 LEDs on GPIO 46, registered with LightsManager |
| IMU | QMI8658 on I2C 1, SCL 7, SDA 6, address `0x6A`, registered with SensorManager |
| Speaker | MAX98357A, I2S SCK 17, WS 18, SD 16; amplifier enable 15, gain 8; AudioManager |
| Buzzer | GPIO 5, AudioManager |
| Sensor bus | SoftI2C, SCL 21 and SDA 14; AHT20 `0x38`, VEML7700 `0x10`, DS1307 `0x68`, exposed for board diagnostics |

The ST7789V driver files are copied unchanged from [lvgl-micropython PR #585](https://github.com/lvgl-micropython/lvgl_micropython/pull/585), final source revision `f4d28e366ffbf88a4046d357a0842f17541ce149`. The package entry point follows the existing display-driver registration pattern. This avoids changing the pinned LVGL/MicroPython submodule just to add the missing driver. Generic ST7789 initialization enables inversion and produced incorrect primary colors on the tested panel; this ST7789V initialization produced the expected red, green and blue.

## Validation

```sh
make lint
make syntax-tests
python3 tests/cpython_d_shell_detection.py
python3 tests/cpython_d_shell_bootstrap.py
python3 tests/cpython_st7789v_pr.py
python3 tests/cpython_d_shell_hardware_guard.py
```

On a D-Shell running this profile, with both keys released, no audio playing, the board stationary and the RTC oscillator running:

```sh
MPOS_TEST_PORT=/dev/ttyACM0 python3 scripts/d_shell/run_hardware_tests.py
```

Use the actual serial port. This helper uses one persistent asyncio REPL session and waits for startup before issuing commands. It checks display settings, GT911 identity, idle keys, QMI8658 acceleration, AHT20 measurement, VEML7700 raw counts, RTC advancement and registered LED/audio outputs. It changes the VEML7700 measurement configuration; it does not set the RTC or perform audio playback. Sensor accuracy and lux conversion are not calibrated by these tests.

`tests/test_graphical_d_shell_hardware.py` also works with the normal test runner. On other boards and the desktop, it skips without importing the D-Shell hardware initializer.

The board contribution contains hardware support and its build/test integration. Diagnostic applications, firmware binaries and changes to shared settings/navigation behavior are maintained separately.
