import json
import logging
import math
import time
from typing import Tuple

try:
    import keyboard as _keyboard
except Exception:
    _keyboard = None

from core.emulator import EmulateX360, EmulateKeyboard
from core.emulator import media_functions, custom_commands
from core.dualsense_lightbar import resolve_lightbar_color
from core.dualsense_gyro import DualSenseGyroSteering, decode_dualsense_motion, is_dualsense
from core.mouse import Mouse, MouseMotion
from core.utils.controller_monitor import controllerMonitor
from core.utils.hotkey_commander import HotkeyCommander
from core.utils.paths import resource_path

logger = logging.getLogger("vpadconnect.mapper")


class Mapper:
    """
    Maps input from a physical HID controller to an emulator (X360 or keyboard).
    """

    # A small fixed deadzone prevents sensor noise and tiny involuntary stick
    # movements from moving the desktop cursor. The output is rescaled so the
    # usable stick range still reaches full speed.
    MOUSE_DEADZONE = 0.10

    def __init__(
        self,
        controller,
        controller_type,
        emulate_to,
        settings,
        controllers_page,
        hotkey_page,
        debug: bool = False,
        lightbar_output=None,
        raw_hid_report_callback=None,
    ):
        self.controller = controller
        self.controller_type = controller_type
        self._connected = False
        self.debug = bool(debug)
        self.settings = settings
        self.controllers_page = controllers_page
        self.raw_hid_report_callback = raw_hid_report_callback
        self._last_raw_report_log_at = 0.0
        self._last_raw_hid_stream_at = 0.0
        self._last_debug_state_log_at = 0.0

        self.mouse_mode = False
        self.mouse_mode_hotkey = False
        self._mouse_active = False
        self._mouse_motion = MouseMotion(smoothing_ms=4.0)

        self._prev_back = False
        self._prev_r3 = False
        self._prev_a = False
        self._prev_b = False
        self._last_battery = None
        self._battery_state = None
        self.lightbar_output = lightbar_output
        self.gyro_steering = None
        try:
            self.lightbar_settings = settings.get_controller_lightbar_settings(
                controller.stable_id
            )
        except (AttributeError, TypeError):
            self.lightbar_settings = {
                "enabled": False,
                "color": "#8B5CF6",
                "battery_mode": False,
                "charging_indication": False,
            }

        if emulate_to == "x360":
            self.emulator = EmulateX360(
                controller.device_path,
                controller.name,
                hotkey_page.hotkey,
                rumble_enabled=(controller_type == "Dualsense"),
                rumble_transport=controller.transport,
                rumble_controller_key=controller.stable_id,
                vibration_enabled=settings.get_vibration_enabled(),
            )
            if is_dualsense(controller.vendor_id, controller.product_id):
                try:
                    gyro_settings = settings.get_controller_gyro_settings(
                        controller.stable_id
                    )
                except (AttributeError, TypeError):
                    gyro_settings = {}
                self.gyro_steering = DualSenseGyroSteering(
                    enabled=gyro_settings.get("enabled", False),
                    sensitivity=gyro_settings.get("sensitivity", 1.0),
                    deadzone_degrees=gyro_settings.get("deadzone_degrees", 2.0),
                    center_gravity=gyro_settings.get("center_gravity"),
                    factory_calibration=getattr(controller, "sensor_calibration", None),
                )
                self.emulator.gyro_steering = self.gyro_steering
                self.emulator.gyro_controller_id = controller.stable_id
            controllers_page.add_x360_instance(self.emulator)
            hotkey_page.add_x360_instance(self.emulator)
        elif emulate_to == "keyboard":
            self.emulator = EmulateKeyboard()
        else:
            raise ValueError(f"Invalid emulate_to target: {emulate_to}")

        self.controller_config = self._load_json(f"{controller_type}.json")
        if self.lightbar_output is not None:
            self._apply_lightbar()

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    def _load_json(self, filename: str) -> dict:
        """
        Load controller profile from the profiles directory.
        """
        try:
            with resource_path("profiles", filename).open("r", encoding="utf-8") as config:
                return json.load(config)
        except FileNotFoundError:
            logger.warning("Controller profile '%s' not found.", filename)
            return {}
        except json.JSONDecodeError:
            logger.error("Controller profile '%s' contains invalid JSON.", filename)
            return {}

    def start(self) -> None:
        """Begin processing HID reports for this controller."""
        if not self._connected:
            self._connected = True
            logger.info("Started mapping for %s (%s)", self.controller.name, self.controller_type)
            if self._debug_enabled():
                logger.debug("Mapping profile loaded for %s: %s", self.controller.name, self.controller_config.keys())

    def stop(self) -> None:
        """
        Stop processing HID reports and shut down the emulator if supported.
        """
        if self._connected:
            logger.info("Stopped mapping for %s", self.controller.name)
        self._connected = False
        self._mouse_motion.reset()
        if self.gyro_steering is not None:
            self.gyro_steering.reset()

        clear_battery = getattr(self.controllers_page, "clear_battery", None)
        if clear_battery is not None:
            try:
                clear_battery(self.controller.device_path)
            except Exception:
                pass

        if hasattr(self.emulator, "shutdown"):
            try:
                self.emulator.shutdown()
            except Exception as e:
                logger.exception("Failed to shut down emulator for %s", self.controller.name)

    # -------------------------------------------------------------------------
    # HID entry points
    # -------------------------------------------------------------------------

    def handle_hid_data(self, data: bytes) -> None:
        """Dispatch raw HID report to the appropriate handler."""
        if not self._connected or self.emulator is None:
            return

        # Raw report capture is opt-in. File logging stays capped at 10 Hz,
        # while the live terminal callback is rate-limited separately so it can
        # show responsive updates without flooding the Qt event queue.
        try:
            raw_debug = bool(self.settings.get_raw_hid_debug())
        except Exception:
            raw_debug = False
        now = time.monotonic()
        if raw_debug:
            report = bytes(data)
            callback = self.raw_hid_report_callback
            if callback is not None and now - self._last_raw_hid_stream_at >= (1.0 / 30.0):
                try:
                    callback(self.controller.name, report)
                except Exception:
                    logger.debug("Could not publish a raw HID report to the live terminal", exc_info=True)
                self._last_raw_hid_stream_at = now

            if now - self._last_raw_report_log_at >= 0.1:
                preview = report[:64].hex(" ")
                suffix = " …" if len(report) > 64 else ""
                logger.debug(
                    "RAW HID controller=%s length=%d bytes=%s%s",
                    self.controller.name, len(report), preview, suffix,
                )
                self._last_raw_report_log_at = now

        if isinstance(self.emulator, EmulateX360):
            self._handle_x360_input(data)
        else:
            self._handle_keyboard_input(data)

    def handle_error(self, msg: str) -> None:
        """Handle device-level errors."""
        logger.error("Device error from %s: %s", self.controller.name, msg)
        self.stop()

    def set_gyro_factory_calibration(self, report: bytes) -> None:
        if self.gyro_steering is not None:
            self.gyro_steering.set_factory_calibration(report)

    def _debug_enabled(self) -> bool:
        try:
            return bool(self.settings.get_developer_debug())
        except Exception:
            return self.debug

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _clamp(v: int, lo: int, hi: int) -> int:
        return max(lo, min(hi, v))

    @staticmethod
    def _scale_stick_0_255_to_x360(val: int, invert_y: bool) -> int:
        """
        Convert 0–255 axis value to XInput signed 16‑bit range.
        """
        centered = float(val) - 128.0
        normalized = -centered / 127.0 if invert_y else centered / 127.0
        scaled = int(round(normalized * 32767.0))
        return int(Mapper._clamp(scaled, -32768, 32767))

    def _steering_x_input(self, analog_x: int, report: bytes) -> int:
        """Use gyro only for DualSense left-stick X when the feature is enabled."""
        steering = self.gyro_steering
        if steering is None or not steering.enabled:
            # Preserve the original stick path exactly and skip sensor work
            # entirely while this optional feature is disabled.
            return analog_x
        motion = decode_dualsense_motion(report)
        if motion is None:
            return 0
        return steering.update(motion)

    @staticmethod
    def _mouse_response(value: float) -> float:
        """Give fine stick movement precision while retaining full-speed travel."""
        value = max(-1.0, min(1.0, float(value)))
        return math.copysign(abs(value) ** 1.35, value)

    @staticmethod
    def _mouse_deadzone(value: float, deadzone: float = MOUSE_DEADZONE) -> float:
        """Remove a fixed center deadzone and preserve the full output range."""
        value = max(-1.0, min(1.0, float(value)))
        deadzone = max(0.0, min(0.99, float(deadzone)))
        magnitude = abs(value)
        if magnitude <= deadzone:
            return 0.0

        remapped = (magnitude - deadzone) / (1.0 - deadzone)
        return math.copysign(remapped, value)

    def _read_byte_safe(self, report: list[int], idx: int | None) -> int:
        """
        Safely read a byte from a HID report by index.
        """
        if idx is None or idx < 0 or idx >= len(report):
            return 0
        return report[idx]

    def _get_button_from_cfg(self, report: list[int], cfg: dict | None) -> bool:
        """
        Decode a digital button state from the report using a mapping entry.
        """
        if cfg is None:
            return False

        byte_idx = cfg.get("index", cfg.get("byte"))
        val = self._read_byte_safe(report, byte_idx)

        mask = cfg.get("mask")
        if mask is not None:
            mask_int = int(mask, 16) if isinstance(mask, str) else int(mask)
            val &= mask_int

        if "value" in cfg:
            return val == cfg["value"]
        return val != 0

    def _get_dpad_from_hat(self, report: list[int], cfg: dict | None) -> Tuple[bool, bool, bool, bool]:
        """
        Decode a hat‑switch style D‑Pad into individual directions.
        """
        if cfg is None:
            return False, False, False, False

        byte_idx = cfg.get("byte")
        raw_val = self._read_byte_safe(report, byte_idx)

        mask = cfg.get("mask", 0x0F)
        if isinstance(mask, str):
            mask = int(mask, 16)

        hat_val = raw_val & mask

        up = hat_val in (0, 1, 7)
        down = hat_val in (3, 4, 5)
        right = hat_val in (1, 2, 3)
        left = hat_val in (5, 6, 7)

        return up, down, left, right

    def _apply_deadzone(
        self,
        raw_x: int,
        raw_y: int,
        deadzone: float,
        invertion: Tuple[bool, bool],
    ) -> Tuple[int, int]:
        """
        Apply radial deadzone and axis inversion, then scale to XInput space.
        """
        invert_x, invert_y = invertion

        cx = raw_x - 128
        cy = raw_y - 128

        if abs(cx) < deadzone * 127:
            cx = 0
        if abs(cy) < deadzone * 127:
            cy = 0

        x_scaled = self._scale_stick_0_255_to_x360(cx + 128, invert_x)
        y_scaled = self._scale_stick_0_255_to_x360(cy + 128, invert_y)

        return x_scaled, y_scaled

    def _apply_button_invertion(self, button: bool, invert: bool) -> bool:
        """
        Optionally invert a digital button state.
        """
        return not button if invert else button

    # -------------------------------------------------------------------------
    # X360 mapping (physical HID)
    # -------------------------------------------------------------------------
    def _interpret_battery(self, battery_byte):
        battery_level = battery_byte & 0x0F  # Lower 4 bits
        charging_state = (battery_byte >> 4) & 0x0F  # Upper 4 bits

        if self.controller_type == "Dualsense":
            # hid-playstation's DualSense status nibble is 0=discharging,
            # 1=charging, 2=full. Each capacity unit represents a 10% band.
            if charging_state == 0x02:
                return 100, False
            if charging_state in (0x00, 0x01):
                percent = min(100, battery_level * 10 + 5)
                return percent, charging_state == 0x01
            return 0, False

        is_charging = (charging_state == 0x02)

        if battery_level == 0x0A:
            percent = 100
        elif battery_level <= 0x09:
            percent = battery_level * 10
        else:
            percent = 100

        # If charging and level shows 9, might actually be full
        if is_charging and battery_level == 0x09:
            percent = 100

        return percent, is_charging

    def _battery_report_index(self, configured_index, report=None):
        """Resolve the battery byte using the report ID before transport metadata."""
        if self.controller_type != "Dualsense":
            return configured_index

        # Use the actual HID input report when available: DualSense USB uses
        # report ID 0x01 (one-byte header), while Bluetooth uses 0x31 (two-byte
        # header). Transport metadata can be missing or stale when the cable is
        # connected, so it should only be a fallback.
        if report:
            report_id = report[0]
            if report_id == 0x01:
                return max(0, configured_index - 1)
            if report_id == 0x31:
                return configured_index

        transport = getattr(self.controller, "transport", None)
        if transport == 1 or str(transport) == "1":  # HIDAPI USB bus type
            return 53 if configured_index == 54 else max(0, configured_index - 1)
        if transport == 2 or str(transport) == "2":  # HIDAPI Bluetooth bus type
            return configured_index

        text = str(transport or "").upper()
        if "USB" in text:
            return 53 if configured_index == 54 else max(0, configured_index - 1)
        return configured_index

    def configure_lightbar(self, settings: dict) -> None:
        """Apply updated per-controller Lightbar preferences from the UI."""
        self.lightbar_settings = dict(settings)
        self._apply_lightbar()

    def _apply_lightbar(self) -> None:
        if self.lightbar_output is None:
            return
        color, enabled = resolve_lightbar_color(
            self.lightbar_settings, self._battery_state
        )
        self.lightbar_output.set_color(color, enabled=enabled)

    def _handle_x360_input(self, data: bytes) -> None:
        """
        Decode a HID report and forward it to the X360 emulator.
        """
        report = list(data)
        if len(report) < 10:
            return

        axes_cfg = self.controller_config.get("axes", {})
        buttons_cfg = self.controller_config.get("buttons", {})
        dpad_cfg = self.controller_config.get("dpad_hat", {})
        battery_cfg = self.controller_config.get("battery_status", {})

        raw_ljx = self._read_byte_safe(report, axes_cfg.get("left_stick_x", {}).get("byte"))
        raw_ljy = self._read_byte_safe(report, axes_cfg.get("left_stick_y", {}).get("byte"))
        raw_rjx = self._read_byte_safe(report, axes_cfg.get("right_stick_x", {}).get("byte"))
        raw_rjy = self._read_byte_safe(report, axes_cfg.get("right_stick_y", {}).get("byte"))
        raw_lt = self._read_byte_safe(report, axes_cfg.get("left_trigger", {}).get("byte"))
        raw_rt = self._read_byte_safe(report, axes_cfg.get("right_trigger", {}).get("byte"))
        battery_percent = None
        is_charging = False
        battery_percent_cfg = battery_cfg.get("percent", {})
        if battery_percent_cfg.get("byte") is not None:
            raw_battery = self._read_byte_safe(
                report,
                self._battery_report_index(battery_percent_cfg.get("byte"), report=report),
            )
            battery_percent, is_charging = self._interpret_battery(raw_battery)
            self._publish_battery(battery_percent, is_charging)
            state = (int(battery_percent), bool(is_charging))
            if state != self._battery_state:
                self._battery_state = state
                self._apply_lightbar()


        left_deadzone, right_deadzone = self.settings.get_deadzones()
        left_inv, right_inv = self.settings.get_joystick_invertion()
        button_inv = self.settings.get_button_invertion()

        ljx, ljy = self._apply_deadzone(raw_ljx, raw_ljy, left_deadzone, left_inv)
        rjx, rjy = self._apply_deadzone(raw_rjx, raw_rjy, right_deadzone, right_inv)
        # Only the left horizontal axis changes; vertical stick and all other
        # controls continue through the original mapping path.
        ljx = self._steering_x_input(ljx, data)

        lt = int(raw_lt)
        rt = int(raw_rt)

        a = self._get_button_from_cfg(report, buttons_cfg.get("cross"))
        b = self._get_button_from_cfg(report, buttons_cfg.get("circle"))
        x_ = self._get_button_from_cfg(report, buttons_cfg.get("square"))
        y_ = self._get_button_from_cfg(report, buttons_cfg.get("triangle"))
        lb = self._get_button_from_cfg(report, buttons_cfg.get("l1"))
        rb = self._get_button_from_cfg(report, buttons_cfg.get("r1"))
        back = self._get_button_from_cfg(report, buttons_cfg.get("share"))
        start = self._get_button_from_cfg(report, buttons_cfg.get("option"))
        l3 = self._get_button_from_cfg(report, buttons_cfg.get("l3"))
        r3 = self._get_button_from_cfg(report, buttons_cfg.get("r3"))

        dpu, dpd, dpl, dpr = self._get_dpad_from_hat(report, dpad_cfg)

        # Keep detailed decoded-state diagnostics useful without writing one
        # record for every HID report; full raw reports have their own toggle.
        now = time.monotonic()
        if now - self._last_debug_state_log_at >= 0.5:
            self._last_debug_state_log_at = now
            if self._debug_enabled():
                pressed = [
                    name for name, active in (
                        ("A", a), ("B", b), ("X", x_), ("Y", y_),
                        ("LB", lb), ("RB", rb), ("BACK", back), ("START", start),
                        ("L3", l3), ("R3", r3), ("D-UP", dpu), ("D-DOWN", dpd),
                        ("D-LEFT", dpl), ("D-RIGHT", dpr),
                    ) if active
                ]
                logger.debug(
                    "Decoded controller=%s sticks=(%d,%d;%d,%d) triggers=(%d,%d) pressed=%s",
                    self.controller.name, raw_ljx, raw_ljy, raw_rjx, raw_rjy,
                    raw_lt, raw_rt, ",".join(pressed) or "none",
                )

        a = self._apply_button_invertion(a, button_inv)
        b = self._apply_button_invertion(b, button_inv)
        x_ = self._apply_button_invertion(x_, button_inv)
        y_ = self._apply_button_invertion(y_, button_inv)
        lb = self._apply_button_invertion(lb, button_inv)
        rb = self._apply_button_invertion(rb, button_inv)
        back = self._apply_button_invertion(back, button_inv)
        start = self._apply_button_invertion(start, button_inv)
        l3 = self._apply_button_invertion(l3, button_inv)
        r3 = self._apply_button_invertion(r3, button_inv)

        if back and r3 and not (self._prev_back and self._prev_r3):
            self.mouse_mode_hotkey = not self.mouse_mode_hotkey

        self.mouse_mode = self.settings.get_mouse_mode()

        mouse_active = bool(self.mouse_mode or self.mouse_mode_hotkey)
        if mouse_active != self._mouse_active:
            self._mouse_active = mouse_active
            if self._debug_enabled():
                logger.debug(
                    "Mouse output %s for %s",
                    "enabled" if mouse_active else "disabled",
                    self.controller.name,
                )
            self._mouse_motion.reset()
            if mouse_active:
                self.emulator.reset_output()
                # Do not turn the mode-switch button press into an accidental
                # mouse click.
                self._prev_a = a
                self._prev_b = b

        if mouse_active:
            sensitivity = max(0.1, float(self.settings.get_mouse_sensitivity()))
            mouse_deadzone = self.settings.get_mouse_deadzone()
            nx = self._mouse_response(
                self._mouse_deadzone(ljx / 32767.0, mouse_deadzone)
            )
            ny = self._mouse_response(
                self._mouse_deadzone(ljy / 32767.0, mouse_deadzone)
            )

            # Pixels per second. The time-based motion integrator below makes
            # this independent of the HID report frequency.
            speed = 850.0 * sensitivity
            target_dx = nx * speed
            target_dy = -ny * speed

            if self.settings.get_dpad_as_mouse():
                dpad_x = int(bool(dpr)) - int(bool(dpl))
                dpad_y = int(bool(dpd)) - int(bool(dpu))
                dpad_length = math.hypot(dpad_x, dpad_y)
                if dpad_length:
                    dpad_speed = 650.0 * sensitivity
                    target_dx += dpad_x / dpad_length * dpad_speed
                    target_dy += dpad_y / dpad_length * dpad_speed

            dx, dy = self._mouse_motion.update(target_dx, target_dy)

            try:
                if dx or dy:
                    Mouse.moveRel(dx, dy, duration=0)
                if a and not self._prev_a:
                    Mouse.leftClick()
                if b and not self._prev_b:
                    Mouse.rightClick()
            except Exception:
                pass

            self._prev_a = a
            self._prev_b = b
        else:
            self.emulator.update(
                ljx, ljy, rjx, rjy,
                a, x_, b, y_,
                rb, rt, lb, lt,
                dpu, dpd, dpr, dpl,
                back, start, l3, r3,
            )

        self._prev_back = back
        self._prev_r3 = r3

    def _publish_battery(self, percent: int, is_charging: bool) -> None:
        """Publish battery changes without touching Qt widgets from HID threads."""
        state = (int(percent), bool(is_charging))
        if state == self._last_battery:
            return
        self._last_battery = state
        publisher = getattr(self.controllers_page, "battery_updated", None)
        if publisher is not None:
            try:
                publisher.emit(self.controller.device_path, *state)
            except Exception:
                pass

    def _handle_keyboard_input(self, data: bytes) -> None:
        """
        Placeholder for keyboard emulation mapping.
        """
        pass


class Phone_mapper:
    """
    Maps input from an authenticated remote client to an emulator.
    """

    def __init__(
        self,
        uuid: str,
        emulate_to: str,
        controllers_page,
        hotkey_page,
        settings,
        debug: bool = False,
    ):
        self.uuid = uuid
        self.settings = settings
        self.debug = debug
        self._connected = True
        self.controllers_page = controllers_page
        self.hotkey = hotkey_page.hotkey
        self.hotkey_commander = HotkeyCommander(media_functions, custom_commands)
        self._last_hotkey_func = None
        self._last_hotkey_time = 0.0
        self._hotkey_interval = 0.1
        self._mouse_buttons = {"left": False, "right": False, "middle": False}

        if emulate_to == "x360":
            self.emulator = EmulateX360(self.uuid, self.uuid, hotkey_page.hotkey)
        elif emulate_to == "keyboard":
            self.emulator = EmulateKeyboard()
        elif emulate_to == "none":
            # Keep secure browser pairing, touch mouse and PC Remote usable
            # when this PC cannot create a virtual XInput device.
            self.emulator = None
        else:
            raise ValueError(f"Invalid emulate_to target: {emulate_to}")

    # -------------------------------------------------------------------------
    # HID entry points
    # -------------------------------------------------------------------------

    def handle_hid_data(self, data: dict) -> None:
        """
        Dispatch normalized remote gamepad state to the appropriate handler.
        """
        if not self._connected:
            return

        if isinstance(self.emulator, EmulateX360):
            self._handle_x360_input(data)
        else:
            self._handle_keyboard_input(data)

    def handle_mouse_data(self, data: dict) -> None:
        """Apply remote touchpad motion and mouse button state to Windows."""
        if not self._connected:
            return

        dx = int(data.get("dx", 0))
        dy = int(data.get("dy", 0))
        scroll = int(data.get("scroll", 0))
        try:
            if dx or dy:
                Mouse.moveRel(dx, dy, duration=0)
        except Exception:
            pass
        try:
            if scroll:
                Mouse.scroll(scroll)
        except Exception:
            pass

        for name in self._mouse_buttons:
            pressed = bool(data.get(name, False))
            if pressed == self._mouse_buttons[name]:
                continue
            try:
                if pressed:
                    Mouse.buttonDown(name)
                else:
                    Mouse.buttonUp(name)
            except Exception:
                pass
            self._mouse_buttons[name] = pressed

    def handle_keyboard_data(self, data: dict) -> None:
        """Apply a bounded text/key event received from a remote client."""
        if not self._connected or not isinstance(data, dict) or _keyboard is None:
            return
        action = data.get("action", "text")
        text = data.get("text", "")
        key = data.get("key", "")
        try:
            if action == "text" and isinstance(text, str) and text:
                _keyboard.write(text, interval=0)
            elif action == "key_down" and isinstance(key, str) and key:
                _keyboard.press(key)
            elif action == "key_up" and isinstance(key, str) and key:
                _keyboard.release(key)
        except Exception:
            # A disconnected desktop session or unsupported key should not
            # tear down the remote connection.
            return

    def release_mouse_buttons(self) -> None:
        """Release remote mouse buttons when changing output mode or disconnecting."""
        for name, pressed in self._mouse_buttons.items():
            if pressed:
                try:
                    Mouse.buttonUp(name)
                except Exception:
                    pass
            self._mouse_buttons[name] = False

    def reset_gamepad(self) -> None:
        """Return the virtual gamepad to neutral before switching to mouse output."""
        if isinstance(self.emulator, EmulateX360):
            self.emulator.reset_output()

    def _handle_keyboard_input(self, data: dict) -> None:
        """
        Placeholder for keyboard emulation mapping from controller input.
        """
        pass

    # -------------------------------------------------------------------------
    # Helpers (kept separate from Mapper for loose coupling)
    # -------------------------------------------------------------------------

    @staticmethod
    def _clamp(v: int, lo: int, hi: int) -> int:
        return max(lo, min(hi, v))

    @staticmethod
    def _scale_stick_0_255_to_x360(val: int, invert_y: bool) -> int:
        centered = float(val) - 128.0
        normalized = -centered / 127.0 if invert_y else centered / 127.0
        scaled = int(round(normalized * 32767.0))
        return int(Phone_mapper._clamp(scaled, -32768, 32767))

    def _apply_deadzone(
        self,
        raw_x: int,
        raw_y: int,
        deadzone: float,
        invertion: Tuple[bool, bool],
    ) -> Tuple[int, int]:
        """
        Apply deadzone and inversion for remote joystick input (0–255).
        """
        invert_x, invert_y = invertion

        cx = raw_x - 128
        cy = raw_y - 128

        if abs(cx) < deadzone * 127:
            cx = 0
        if abs(cy) < deadzone * 127:
            cy = 0

        x_scaled = self._scale_stick_0_255_to_x360(cx + 128, invert_x)
        y_scaled = self._scale_stick_0_255_to_x360(cy + 128, invert_y)

        return x_scaled, y_scaled

    def _apply_button_invertion(self, button: bool, invert: bool) -> bool:
        """
        Optionally invert a digital button state.
        """
        return not button if invert else button

    def _maybe_do_hotkey(self, ok: bool, func: str | None) -> None:
        if not ok or func is None:
            self._last_hotkey_func = None
            return

        now = time.monotonic()
        if func != self._last_hotkey_func:
            self._last_hotkey_func = func
            self._last_hotkey_time = now
            self.hotkey_commander.do(func, False)
            return

        if now - self._last_hotkey_time >= self._hotkey_interval:
            self._last_hotkey_time = now
            self.hotkey_commander.do(func, False)

    # -------------------------------------------------------------------------
    # X360 mapping (remote-controller JSON)
    # -------------------------------------------------------------------------

    def _handle_x360_input(self, data: dict) -> None:
        """
        Decode JSON controller state and forward it to the X360 emulator.
        """
        buttons = data.get("buttons", {})
        analog = data.get("analog", {})
        joystick = data.get("joystick", {})

        left_deadzone, right_deadzone = self.settings.get_deadzones()
        left_inv, right_inv = self.settings.get_joystick_invertion()
        button_inv = self.settings.get_button_invertion()

        lx_val = joystick.get("left_x", 128)
        ly_val = joystick.get("left_y", 128)
        rx_val = joystick.get("right_x", 128)
        ry_val = joystick.get("right_y", 128)

        ljx, ljy = self._apply_deadzone(lx_val, ly_val, left_deadzone, left_inv)
        rjx, rjy = self._apply_deadzone(rx_val, ry_val, right_deadzone, right_inv)

        a = buttons.get("A", False)
        b = buttons.get("B", False)
        x_ = buttons.get("X", False)
        y_ = buttons.get("Y", False)
        lb = buttons.get("LB", False)
        rb = buttons.get("RB", False)
        back = buttons.get("BACK", False)
        start = buttons.get("START", False)
        l3 = buttons.get("L3", False)
        r3 = buttons.get("R3", False)
        dpu = buttons.get("DPAD_UP", False)
        dpd = buttons.get("DPAD_DOWN", False)
        dpr = buttons.get("DPAD_RIGHT", False)
        dpl = buttons.get("DPAD_LEFT", False)

        rt = analog.get("R2", 0)
        lt = analog.get("L2", 0)

        a = self._apply_button_invertion(a, button_inv)
        b = self._apply_button_invertion(b, button_inv)
        x_ = self._apply_button_invertion(x_, button_inv)
        y_ = self._apply_button_invertion(y_, button_inv)
        lb = self._apply_button_invertion(lb, button_inv)
        rb = self._apply_button_invertion(rb, button_inv)
        back = self._apply_button_invertion(back, button_inv)
        start = self._apply_button_invertion(start, button_inv)
        l3 = self._apply_button_invertion(l3, button_inv)
        r3 = self._apply_button_invertion(r3, button_inv)

        binary, _, _, _, _, _, _ = controllerMonitor.monitor(
            a, b, y_, x_, start, back,
            r3, l3, dpu, dpd, dpr, dpl, rb, lb,
            rt, lt, ljx, ljy, rjx, rjy,
        )
        ok, func, _ = self.hotkey.get_hotkey(binary)
        self._maybe_do_hotkey(ok, func)

        self.emulator.update(
            ljx, ljy, rjx, rjy,
            a, x_, b, y_,
            rb, rt, lb, lt,
            dpu, dpd, dpr, dpl,
            back, start, l3, r3,
        )

    def shutdown(self) -> None:
        self.release_mouse_buttons()
        self._connected = False
        if hasattr(self.emulator, "shutdown"):
            try:
                self.emulator.shutdown()
            except Exception as exc:
                logger.exception("Failed to shut down Web Companion emulator for %s", self.uuid)
