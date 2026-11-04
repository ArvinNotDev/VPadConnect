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


class DualSenseGyroSteering:
    """Estimate lateral tilt with gyro integration corrected by gravity.

    The controller's across-pad direction is sensor X. At center calibration,
    its measured gravity vector defines the neutral pose. Their cross product
    gives the physical axis around which a left/right tilt rotates, avoiding a
    hard-coded assumption that a sensor axis named X/Y/Z is the steering axis.
    """

    # Keep the gravity correction responsive without aggressively filtering
    # the high-rate gyroscope signal.
    complementary_time_constant = 0.12
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
            if enabled and not self.enabled:
                self._angle_radians = None
                self._last_host_time = None
                self._last_sensor_timestamp = None
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
            sensor_timestamp = int(motion.sensor_timestamp) & 0xFFFFFFFF
            if previous_timestamp is not None:
                delta_ticks = (sensor_timestamp - int(previous_timestamp)) & 0xFFFFFFFF
                max_ticks = int(self.max_sample_interval * SENSOR_TICKS_PER_SECOND)
                if 0 < delta_ticks <= max_ticks:
                    sensor_dt = delta_ticks / SENSOR_TICKS_PER_SECOND
            self._last_sensor_timestamp = sensor_timestamp
            dt = self._clamp(
                sensor_dt if sensor_dt is not None else host_dt,
                0.0,
                self.max_sample_interval,
            )

            if self._steering_axis is None:
                return self._steering_value_locked()

            gyro_rad_s = (
                calibration.gyro_rate_radians_per_second(motion.gyro)
                if calibration is not None
                else tuple(
                    math.radians(value * (2048.0 / 32767.0))
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
            elif 0.70 <= accel_magnitude <= 1.30:
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
                if self._last_accel_g and 0.70 <= self._last_accel_magnitude <= 1.30
                else None
            )
            if gravity is None:
                return None
            self.center_gravity = gravity
            self._set_steering_axis()
            self._angle_radians = 0.0
            self._last_host_time = None
            self._last_sensor_timestamp = None
            return gravity

    def reset(self) -> None:
        """Clear temporal state on disconnect while retaining saved preferences."""
        with self._lock:
            self._angle_radians = None
            self._last_host_time = None
            self._last_sensor_timestamp = None
            self._last_accel_g = None
            self._last_accel_magnitude = 0.0
