import math
import struct

from core.dualsense_gyro import (
    DUALSHOCK4_SENSOR_TICKS_PER_SECOND,
    DualShock4FactoryCalibration,
    DualShock4GyroSteering,
    decode_dualshock4_motion,
)


def _feature(report_id):
    report = bytearray(37 if report_id == 0x02 else 41)
    report[0] = report_id
    for offset, value in zip((1, 3, 5), (100, -40, 25)):
        struct.pack_into("<h", report, offset, value)
    plus, minus = (1124, 984, 1049), (-924, -1064, -999)
    if report_id == 0x02:
        pairs = ((7, 9), (11, 13), (15, 17))
        for (po, mo), p, n in zip(pairs, plus, minus):
            struct.pack_into("<h", report, po, p)
            struct.pack_into("<h", report, mo, n)
    else:
        for off, val in zip((7, 9, 11), plus):
            struct.pack_into("<h", report, off, val)
        for off, val in zip((13, 15, 17), minus):
            struct.pack_into("<h", report, off, val)
    struct.pack_into("<hh", report, 19, 1, 1)
    for po, mo in ((23, 25), (27, 29), (31, 33)):
        struct.pack_into("<h", report, po, 8192)
        struct.pack_into("<h", report, mo, -8192)
    return bytes(report)


def _input(report_id, angle=0.0, gyro_y_dps=-4.0, timestamp=0):
    report = bytearray(64 if report_id == 0x01 else 78)
    report[0] = report_id
    shift = 0 if report_id == 0x01 else 2
    gyro_offset = 13 + shift
    timestamp_offset = 10 + shift
    accel_offset = gyro_offset + 6
    a = math.radians(angle)
    struct.pack_into("<H", report, timestamp_offset, timestamp & 0xFFFF)
    struct.pack_into("<hhh", report, gyro_offset, 0, round(gyro_y_dps * 1024), 0)
    struct.pack_into("<hhh", report, accel_offset,
                     round(-math.sin(a) * 8192), 0, round(math.cos(a) * 8192))
    return bytes(report)


def test_dualshock4_usb_and_bluetooth_sensor_offsets():
    usb = decode_dualshock4_motion(_input(0x01, angle=12, timestamp=1234))
    bt = decode_dualshock4_motion(_input(0x11, angle=-8, gyro_y_dps=6, timestamp=0xFF00))
    assert usb.sensor_timestamp == 1234
    assert bt.sensor_timestamp == 0xFF00
    assert usb.gyro[1] == -4096
    assert bt.gyro[1] == 6144
    assert usb.accel[0] == round(-math.sin(math.radians(12)) * 8192)


def test_dualshock4_sensor_decoder_rejects_minimal_bluetooth_report():
    assert decode_dualshock4_motion(bytes([0x01]) + bytes(9)) is None
    assert decode_dualshock4_motion(bytes([0x11]) + bytes(20)) is None


def test_dualshock4_usb_and_bluetooth_factory_calibration():
    for report_id in (0x02, 0x05):
        calibration = DualShock4FactoryCalibration.from_feature_report(_feature(report_id))
        assert calibration is not None
        assert calibration.gyro_bias == (100, -40, 25)
        assert all(abs(v - 1 / 1024) < 1e-9 for v in calibration.gyro_dps_per_count)
        assert all(abs(v - 1 / 8192) < 1e-9 for v in calibration.accel_g_per_count)
    assert DualShock4FactoryCalibration.from_feature_report(bytes(37)) is None


def test_dualshock4_gyro_uses_16bit_sensor_clock_with_wraparound():
    assert DUALSHOCK4_SENSOR_TICKS_PER_SECOND == 187500
    gyro = DualShock4GyroSteering(
        enabled=True, center_gravity=(0, 0, 1), deadzone_degrees=0,
        factory_calibration=_feature(0x02),
    )
    start = 0xFFF0
    for i in range(100):
        report = bytearray(_input(0x01, gyro_y_dps=-15, timestamp=(start + i*1875) & 0xFFFF))
        struct.pack_into("<hhh", report, 19, 0, 0, 16384)  # 2g: suppress gravity correction
        gyro.update(decode_dualshock4_motion(report), now=1.0 + i*0.001)
    assert 14.0 < gyro.current_angle_degrees < 15.2
    assert gyro.steering_value > 0
    assert abs(gyro.sample_rate_hz - 100.0) < 1.0
