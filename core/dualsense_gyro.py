"""DualSense motion report decoding and low-latency steering tilt filter."""

from __future__ import annotations

from dataclasses import dataclass
import math
import struct
import threading
import time


DUALSENSE_VENDOR_ID = 0x054C
DUALSENSE_PRODUCT_IDS = (0x0CE6, 0x0DF2)
GYRO_COUNTS_PER_DEGREE_PER_SECOND = 1024.0
ACCEL_COUNTS_PER_G = 8192.0
SENSOR_TICKS_PER_SECOND = 3_000_000.0


@dataclass(frozen=True)
class DualSenseMotion:
    gyro: tuple[int, int, int]
    accel: tuple[int, int, int]
    sensor_timestamp: int


@dataclass(frozen=True)
class DualSenseFactoryCalibration:
    gyro_bias: tuple[int, int, int]
    gyro_dps_per_count: tuple[float, float, float]
    accel_bias: tuple[float, float, float]
    accel_g_per_count: tuple[float, float, float]

    @classmethod
    def from_feature_report(cls, report: bytes) -> "DualSenseFactoryCalibration | None":
        """Decode DualSense feature report 0x05 calibration parameters."""
        report = bytes(report)
        if len(report) < 35 or report[0] != 0x05:
            return None

        s16 = lambda offset: struct.unpack_from("<h", report, offset)[0]
        gyro_bias = tuple(s16(offset) for offset in (1, 3, 5))
        gyro_plus = tuple(s16(offset) for offset in (7, 11, 15))
        gyro_minus = tuple(s16(offset) for offset in (9, 13, 17))
        speed_sum = s16(19) + s16(21)
        gyro_scale = tuple(
            speed_sum / (abs(plus - bias) + abs(minus - bias))
            if abs(plus - bias) + abs(minus - bias) and speed_sum
            else 2048.0 / 32767.0
            for bias, plus, minus in zip(gyro_bias, gyro_plus, gyro_minus)
        )

        accel_plus = tuple(s16(offset) for offset in (23, 27, 31))
        accel_minus = tuple(s16(offset) for offset in (25, 29, 33))
        accel_bias = tuple(plus - (plus - minus) / 2.0 for plus, minus in zip(accel_plus, accel_minus))
        accel_scale = tuple(
            2.0 / (plus - minus) if plus != minus else 4.0 / 32767.0
            for plus, minus in zip(accel_plus, accel_minus)
        )
        return cls(gyro_bias, gyro_scale, accel_bias, accel_scale)

    def gyro_rate_radians_per_second(self, raw: tuple[int, int, int]):
        return tuple(
            math.radians((value - bias) * scale)
            for value, bias, scale in zip(raw, self.gyro_bias, self.gyro_dps_per_count)
        )

    def accel_g(self, raw: tuple[int, int, int]):
        return tuple(
            (value - bias) * scale
            for value, bias, scale in zip(raw, self.accel_bias, self.accel_g_per_count)
        )


def decode_dualsense_motion(report: bytes) -> DualSenseMotion | None:
    """Decode gyro, accelerometer and the sensor clock from USB/BT reports."""
    report = bytes(report)
    if not report:
        return None

    if report[0] == 0x01:
        gyro_offset = 16
    elif report[0] == 0x31:
        gyro_offset = 17
    else:
        return None

    accel_offset = gyro_offset + 6
    timestamp_offset = accel_offset + 6
    if len(report) < timestamp_offset + 4:
        return None

    gyro = struct.unpack_from("<hhh", report, gyro_offset)
    accel = struct.unpack_from("<hhh", report, accel_offset)
    timestamp = struct.unpack_from("<I", report, timestamp_offset)[0]
    return DualSenseMotion(gyro, accel, timestamp)


def is_dualsense(vendor_id, product_id) -> bool:
    try:
        return int(vendor_id) == DUALSENSE_VENDOR_ID and int(product_id) in DUALSENSE_PRODUCT_IDS
    except (TypeError, ValueError):
        return False


def _dot(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: tuple[float, float, float], b: tuple[float, float, float]):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _unit(vector: tuple[float, float, float]) -> tuple[float, float, float] | None:
    length = math.sqrt(_dot(vector, vector))
    if length < 1e-9:
        return None
    return tuple(component / length for component in vector)


def _wrap_radians(value: float) -> float:
    return (value + math.pi) % (2.0 * math.pi) - math.pi



DUALSHOCK4_GYRO_FALLBACK_DPS_PER_COUNT = 2048.0 / 32767.0
DUALSHOCK4_SENSOR_TICKS_PER_SECOND = 187_500.0


def is_dualshock4(vendor_id, product_id) -> bool:
    try:
        vendor = int(vendor_id, 0) if isinstance(vendor_id, str) else int(vendor_id)
        product = int(product_id, 0) if isinstance(product_id, str) else int(product_id)
    except (TypeError, ValueError):
        return False
    return vendor == 0x054C and product in (0x05C4, 0x09CC)


@dataclass(frozen=True)
class DualShock4FactoryCalibration:
    gyro_bias: tuple[int, int, int]
    gyro_dps_per_count: tuple[float, float, float]
    accel_bias: tuple[float, float, float]
    accel_g_per_count: tuple[float, float, float]

    @classmethod
    def from_feature_report(cls, report: bytes) -> "DualShock4FactoryCalibration | None":
        report = bytes(report)
        if not report or report[0] not in (0x02, 0x05):
            return None
        if (report[0] == 0x02 and len(report) < 37) or (report[0] == 0x05 and len(report) < 41):
            return None
        s16 = lambda offset: struct.unpack_from("<h", report, offset)[0]
        gyro_bias = tuple(s16(offset) for offset in (1, 3, 5))
        if report[0] == 0x02:
            gyro_plus = tuple(s16(offset) for offset in (7, 11, 15))
            gyro_minus = tuple(s16(offset) for offset in (9, 13, 17))
        else:
            gyro_plus = tuple(s16(offset) for offset in (7, 9, 11))
            gyro_minus = tuple(s16(offset) for offset in (13, 15, 17))
        speed_sum = s16(19) + s16(21)
        gyro_scale = tuple(
            speed_sum / (abs(plus - bias) + abs(minus - bias))
            if abs(plus - bias) + abs(minus - bias) and speed_sum > 0
            else DUALSHOCK4_GYRO_FALLBACK_DPS_PER_COUNT
            for bias, plus, minus in zip(gyro_bias, gyro_plus, gyro_minus)
        )
        accel_plus = tuple(s16(offset) for offset in (23, 27, 31))
        accel_minus = tuple(s16(offset) for offset in (25, 29, 33))
        accel_bias = tuple(plus - (plus - minus) / 2.0 for plus, minus in zip(accel_plus, accel_minus))
        accel_scale = tuple(
            2.0 / (plus - minus) if plus != minus else 4.0 / 32767.0
            for plus, minus in zip(accel_plus, accel_minus)
        )
        return cls(gyro_bias, gyro_scale, accel_bias, accel_scale)

    def gyro_rate_radians_per_second(self, raw):
        return tuple(math.radians((v - b) * s) for v, b, s in zip(raw, self.gyro_bias, self.gyro_dps_per_count))

    def accel_g(self, raw):
        return tuple((v - b) * s for v, b, s in zip(raw, self.accel_bias, self.accel_g_per_count))


def decode_dualshock4_motion(report: bytes) -> DualSenseMotion | None:
    report = bytes(report)
    if not report:
        return None
    if report[0] == 0x01:
        if len(report) < 64:
            return None
        timestamp_offset, gyro_offset = 10, 13
    elif report[0] == 0x11:
        if len(report) < 78:
            return None
        timestamp_offset, gyro_offset = 12, 15
    else:
        return None
    accel_offset = gyro_offset + 6
    gyro = struct.unpack_from("<hhh", report, gyro_offset)
    accel = struct.unpack_from("<hhh", report, accel_offset)
    timestamp = struct.unpack_from("<H", report, timestamp_offset)[0]
    return DualSenseMotion(gyro, accel, timestamp)




class DualSenseGyroSteering:
    """Estimate lateral tilt with gyro integration corrected by gravity.

    The controller's across-pad direction is sensor X. At center calibration,
    its measured gravity vector defines the neutral pose. Their cross product
    gives the physical axis around which a left/right tilt rotates, avoiding a
    hard-coded assumption that a sensor axis named X/Y/Z is the steering axis.
    """

    # A short correction time constant keeps the gravity reference responsive.
    # The gyroscope still supplies the immediate rotation estimate.
    complementary_time_constant = 0.025
    min_gravity_magnitude_g = 0.80
    max_gravity_magnitude_g = 1.20
    max_sample_interval = 0.05
    full_steer_angle_degrees = 20.0

    def __init__(
        self,
        *,
        enabled: bool = False,
        sensitivity: float = 1.0,
        deadzone_degrees: float = 2.0,
        center_gravity: tuple[float, float, float] | None = None,
        factory_calibration: bytes | None = None,
        sensor_timestamp_bits: int = 32,
        sensor_ticks_per_second: float = SENSOR_TICKS_PER_SECOND,
        fallback_gyro_dps_per_count: float = 2048.0 / 32767.0,
    ):
        self._lock = threading.RLock()
        self.enabled = bool(enabled)
        self.sensitivity = self._clamp(float(sensitivity), 0.25, 4.0)
        self.deadzone_degrees = self._clamp(float(deadzone_degrees), 0.0, 15.0)
        self.center_gravity = _unit(tuple(center_gravity)) if center_gravity else None
        self._steering_axis = None
        self._steering_lateral = None
        self._angle_radians: float | None = None
        self._last_host_time: float | None = None
        self._last_sensor_timestamp: int | None = None
        self._last_accel_g: tuple[float, float, float] | None = None
        self._last_accel_magnitude = 0.0
        self._sample_rate_hz: float | None = None
        self._sensor_timestamp_mask = (1 << max(1, min(32, int(sensor_timestamp_bits)))) - 1
        self._sensor_ticks_per_second = max(1.0, float(sensor_ticks_per_second))
        self._fallback_gyro_dps_per_count = max(1e-9, float(fallback_gyro_dps_per_count))
        self._factory_calibration = DualSenseFactoryCalibration.from_feature_report(
            factory_calibration
        ) if factory_calibration else None
        if self.center_gravity is not None:
            self._set_steering_axis()

    @staticmethod
    def _clamp(value: float, low: float, high: float) -> float:
        return max(low, min(high, value))

    def set_enabled(self, enabled: bool) -> None:
        with self._lock:
            enabled = bool(enabled)
            if enabled != self.enabled:
                self._angle_radians = None
                self._last_host_time = None
                self._last_sensor_timestamp = None
                self._sample_rate_hz = None
            self.enabled = enabled

    def set_parameters(self, sensitivity: float, deadzone_degrees: float) -> None:
        with self._lock:
            self.sensitivity = self._clamp(float(sensitivity), 0.25, 4.0)
            self.deadzone_degrees = self._clamp(float(deadzone_degrees), 0.0, 15.0)

    def set_factory_calibration(self, report: bytes) -> None:
        calibration = DualSenseFactoryCalibration.from_feature_report(report)
        if calibration is not None:
            with self._lock:
                self._factory_calibration = calibration

    def _set_steering_axis(self) -> None:
        if self.center_gravity is None:
            self._steering_axis = None
            return

        # Sensor X is aligned across the controller body. Its cross product
        # with measured neutral gravity yields the actual left/right roll axis.
        lateral_axis = (1.0, 0.0, 0.0)
        lateral = _unit(tuple(
            lateral_axis[i] - _dot(lateral_axis, self.center_gravity) * self.center_gravity[i]
            for i in range(3)
        ))
        if lateral is None:
            lateral_axis = (0.0, 1.0, 0.0)
            lateral = _unit(tuple(
                lateral_axis[i] - _dot(lateral_axis, self.center_gravity) * self.center_gravity[i]
                for i in range(3)
            ))
        axis = _unit(_cross(lateral, self.center_gravity)) if lateral is not None else None
        self._steering_lateral = lateral
        self._steering_axis = axis

    @property
    def calibrated_center(self) -> tuple[float, float, float] | None:
        with self._lock:
            return self.center_gravity

    @property
    def current_angle_degrees(self) -> float:
        with self._lock:
            return math.degrees(self._angle_radians or 0.0)

    @property
    def sample_rate_hz(self) -> float | None:
        """Smoothed rate of valid hardware-timestamped sensor reports."""
        with self._lock:
            return self._sample_rate_hz

    def _steering_value_locked(self) -> int:
        """Return the current XInput value while the state lock is held."""
        if not self.enabled or self._angle_radians is None:
            return 0
        angle = math.degrees(self._angle_radians)
        deadzone = self.deadzone_degrees
        magnitude = abs(angle)
        if magnitude <= deadzone:
            return 0
        adjusted = math.copysign(magnitude - deadzone, angle)
        range_degrees = self.full_steer_angle_degrees / self.sensitivity
        normalized = self._clamp(adjusted / max(1e-6, range_degrees - deadzone), -1.0, 1.0)
        return int(round(normalized * 32767.0))

    @property
    def steering_value(self) -> int:
        with self._lock:
            return self._steering_value_locked()

    def update(self, motion: DualSenseMotion, now: float | None = None) -> int:
        """Process one HID sample and return the signed XInput steering axis."""
        now = time.monotonic() if now is None else float(now)
        with self._lock:
            calibration = self._factory_calibration
        accel = (
            calibration.accel_g(motion.accel)
            if calibration is not None
            else tuple(value / ACCEL_COUNTS_PER_G for value in motion.accel)
        )
        accel_magnitude = math.sqrt(_dot(accel, accel))
        gravity = _unit(accel)

        with self._lock:
            if gravity is None:
                return self._steering_value_locked()
            self._last_accel_g = accel
            self._last_accel_magnitude = accel_magnitude
            if self.center_gravity is None:
                self.center_gravity = gravity
                self._set_steering_axis()
                self._angle_radians = 0.0

            # DualSense sensor timestamps are 32-bit values in 1/3-us units.
            # Using the device clock avoids host-thread scheduling jitter.
            host_dt = 0.0 if self._last_host_time is None else now - self._last_host_time
            self._last_host_time = now
            sensor_dt = None
            previous_timestamp = self._last_sensor_timestamp
            timestamp_mask = self._sensor_timestamp_mask
            sensor_timestamp = int(motion.sensor_timestamp) & timestamp_mask
            if previous_timestamp is not None:
                delta_ticks = (sensor_timestamp - int(previous_timestamp)) & timestamp_mask
                max_ticks = int(self.max_sample_interval * self._sensor_ticks_per_second)
                if 0 < delta_ticks <= max_ticks:
                    sensor_dt = delta_ticks / self._sensor_ticks_per_second
            self._last_sensor_timestamp = sensor_timestamp
            dt = self._clamp(
                sensor_dt if sensor_dt is not None else host_dt,
                0.0,
                self.max_sample_interval,
            )

            # Expose the real device report rate for diagnostics. This is based
            # only on the controller clock, not on GUI refresh or Python timing.
            if sensor_dt is not None and sensor_dt > 0.0:
                measured_rate = 1.0 / sensor_dt
                if 1.0 <= measured_rate <= 5000.0:
                    if self._sample_rate_hz is None:
                        self._sample_rate_hz = measured_rate
                    else:
                        rate_alpha = 1.0 - math.exp(-dt / 0.12)
                        self._sample_rate_hz += rate_alpha * (
                            measured_rate - self._sample_rate_hz
                        )

            if self._steering_axis is None:
                return self._steering_value_locked()

            gyro_rad_s = (
                calibration.gyro_rate_radians_per_second(motion.gyro)
                if calibration is not None
                else tuple(
                    math.radians(value * self._fallback_gyro_dps_per_count)
                    for value in motion.gyro
                )
            )
            angular_rate = _dot(gyro_rad_s, self._steering_axis)
            previous = self._angle_radians or 0.0
            predicted = previous + angular_rate * dt

            lateral = self._steering_lateral or (1.0, 0.0, 0.0)
            accel_angle = math.atan2(
                -_dot(gravity, lateral), _dot(gravity, self.center_gravity)
            )
            if self._angle_radians is None:
                self._angle_radians = accel_angle
            elif (
                self.min_gravity_magnitude_g
                <= accel_magnitude
                <= self.max_gravity_magnitude_g
            ):
                correction = 1.0 - math.exp(-dt / self.complementary_time_constant)
                self._angle_radians = predicted + correction * _wrap_radians(
                    accel_angle - predicted
                )
            else:
                # Accelerometer is unreliable during strong linear acceleration.
                self._angle_radians = predicted
            return self._steering_value_locked()

    def calibrate_center(self) -> tuple[float, float, float] | None:
        """Set current gravity direction as the new physical neutral pose."""
        with self._lock:
            gravity = (
                _unit(self._last_accel_g)
                if (
                    self._last_accel_g
                    and self.min_gravity_magnitude_g
                    <= self._last_accel_magnitude
                    <= self.max_gravity_magnitude_g
                )
                else None
            )
            if gravity is None:
                return None
            self.center_gravity = gravity
            self._set_steering_axis()
            self._angle_radians = 0.0
            self._last_host_time = None
            self._last_sensor_timestamp = None
            self._sample_rate_hz = None
            return gravity

    def reset(self) -> None:
        """Clear temporal state on disconnect while retaining saved preferences."""
        with self._lock:
            self._angle_radians = None
            self._last_host_time = None
            self._last_sensor_timestamp = None
            self._last_accel_g = None
            self._last_accel_magnitude = 0.0
            self._sample_rate_hz = None


class DualShock4GyroSteering(DualSenseGyroSteering):
    """DS4 gyro steering with its factory calibration and 16-bit device clock."""

    def __init__(self, *, enabled=False, sensitivity=1.0, deadzone_degrees=2.0,
                 center_gravity=None, factory_calibration=None):
        super().__init__(
            enabled=enabled,
            sensitivity=sensitivity,
            deadzone_degrees=deadzone_degrees,
            center_gravity=center_gravity,
            factory_calibration=None,
            sensor_timestamp_bits=16,
            sensor_ticks_per_second=DUALSHOCK4_SENSOR_TICKS_PER_SECOND,
            fallback_gyro_dps_per_count=DUALSHOCK4_GYRO_FALLBACK_DPS_PER_COUNT,
        )
        self._factory_calibration = (
            DualShock4FactoryCalibration.from_feature_report(factory_calibration)
            if factory_calibration else None
        )

    def set_factory_calibration(self, report: bytes) -> None:
        calibration = DualShock4FactoryCalibration.from_feature_report(report)
        if calibration is not None:
            with self._lock:
                self._factory_calibration = calibration
