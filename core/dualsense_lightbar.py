"""DualSense USB/Bluetooth Lightbar output reports."""

from __future__ import annotations

import re
import threading
import time
import hid

from core.dualsense_output import (
    dualsense_output_lock,
    next_dualsense_bt_sequence,
)


SONY_VENDOR_ID = 0x054C
DUALSENSE_PRODUCT_IDS = (0x0CE6, 0x0DF2)  # DualSense and optional Edge support.

USB_OUTPUT_REPORT_ID = 0x02
# The USB HID descriptor defines report 0x02 as 47 data bytes plus the ID.
USB_OUTPUT_REPORT_LENGTH = 48
BT_OUTPUT_REPORT_ID = 0x31
BT_OUTPUT_REPORT_LENGTH = 78
BT_OUTPUT_CRC_SEED = 0xA2
LIGHTBAR_SETUP_LIGHT_OUT = 0x02

DEFAULT_LIGHTBAR_COLOR = "#8B5CF6"
CHARGING_LIGHTBAR_COLOR = (56, 189, 248)

# Saturated status colors remain easy to distinguish on the controller LEDs.
BATTERY_HIGH_COLOR = (0, 255, 0)       # 70–100%: green
BATTERY_MEDIUM_COLOR = (255, 200, 0)   # 40–69%: yellow
BATTERY_LOW_COLOR = (255, 80, 0)       # 20–39%: orange
BATTERY_CRITICAL_COLOR = (255, 0, 0)  # 0–19%: red

# Let the DualSense finish handing the startup lightbar back to host control.
LIGHTBAR_STARTUP_SETTLE_SECONDS = 0.08


def is_dualsense_device(vendor_id, product_id) -> bool:
    try:
        return int(vendor_id) == SONY_VENDOR_ID and int(product_id) in DUALSENSE_PRODUCT_IDS
    except (TypeError, ValueError):
        return False


def dualsense_bt_crc(report_without_crc: bytes) -> int:
    """Compute the DualSense Bluetooth output CRC32 used by Linux/dualsensectl."""
    crc = 0xFFFFFFFF
    for value in bytes((BT_OUTPUT_CRC_SEED,)) + bytes(report_without_crc):
        crc ^= value
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xEDB88320
            else:
                crc >>= 1
    return (~crc) & 0xFFFFFFFF


def _rgb(color) -> tuple[int, int, int]:
    return tuple(max(0, min(255, int(channel))) for channel in color)


def build_usb_lightbar_report(color, enabled: bool = True) -> bytearray:
    """Build USB report 0x02 at its descriptor-defined 48-byte length."""
    report = bytearray(USB_OUTPUT_REPORT_LENGTH)
    report[0] = USB_OUTPUT_REPORT_ID
    # Color updates use only valid_flag1 + RGB.  Lightbar setup/power control
    # is a separate DualSense output command and must not be mixed into this
    # color report.
    report[2] = 0x04  # valid_flag1: enable Lightbar color control.
    report[45:48] = bytes(_rgb(color) if enabled else (0, 0, 0))
    return report


def build_bt_lightbar_report(sequence: int, color, enabled: bool = True) -> bytearray:
    """Build the 78-byte DualSense Bluetooth output report (without CRC seed)."""
    report = bytearray(BT_OUTPUT_REPORT_LENGTH)
    report[0] = BT_OUTPUT_REPORT_ID
    report[1] = (int(sequence) & 0x0F) << 4
    report[2] = 0x10
    # Color updates use only valid_flag1 + RGB.  Do not add the separate
    # Lightbar setup command to the same report.
    report[4] = 0x04  # valid_flag1: enable Lightbar color control.
    report[47:50] = bytes(_rgb(color) if enabled else (0, 0, 0))
    report[74:78] = dualsense_bt_crc(bytes(report[:-4])).to_bytes(4, "little")
    return report


def build_usb_lightbar_reset_report() -> bytearray:
    """Release controller startup lighting before applying a custom color."""
    report = bytearray(USB_OUTPUT_REPORT_LENGTH)
    report[0] = USB_OUTPUT_REPORT_ID
    report[39] = 0x02  # valid_flag2: LIGHTBAR_SETUP_CONTROL_ENABLE
    report[42] = LIGHTBAR_SETUP_LIGHT_OUT  # Fade out startup/controller lighting.
    return report


def build_bt_lightbar_reset_report(sequence: int) -> bytearray:
    """Release controller startup lighting before applying a custom color."""
    report = bytearray(BT_OUTPUT_REPORT_LENGTH)
    report[0] = BT_OUTPUT_REPORT_ID
    report[1] = (int(sequence) & 0x0F) << 4
    report[2] = 0x10
    report[41] = 0x02  # valid_flag2: LIGHTBAR_SETUP_CONTROL_ENABLE
    report[44] = LIGHTBAR_SETUP_LIGHT_OUT  # Fade out startup/controller lighting.
    report[74:78] = dualsense_bt_crc(bytes(report[:-4])).to_bytes(4, "little")
    return report


def resolve_lightbar_color(settings: dict, battery_state=None) -> tuple[tuple[int, int, int], bool]:
    """Return the effective RGB and enabled state without altering saved color."""
    if not settings.get("enabled", False):
        return (0, 0, 0), False

    if battery_state is not None:
        percent, charging = battery_state
        if settings.get("charging_indication", False) and charging:
            return CHARGING_LIGHTBAR_COLOR, True
        if settings.get("battery_mode", False):
            percent = max(0, min(100, int(percent)))
            if percent >= 70:
                return BATTERY_HIGH_COLOR, True
            if percent >= 40:
                return BATTERY_MEDIUM_COLOR, True
            if percent >= 20:
                return BATTERY_LOW_COLOR, True
            return BATTERY_CRITICAL_COLOR, True

    color = str(settings.get("color", DEFAULT_LIGHTBAR_COLOR)).strip()
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        color = DEFAULT_LIGHTBAR_COLOR
    return tuple(bytes.fromhex(color[1:])), True


class DualSenseLightbar:
    """Coalescing per-controller writer; sends only changed Lightbar states."""

    def __init__(
        self,
        device_path,
        transport=None,
        controller_key=None,
        device_info=None,
        debug: bool = False,
    ):
        self.device_path = device_path
        self._controller_key = controller_key or device_path
        self._device_info = device_info or {}
        self._bluetooth = self._is_bluetooth_transport(
            transport,
            device_path,
            self._device_info.get("interface_number"),
        )
        self._debug = bool(debug)
        self._condition = threading.Condition()
        self._pending = None
        self._stopping = False
        self._device = None
        self._initialized = False
        self._last_sent = None
        self._last_error_message = None
        self._in_flight = None
        self._thread = threading.Thread(
            target=self._run,
            name="DualSenseLightbar",
            daemon=True,
        )
        self._thread.start()

    @staticmethod
    def _is_bluetooth_transport(transport, device_path, interface_number=None) -> bool:
        if transport == 2 or str(transport) == "2":
            return True
        if transport == 1 or str(transport) == "1":
            return False
        text = str(transport or "").upper()
        if "BLUETOOTH" in text or text in {"BT", "BTH"}:
            return True
        if "USB" in text:
            return False
        try:
            if int(interface_number) == -1:
                return True
        except (TypeError, ValueError):
            pass
        path = str(device_path).upper()
        return "BTHENUM" in path or "BLUETOOTH" in path

    def set_color(self, color, enabled: bool = True) -> None:
        command = (bool(enabled), _rgb(color))
        with self._condition:
            if self._stopping:
                return
            if command == self._pending:
                return
            if command == self._last_sent and self._in_flight is None:
                self._pending = None
                return
            self._pending = command
            self._condition.notify()

    def stop(self) -> None:
        """Finish any queued update and close the handle without changing color."""
        with self._condition:
            self._stopping = True
            self._condition.notify()
        self._thread.join(timeout=1.0)
        if self._thread.is_alive():
            self._close_device()

    def _run(self) -> None:
        retry_delay = 0.25
        while True:
            with self._condition:
                while self._pending is None and not self._stopping:
                    self._condition.wait()
                if self._pending is None and self._stopping:
                    break
                command = self._pending
                self._pending = None
                self._in_flight = command

            sent = command == self._last_sent or self._send(command)
            with self._condition:
                self._in_flight = None
                if sent:
                    self._last_sent = command
                    self._last_error_message = None
                    retry_delay = 0.25
                elif self._stopping:
                    self._pending = None
                else:
                    # Keep the latest requested color alive across transient
                    # HID-open/write failures during controller startup.
                    if self._pending is None:
                        self._pending = command
                    if self._pending == command:
                        self._condition.wait(timeout=retry_delay)
                    retry_delay = min(retry_delay * 2.0, 2.0)
        self._close_device()

    def _log_output_error(self, operation: str, exc: Exception) -> None:
        message = f"{operation}: {exc}"
        if message != self._last_error_message:
            print(f"[DualSenseLightbar] {message}")
            self._last_error_message = message

    def _ensure_device(self) -> bool:
        if self._device is not None:
            return True
        try:
            device = hid.device()
            device.open_path(self.device_path)
            self._device = device
            self._initialized = False
            if self._debug:
                info = self._device_info
                transport = "Bluetooth" if self._bluetooth else "USB"
                try:
                    vendor_id = info.get("vendor_id", SONY_VENDOR_ID)
                    product_id = info.get("product_id")
                    if isinstance(vendor_id, str):
                        vendor_id = int(vendor_id, 0)
                    if isinstance(product_id, str):
                        product_id = int(product_id, 0)
                    vid_pid = f"{int(vendor_id):04X}:{int(product_id):04X}"
                except (TypeError, ValueError):
                    vid_pid = f"{info.get('vendor_id', SONY_VENDOR_ID)}:{info.get('product_id')}"
                print(
                    "[DualSenseLightbar] Opened output interface: "
                    f"controller={self._controller_key!r} transport={transport} "
                    f"path={self.device_path!r} "
                    f"VID:PID={vid_pid} "
                    f"usage_page={info.get('usage_page')} usage={info.get('usage')} "
                    f"interface_number={info.get('interface_number')} "
                    f"bus_type={info.get('bus_type', info.get('transport'))}"
                )
            return True
        except Exception as exc:
            self._log_output_error("Failed to open device", exc)
            self._close_device()
            return False

    def _log_report(self, label: str, report: bytearray, written=None) -> None:
        if not self._debug:
            return

        transport = "Bluetooth" if self._bluetooth else "USB"
        if self._bluetooth:
            flags = (
                f"valid_flags={report[3]:02X}/{report[4]:02X}/{report[41]:02X} "
                f"tag={report[2]:02X} sequence={report[1] >> 4}"
            )
            rgb = report[47:50]
            crc = int.from_bytes(report[74:78], "little")
            details = f"{flags} setup={report[44]:02X} crc={crc:08X}"
        else:
            flags = f"valid_flags={report[1]:02X}/{report[2]:02X}/{report[39]:02X}"
            rgb = report[45:48]
            details = f"{flags} setup={report[42]:02X}"

        print(
            f"[DualSenseLightbar] {label}: controller={self._controller_key!r} "
            f"transport={transport} path={self.device_path!r} "
            f"report_id={report[0]:02X} report_length={len(report)} "
            f"rgb={rgb[0]:02X} {rgb[1]:02X} {rgb[2]:02X} {details} "
            f"hid_write_return={written}"
        )
        print(f"[DualSenseLightbar] HEX: {bytes(report).hex(' ').upper()}")

    def _write_report(self, label: str, report: bytearray) -> None:
        written = self._device.write(bytes(report))
        self._log_report(label, report, written)
        # Windows HIDAPI can zero-pad to OutputReportByteLength, so a valid
        # return count may be larger than this report's protocol length.
        if written is not None and written < len(report):
            raise OSError(
                f"Short {label} HID write (hid_write returned {written}, "
                f"report length {len(report)})"
            )

    def _send_lightbar_reset(self) -> None:
        if self._bluetooth:
            sequence = next_dualsense_bt_sequence(self._controller_key)
            report = build_bt_lightbar_reset_report(sequence)
        else:
            report = build_usb_lightbar_reset_report()
        self._write_report("setup reset", report)

    def _send(self, command) -> bool:
        enabled, color = command
        if not self._ensure_device():
            return False
        try:
            with dualsense_output_lock(self._controller_key):
                if not self._initialized:
                    self._send_lightbar_reset()
                    time.sleep(LIGHTBAR_STARTUP_SETTLE_SECONDS)
                    self._initialized = True

                if self._bluetooth:
                    sequence = next_dualsense_bt_sequence(self._controller_key)
                    report = build_bt_lightbar_report(sequence, color, enabled)
                else:
                    report = build_usb_lightbar_report(color, enabled)

                self._write_report("color", report)
            return True
        except Exception as exc:
            self._log_output_error("Output report failed", exc)
            self._close_device()
            return False

    def _close_device(self) -> None:
        device = self._device
        self._device = None
        self._initialized = False
        if device is not None:
            try:
                device.close()
            except Exception:
                pass
