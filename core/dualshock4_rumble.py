"""Low-latency classic rumble output for Sony DualShock 4 controllers."""

from __future__ import annotations
import threading
import zlib
import hid

XINPUT_VIBRATION_MAX = 0xFFFF
MOTOR_MAX = 0xFF
USB_OUTPUT_REPORT_ID = 0x05
USB_OUTPUT_REPORT_LENGTH = 32
BT_OUTPUT_REPORT_ID = 0x11
BT_OUTPUT_REPORT_LENGTH = 78
BT_OUTPUT_CRC_SEED = 0xA2
OUTPUT_VALID_FLAG0_MOTOR = 0x01


def _clamp(value, low, high):
    return max(low, min(high, int(value)))


def xinput_to_dualshock4_intensity(value):
    value = _clamp(value, 0, XINPUT_VIBRATION_MAX)
    return (value * MOTOR_MAX + XINPUT_VIBRATION_MAX // 2) // XINPUT_VIBRATION_MAX


def dualshock4_bt_crc(report_without_crc):
    return zlib.crc32(bytes((BT_OUTPUT_CRC_SEED,)) + bytes(report_without_crc)) & 0xFFFFFFFF


def build_usb_report(left_motor, right_motor):
    report = bytearray(USB_OUTPUT_REPORT_LENGTH)
    report[0] = USB_OUTPUT_REPORT_ID
    report[1] = OUTPUT_VALID_FLAG0_MOTOR
    report[4] = _clamp(right_motor, 0, MOTOR_MAX)
    report[5] = _clamp(left_motor, 0, MOTOR_MAX)
    return report


def build_bt_report(left_motor, right_motor):
    report = bytearray(BT_OUTPUT_REPORT_LENGTH)
    report[0] = BT_OUTPUT_REPORT_ID
    report[1] = 0xC0
    report[3] = OUTPUT_VALID_FLAG0_MOTOR
    report[6] = _clamp(right_motor, 0, MOTOR_MAX)
    report[7] = _clamp(left_motor, 0, MOTOR_MAX)
    report[-4:] = dualshock4_bt_crc(report[:-4]).to_bytes(4, "little")
    return report


class DualShock4Rumble:
    """Coalescing background writer; controller HID reads never wait for rumble."""

    def __init__(self, device_path, transport=None, controller_key=None):
        self.device_path = device_path
        self._bluetooth = self._is_bluetooth_transport(transport, device_path)
        self._condition = threading.Condition()
        self._pending = None
        self._stopping = False
        self._device = None
        self._last_sent = None
        self._thread = threading.Thread(target=self._run, name="DualShock4Rumble", daemon=True)
        self._thread.start()

    @staticmethod
    def _is_bluetooth_transport(transport, device_path):
        if transport == 2 or str(transport) == "2":
            return True
        if transport == 1 or str(transport) == "1":
            return False
        text = str(transport or "").upper()
        if "BLUETOOTH" in text or text in {"BT", "BTH"}:
            return True
        if "USB" in text:
            return False
        if isinstance(device_path, bytes):
            device_path = device_path.decode("utf-8", errors="ignore")
        path = str(device_path or "").upper()
        return "BTHENUM" in path or "BLUETOOTH" in path

    @property
    def is_bluetooth(self):
        return self._bluetooth

    def set_xinput_vibration(self, left_motor, right_motor):
        command = (xinput_to_dualshock4_intensity(left_motor), xinput_to_dualshock4_intensity(right_motor))
        with self._condition:
            if self._stopping:
                return
            self._pending = command
            self._condition.notify()

    def stop(self):
        with self._condition:
            if self._stopping:
                return
            self._stopping = True
            self._pending = (0, 0)
            self._condition.notify()
        self._thread.join(timeout=1.0)
        if self._thread.is_alive():
            self._close_device()

    def _run(self):
        try:
            while True:
                with self._condition:
                    while self._pending is None and not self._stopping:
                        self._condition.wait()
                    if self._pending is None:
                        break
                    command = self._pending
                    self._pending = None
                if command != self._last_sent and self._send(*command):
                    self._last_sent = command
                with self._condition:
                    if self._stopping and self._pending is None:
                        break
        finally:
            self._close_device()

    def _ensure_device(self):
        if self._device is not None:
            return True
        try:
            device = hid.device()
            device.open_path(self.device_path)
            self._device = device
            return True
        except Exception as exc:
            print(f"[DualShock4Rumble] Failed to open device: {exc}")
            self._close_device()
            return False

    def _send(self, left_motor, right_motor):
        if not self._ensure_device():
            return False
        try:
            report = build_bt_report(left_motor, right_motor) if self._bluetooth else build_usb_report(left_motor, right_motor)
            written = self._device.write(bytes(report))
            if written is not None and written < 0:
                raise OSError(f"HID write returned {written}")
            return True
        except Exception as exc:
            print(f"[DualShock4Rumble] Output report failed: {exc}")
            self._close_device()
            return False

    def _close_device(self):
        device = self._device
        self._device = None
        if device is not None:
            try:
                device.close()
            except Exception:
                pass
