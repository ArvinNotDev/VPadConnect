import math
import struct
import unittest

from core.dualsense_gyro import DualSenseGyroSteering, DualSenseMotion


def _factory_calibration() -> bytes:
    report = bytearray(41)
    report[0] = 0x05
    for offset in (1, 3, 5):
        struct.pack_into("<h", report, offset, 0)
    for plus, minus in ((7, 9), (11, 13), (15, 17)):
        struct.pack_into("<h", report, plus, 1024)
        struct.pack_into("<h", report, minus, -1024)
    struct.pack_into("<HH", report, 19, 1, 1)
    for plus, minus in ((23, 25), (27, 29), (31, 33)):
        struct.pack_into("<h", report, plus, 8192)
        struct.pack_into("<h", report, minus, -8192)
    return bytes(report)


class DualSenseGyroRealtimeTests(unittest.TestCase):
    def make_filter(self) -> DualSenseGyroSteering:
        return DualSenseGyroSteering(
            enabled=True,
            center_gravity=(0.0, 0.0, 1.0),
            deadzone_degrees=0.0,
            factory_calibration=_factory_calibration(),
        )

    def test_sensor_rate_uses_hardware_timestamp_and_wraps(self):
        gyro = self.make_filter()
        start = 0xFFFF0000

        for index in range(40):
            timestamp = (start + index * 12_000) & 0xFFFFFFFF
            gyro.update(
                DualSenseMotion((0, 0, 0), (0, 0, 8192), timestamp),
                now=10.0 + index * 0.004,
            )

        self.assertIsNotNone(gyro.sample_rate_hz)
        self.assertAlmostEqual(gyro.sample_rate_hz, 250.0, delta=0.5)

    def test_gravity_correction_converges_quickly_without_extra_smoothing(self):
        gyro = self.make_filter()
        gyro.update(
            DualSenseMotion((0, 0, 0), (0, 0, 8192), 1_000),
            now=1.0,
        )

        angle = math.radians(10.0)
        tilted_gravity = (
            round(-math.sin(angle) * 8192),
            0,
            round(math.cos(angle) * 8192),
        )
        for index in range(1, 11):
            gyro.update(
                DualSenseMotion((0, 0, 0), tilted_gravity, 1_000 + index * 12_000),
                now=1.0 + index * 0.004,
            )

        # A 25 ms complementary time constant should follow a 10-degree
        # gravity reference quickly while the gyroscope remains immediate.
        self.assertGreater(gyro.current_angle_degrees, 7.5)
        self.assertLess(gyro.current_angle_degrees, 10.5)


if __name__ == "__main__":
    unittest.main()
