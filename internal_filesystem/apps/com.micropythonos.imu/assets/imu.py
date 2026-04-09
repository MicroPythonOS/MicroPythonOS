from mpos import Activity, SensorManager

class IMU(Activity):

    accel_sensor = None
    gyro_sensor = None
    temp_sensor = None
    refresh_timer = None

    # widgets:
    sliderx = None
    slidery = None
    sliderz = None
    slidergx = None
    slidergy = None
    slidergz = None

    def onCreate(self):
        screen = lv.obj()
        self.templabel = lv.label(screen)
        self.templabel.align(lv.ALIGN.TOP_MID, 0, 10)
        self.sliderx = lv.slider(screen)
        self.sliderx.align(lv.ALIGN.CENTER, 0, -60)
        self.slidery = lv.slider(screen)
        self.slidery.align(lv.ALIGN.CENTER, 0, -30)
        self.sliderz = lv.slider(screen)
        self.sliderz.align(lv.ALIGN.CENTER, 0, 0)
        self.slidergx = lv.slider(screen)
        self.slidergx.align(lv.ALIGN.CENTER, 0, 30)
        self.slidergy = lv.slider(screen)
        self.slidergy.align(lv.ALIGN.CENTER, 0, 60)
        self.slidergz = lv.slider(screen)
        self.slidergz.align(lv.ALIGN.CENTER, 0, 90)
        try:
            if SensorManager.is_available():
                self.accel_sensor = SensorManager.get_default_sensor(SensorManager.TYPE_ACCELEROMETER)
                self.gyro_sensor = SensorManager.get_default_sensor(SensorManager.TYPE_GYROSCOPE)
                # Get IMU temperature (not MCU temperature)
                self.temp_sensor = SensorManager.get_default_sensor(SensorManager.TYPE_IMU_TEMPERATURE)
                print("IMU sensors initialized via SensorManager")
                print(f"Available sensors: {SensorManager.get_sensor_list()}")
                if not self.accel_sensor and not self.gyro_sensor:
                    self.templabel.set_text("No IMU accel/gyro sensors available")
            else:
                print("Warning: No IMU sensors available")
                self.templabel.set_text("No IMU sensors available")
        except Exception as e:
            warning = f"Warning: could not initialize IMU hardware:\n{e}"
            print(warning)
            self.templabel.set_text(warning)
        self.setContentView(screen)

    def onStart(self, screen):
        print("starting imu refresh_timer")
        self.refresh_timer = lv.timer_create(self.refresh, 100, None)

    def onStop(self, screen):
        if self.refresh_timer:
            print("stopping imu refresh_timer")
            self.refresh_timer.delete()

    def convert_percentage(self, value: float) -> int:
        return round(50.0 + value)
        # non-linear mapping isn't really useful so unused:
        # Preserve sign and work with absolute value
        sign = 1 if value >= 0 else -1
        abs_value = abs(value)
        # Apply non-linear transformation (square root) to absolute value
        # Scale input range [0, 200] to [0, sqrt(200)] first
        sqrt_value = (abs_value ** 0.5)
        # Scale to output range [0, 100]
        # Map [0, sqrt(200)] to [50, 100] for positive, [0, 50] for negative
        max_sqrt = 200.0 ** 0.5  # Approx 14.142
        scaled = (sqrt_value / max_sqrt) * 50.0  # Scale to [0, 50]
        return int(50.0 + (sign * scaled))  # Shift to [0, 100]
    
    def refresh(self, timer):
        #print("refresh timer")
        axp = 50
        ayp = 50
        azp = 50
        gx = 50
        gy = 50
        gz = 50

        accel = SensorManager.read_sensor(self.accel_sensor) if self.accel_sensor else None
        gyro = SensorManager.read_sensor(self.gyro_sensor) if self.gyro_sensor else None
        temp = SensorManager.read_sensor(self.temp_sensor) if self.temp_sensor else None

        if accel:
            # Convert m/s² to G for display (divide by 9.80665)
            # Range: ±1G mapped to 0-100
            ax, ay, az = accel
            ax_g = ax / 9.80665
            ay_g = ay / 9.80665
            az_g = az / 9.80665
            axp = int((ax_g * 100 + 100) / 2)
            ayp = int((ay_g * 100 + 100) / 2)
            azp = int((az_g * 100 + 100) / 2)

        if gyro:
            # Gyro already in deg/s, map ±200 DPS to 0-100
            gx, gy, gz = gyro
            gx = self.convert_percentage(gx)
            gy = self.convert_percentage(gy)
            gz = self.convert_percentage(gz)

        if temp is not None:
            self.templabel.set_text(f"IMU chip temperature: {temp:.2f}°C")
        elif accel or gyro:
            self.templabel.set_text("IMU active (no temperature sensor)")
        else:
            self.templabel.set_text("IMU inactive")

        self.sliderx.set_value(axp, False)
        self.slidery.set_value(ayp, False)
        self.sliderz.set_value(azp, False)
        self.slidergx.set_value(gx, False)
        self.slidergy.set_value(gy, False)
        self.slidergz.set_value(gz, False)

