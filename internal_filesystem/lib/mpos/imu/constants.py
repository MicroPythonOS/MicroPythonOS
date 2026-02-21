TYPE_ACCELEROMETER = 1      # Units: m/s² (meters per second squared)
TYPE_MAGNETIC_FIELD = 2      # Units: μT (micro teslas)
TYPE_GYROSCOPE = 4           # Units: deg/s (degrees per second)
TYPE_TEMPERATURE = 13        # Units: °C (generic, returns first available - deprecated)
TYPE_IMU_TEMPERATURE = 14    # Units: °C (IMU chip temperature)
TYPE_SOC_TEMPERATURE = 15    # Units: °C (MCU/SoC internal temperature)

# mounted_position:
FACING_EARTH = 20  # underside of PCB, like fri3d_2024
FACING_SKY = 21    # top of PCB, like waveshare_esp32_s3_lcd_touch_2 (default)

# Gravity constant for unit conversions
GRAVITY = 9.80665  # m/s²

IMU_CALIBRATION_FILENAME = "imu_calibration.json"
