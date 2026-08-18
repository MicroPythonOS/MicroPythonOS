import math
import time

from mpos.imu.constants import GRAVITY
from mpos.imu.drivers.base import IMUDriverBase

# Simulated motion: the device slowly rocks around X (roll) and Y (pitch),
# so accelerometer/gyroscope readings are smooth, plausible and consistent
# with each other (gyro is the analytic derivative of the tilt angles).
_ROLL_AMPLITUDE_RAD = math.radians(15.0)
_PITCH_AMPLITUDE_RAD = math.radians(10.0)
_ROLL_PERIOD_MS = 8000
_PITCH_PERIOD_MS = 13000

_TWO_PI = 2.0 * math.pi


class MockDriver(IMUDriverBase):
    """Simulated IMU for platforms without sensor hardware (web/desktop).

    motion=True: slow rocking motion so readings visibly change.
    motion=False: static, perfectly level device — accel (0, 0, GRAVITY),
    gyro zeros — for screenshots and deterministic tests. Toggle at runtime
    with set_motion().
    """

    def __init__(self, motion=True):
        super().__init__()
        self.motion = motion

    def set_motion(self, enabled):
        self.motion = enabled

    def _phases(self):
        if not self.motion:
            return 0.0, 0.0
        t = time.ticks_ms()
        roll_phase = _TWO_PI * (t % _ROLL_PERIOD_MS) / _ROLL_PERIOD_MS
        pitch_phase = _TWO_PI * (t % _PITCH_PERIOD_MS) / _PITCH_PERIOD_MS
        return roll_phase, pitch_phase

    def _raw_acceleration_mps2(self):
        roll_phase, pitch_phase = self._phases()
        roll = _ROLL_AMPLITUDE_RAD * math.sin(roll_phase)
        pitch = _PITCH_AMPLITUDE_RAD * math.sin(pitch_phase)

        ax = -GRAVITY * math.sin(pitch)
        ay = GRAVITY * math.sin(roll) * math.cos(pitch)
        az = GRAVITY * math.cos(roll) * math.cos(pitch)
        return (ax, ay, az)

    def _raw_gyroscope_dps(self):
        if not self.motion:
            return (0.0, 0.0, 0.0)
        roll_phase, pitch_phase = self._phases()
        roll_rate = _ROLL_AMPLITUDE_RAD * (_TWO_PI * 1000.0 / _ROLL_PERIOD_MS) * math.cos(roll_phase)
        pitch_rate = _PITCH_AMPLITUDE_RAD * (_TWO_PI * 1000.0 / _PITCH_PERIOD_MS) * math.cos(pitch_phase)

        gx = math.degrees(roll_rate)
        gy = math.degrees(pitch_rate)
        gz = 0.0
        return (gx, gy, gz)

    def read_acceleration(self):
        return self._raw_acceleration_mps2()

    def read_gyroscope(self):
        return self._raw_gyroscope_dps()

    def read_magnetometer(self):
        # Roughly Earth's field at mid latitudes (uT), fixed heading.
        return (20.0, 0.0, -45.0)

    def read_temperature(self):
        _, pitch_phase = self._phases()
        return 25.0 + 0.5 * math.sin(pitch_phase)

    # Simulated values are already "true": calibration is a no-op so that
    # calibrating while the mock is rocking cannot bake bogus offsets into
    # SharedPreferences (which real hardware would then load).

    def calibrate_accelerometer(self, samples):
        return (0.0, 0.0, 0.0)

    def calibrate_gyroscope(self, samples):
        return (0.0, 0.0, 0.0)

    def set_calibration(self, accel_offsets, gyro_offsets):
        pass
