from mpos.apps import Activity

class IMU(Activity):

    sensor = None
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
            from machine import Pin, I2C
            from qmi8658 import QMI8658
            import machine
            self.sensor = QMI8658(I2C(0, sda=machine.Pin(48), scl=machine.Pin(47)))
            print("IMU sensor initialized")
            #print(f"{self.sensor.temperature=} {self.sensor.acceleration=} {self.sensor.gyro=}")
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
        if self.sensor:
            #print(f"{self.sensor.temperature=} {self.sensor.acceleration=} {self.sensor.gyro=}")
            temp = self.sensor.temperature
            ax = self.sensor.acceleration[0]
            axp = int((ax * 100 + 100)/2)
            ay = self.sensor.acceleration[1]
            ayp = int((ay * 100 + 100)/2)
            az = self.sensor.acceleration[2]
            azp = int((az * 100 + 100)/2)
            # values between -200 and 200 => /4 becomes -50 and 50 => +50 becomes 0 and 100
            gx = self.convert_percentage(self.sensor.gyro[0])
            gy = self.convert_percentage(self.sensor.gyro[1])
            gz = self.convert_percentage(self.sensor.gyro[2])
            self.templabel.set_text(f"IMU chip temperature: {temp:.2f}°C")
        else:
            #temp = 12.34
            import random
            randomnr = random.randint(0,100)
            axp = randomnr
            ayp = 50
            azp = 75
            gx = 45
            gy = 50
            gz = 55
        self.sliderx.set_value(axp, False)
        self.slidery.set_value(ayp, False)
        self.sliderz.set_value(azp, False)
        self.slidergx.set_value(gx, False)
        self.slidergy.set_value(gy, False)
        self.slidergz.set_value(gz, False)

