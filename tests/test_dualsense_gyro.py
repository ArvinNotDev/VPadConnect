import configparser
import math
import os
import struct
from types import SimpleNamespace
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication

from core.dualsense_gyro import (
    ACCEL_COUNTS_PER_G,
    GYRO_COUNTS_PER_DEGREE_PER_SECOND,
    DualSenseFactoryCalibration,
    DualSenseGyroSteering,
    DualSenseMotion,
    decode_dualsense_motion,
)
from core.mapper import Mapper
from core.settings import SettingsManager
from ui.pages.controllers import ControllersPage


def _report(report_id=0x01, angle_degrees=0.0, gyro_y_dps=0.0, timestamp=0):
    report = bytearray(64 if report_id == 0x01 else 78)
    report[0] = report_id
    gyro_offset = 16 if report_id == 0x01 else 17
    accel_offset = gyro_offset + 6
    timestamp_offset = accel_offset + 6
    gyro = (0, round(gyro_y_dps * GYRO_COUNTS_PER_DEGREE_PER_SECOND), 0)
    angle = math.radians(angle_degrees)
    accel = (
        round(-math.sin(angle) * ACCEL_COUNTS_PER_G),
        0,
        round(math.cos(angle) * ACCEL_COUNTS_PER_G),
    )
    struct.pack_into("<hhh", report, gyro_offset, *gyro)
    struct.pack_into("<hhh", report, accel_offset, *accel)
    struct.pack_into("<I", report, timestamp_offset, timestamp & 0xFFFFFFFF)
    return bytes(report)


def _factory_calibration():
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


class DualSenseMotionTests(unittest.TestCase):
    def test_decodes_usb_and_bluetooth_motion_and_clock(self):
        for report_id, timestamp in ((0x01, 123456), (0x31, 0xFFFFFF00)):
            report = _report(report_id, angle_degrees=12, gyro_y_dps=-4, timestamp=timestamp)
            motion = decode_dualsense_motion(report)
            self.assertIsNotNone(motion)
            self.assertEqual(motion.sensor_timestamp, timestamp)
            self.assertEqual(motion.accel[0], round(-math.sin(math.radians(12)) * 8192))
            self.assertAlmostEqual(motion.gyro[1] / GYRO_COUNTS_PER_DEGREE_PER_SECOND, -4)

    def test_rejects_wrong_or_truncated_reports(self):
        self.assertIsNone(decode_dualsense_motion(b""))
        self.assertIsNone(decode_dualsense_motion(bytes([0x02]) + bytes(64)))
        self.assertIsNone(decode_dualsense_motion(bytes([0x01]) + bytes(24)))

    def test_factory_feature_report_calibrates_gyro_and_accelerometer_units(self):
        calibration = DualSenseFactoryCalibration.from_feature_report(_factory_calibration())
        self.assertIsNotNone(calibration)
        self.assertAlmostEqual(calibration.gyro_dps_per_count[0], 1 / 1024)
        self.assertAlmostEqual(calibration.accel_g_per_count[0], 1 / 8192)
        self.assertIsNone(DualSenseFactoryCalibration.from_feature_report(bytes(41)))

    def test_factory_gyro_bias_is_removed_before_rate_conversion(self):
        report = bytearray(_factory_calibration())
        struct.pack_into("<h", report, 1, 100)
        calibration = DualSenseFactoryCalibration.from_feature_report(report)
        self.assertAlmostEqual(
            calibration.gyro_rate_radians_per_second((100, 0, 0))[0], 0.0
        )

    def test_accelerometer_gravity_defines_physical_lateral_axis(self):
        filter_ = DualSenseGyroSteering(
            enabled=True, center_gravity=(0, 0, 1), factory_calibration=_factory_calibration()
        )
        value = filter_.update(DualSenseMotion((0, -15 * 1024, 0), (0, 0, 8192), 0), now=1.0)
        self.assertEqual(value, 0)

        # A yaw-like rate around the gravity axis has no steering projection.
        for tick in range(1, 20):
            value = filter_.update(
                DualSenseMotion((0, 0, 90 * 1024), (0, 0, 8192), tick * 30_000),
                now=1.0 + tick / 100.0,
            )
        self.assertEqual(value, 0)

    def test_integrates_tilt_and_accelerometer_corrects_angle(self):
        filter_ = DualSenseGyroSteering(
            enabled=True, center_gravity=(0, 0, 1), deadzone_degrees=0,
            factory_calibration=_factory_calibration(),
        )
        for tick in range(1, 101):
            angle = 15.0 * tick / 100.0
            filter_.update(
                decode_dualsense_motion(
                    _report(angle_degrees=angle, gyro_y_dps=-15, timestamp=tick * 30_000)
                ),
                now=10.0 + tick / 100.0,
            )
        self.assertAlmostEqual(filter_.current_angle_degrees, 15.0, delta=1.0)
        self.assertGreater(filter_.steering_value, 0)

    def test_center_calibration_recenters_and_deadzone_suppresses_small_tilt(self):
        filter_ = DualSenseGyroSteering(
            enabled=True, center_gravity=(0, 0, 1), deadzone_degrees=2,
            factory_calibration=_factory_calibration(),
        )
        motion = decode_dualsense_motion(_report(angle_degrees=1, timestamp=30_000))
        filter_.update(motion, now=1.0)
        self.assertEqual(filter_.steering_value, 0)

        motion = decode_dualsense_motion(_report(angle_degrees=12, timestamp=60_000))
        filter_.update(motion, now=1.01)
        self.assertIsNotNone(filter_.calibrate_center())
        self.assertEqual(filter_.steering_value, 0)

    def test_sensitivity_and_deadzone_change_output(self):
        low = DualSenseGyroSteering(
            enabled=True, center_gravity=(0, 0, 1), sensitivity=0.5, deadzone_degrees=0,
            factory_calibration=_factory_calibration(),
        )
        high = DualSenseGyroSteering(
            enabled=True, center_gravity=(0, 0, 1), sensitivity=2.0, deadzone_degrees=0,
            factory_calibration=_factory_calibration(),
        )
        motion = decode_dualsense_motion(_report(angle_degrees=10, timestamp=30_000))
        low.update(motion, now=1.0)
        high.update(motion, now=1.0)
        self.assertGreater(high.steering_value, low.steering_value)

    def test_reset_clears_tilt_on_disconnect(self):
        filter_ = DualSenseGyroSteering(
            enabled=True, center_gravity=(0, 0, 1), deadzone_degrees=0,
            factory_calibration=_factory_calibration(),
        )
        filter_.update(decode_dualsense_motion(_report(angle_degrees=20)), now=1.0)
        self.assertGreater(filter_.steering_value, 0)
        filter_.reset()
        self.assertEqual(filter_.steering_value, 0)

    def test_mapper_stop_resets_gyro_and_shuts_down_virtual_output(self):
        filter_ = DualSenseGyroSteering(
            enabled=True, center_gravity=(0, 0, 1), deadzone_degrees=0,
            factory_calibration=_factory_calibration(),
        )
        filter_.update(decode_dualsense_motion(_report(angle_degrees=20)), now=1.0)
        self.assertGreater(filter_.steering_value, 0)

        class Motion:
            def reset(self):
                pass

        class Emulator:
            stopped = False

            def shutdown(self):
                self.stopped = True

        mapper = object.__new__(Mapper)
        mapper.gyro_steering = filter_
        mapper._connected = True
        mapper._mouse_motion = Motion()
        mapper.controllers_page = SimpleNamespace(clear_battery=lambda _path: None)
        mapper.controller = SimpleNamespace(device_path="test-path", name="Test DualSense")
        mapper.emulator = Emulator()
        mapper.stop()

        self.assertEqual(filter_.steering_value, 0)
        self.assertTrue(mapper.emulator.stopped)

    def test_disabled_gyro_preserves_analog_x_exactly(self):
        mapper = object.__new__(Mapper)
        mapper.gyro_steering = None
        self.assertEqual(mapper._steering_x_input(12345, b""), 12345)

        mapper.gyro_steering = DualSenseGyroSteering(enabled=False)
        self.assertEqual(mapper._steering_x_input(-5432, _report(angle_degrees=25)), -5432)

    def test_enabled_gyro_replaces_only_horizontal_steering_value(self):
        mapper = object.__new__(Mapper)
        mapper.gyro_steering = DualSenseGyroSteering(
            enabled=True, center_gravity=(0, 0, 1), deadzone_degrees=0,
            factory_calibration=_factory_calibration(),
        )
        value = mapper._steering_x_input(20000, _report(angle_degrees=10))
        self.assertGreater(value, 0)
        self.assertNotEqual(value, 20000)


class PerControllerGyroSettingsTests(unittest.TestCase):
    def test_settings_are_independent_by_stable_controller_id(self):
        settings = object.__new__(SettingsManager)
        settings.config = configparser.ConfigParser()
        settings.set_controller_gyro_settings("controller-a", {
            "enabled": True,
            "sensitivity": 1.75,
            "deadzone_degrees": 3.5,
            "center_gravity": (0.1, 0.2, 0.97),
        })
        settings.set_controller_gyro_settings("controller-b", {
            "enabled": False,
            "sensitivity": 0.75,
            "deadzone_degrees": 1.0,
            "center_gravity": None,
        })

        a = settings.get_controller_gyro_settings("controller-a")
        b = settings.get_controller_gyro_settings("controller-b")
        self.assertTrue(a["enabled"])
        self.assertAlmostEqual(a["sensitivity"], 1.75)
        self.assertEqual(a["center_gravity"], (0.1, 0.2, 0.97))
        self.assertFalse(b["enabled"])
        self.assertAlmostEqual(b["sensitivity"], 0.75)
        self.assertIsNone(b["center_gravity"])

    def test_shortcut_toggles_only_the_selected_controller(self):
        app = QApplication.instance() or QApplication([])
        page = ControllersPage(settings=None, vigem_available=False)

        class Card:
            def __init__(self):
                self._gyro = DualSenseGyroSteering(enabled=False)
                self.controller_name = "Selected DualSense"

            def toggle_gyro(self):
                self._gyro.set_enabled(not self._gyro.enabled)

        first, second = Card(), Card()
        page._cards = {"first": first, "second": second}
        page.gyro_target_combo.addItem("First DualSense", "first")
        page.gyro_target_combo.addItem("Second DualSense", "second")
        page.gyro_target_combo.setCurrentIndex(1)

        self.assertTrue(page.toggle_selected_gyro())
        self.assertFalse(first._gyro.enabled)
        self.assertTrue(second._gyro.enabled)
        self.assertTrue(page.toggle_selected_gyro())
        self.assertFalse(second._gyro.enabled)

        page.refresh_timer.stop()
        page.close()
        app.processEvents()


if __name__ == "__main__":
    unittest.main()
