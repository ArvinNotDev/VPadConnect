import configparser
import hashlib
import re
from pathlib import Path

from core.utils.paths import ensure_user_file, resolve_data_path


class SettingsManager:
    POLL_INTERVAL_MIN_MS = 1.0
    POLL_INTERVAL_MAX_MS = 1000.0

    def __init__(self, path="config/settings.conf"):
        self.path = resolve_data_path(path)
        self.config = configparser.ConfigParser()

        if not self.path.exists():
            default_config = ensure_user_file(
                "config/settings.conf",
                "config/settings.conf",
            )
            if default_config.exists():
                self.path = default_config
            else:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self.config["device"] = {
                    "poll_interval_ms": "1.0",
                    "auto_reconnect": "true",
                    "dpad_as_mouse": "true",
                    "left_stick_deadzone": "0.000000",
                    "right_stick_deadzone": "0.000000",
                    "right_stick_invert_x": "false",
                    "right_stick_invert_y": "false",
                    "left_stick_invert_x": "false",
                    "left_stick_invert_y": "true",
                    "mouse_mode": "false",
                    "mouse_sensitivity": "1.0",
                    "mouse_deadzone": "0.10",
                    "vibration_enabled": "true"
                }
                self.config["ui"] = {
                    "language": "eng",
                    "theme": "dark",
                    "reduced_motion": "false",
                }
                self.config["developer"] = {
                    "debug": "false",
                    "raw_hid_debug": "false",
                    "log_to_file": "false",
                    "log_file_path": "logs/mapper.log"
                }
                with self.path.open("w", encoding="utf-8") as f:
                    self.config.write(f)

        self.config.read(self.path)

    # -------- device --------
    def get_poll_interval_ms(self) -> float:
        """Return the HID polling sleep interval in milliseconds.

        ``polling_rate`` was the old, misleading name. Keep reading it as a
        compatibility fallback so existing settings and profiles continue to
        work, but normalize new writes to the explicit interval name.
        """
        try:
            if self.config.has_option("device", "poll_interval_ms"):
                value = self.config.getfloat("device", "poll_interval_ms")
            else:
                value = self.config.getfloat("device", "polling_rate", fallback=1.0)
        except (ValueError, TypeError):
            value = 1.0

        return max(self.POLL_INTERVAL_MIN_MS, min(self.POLL_INTERVAL_MAX_MS, float(value)))

    def set_poll_interval_ms(self, v: float):
        if not self.config.has_section("device"):
            self.config.add_section("device")
        value = max(self.POLL_INTERVAL_MIN_MS, min(self.POLL_INTERVAL_MAX_MS, float(v)))
        self.config.set("device", "poll_interval_ms", f"{value:.3f}")
        self.config.remove_option("device", "polling_rate")

    # Backward-compatible API for older callers.
    def get_polling_rate(self):
        return self.get_poll_interval_ms()

    def set_polling_rate(self, v: float):
        self.set_poll_interval_ms(v)

    def get_auto_reconnect(self):
        return self.config.getboolean("device", "auto_reconnect", fallback=True)

    def set_auto_reconnect(self, enabled: bool):
        if not self.config.has_section("device"):
            self.config.add_section("device")
        self.config.set("device", "auto_reconnect", "true" if enabled else "false")

    def get_dpad_as_mouse(self):
        return self.config.getboolean("device", "dpad_as_mouse", fallback=True)

    def set_dpad_as_mouse(self, enabled: bool):
        if not self.config.has_section("device"):
            self.config.add_section("device")
        self.config.set("device", "dpad_as_mouse", "true" if enabled else "false")

    def get_deadzones(self):
        left = self.config.getfloat("device", "left_stick_deadzone", fallback=0.1)
        right = self.config.getfloat("device", "right_stick_deadzone", fallback=0.1)
        left = max(0.0, min(1.0, left))
        right = max(0.0, min(1.0, right))
        return left, right

    def set_deadzones(self, left: float, right: float):
        if not self.config.has_section("device"):
            self.config.add_section("device")
        left = max(0.0, min(1.0, float(left)))
        right = max(0.0, min(1.0, float(right)))
        self.config.set("device", "left_stick_deadzone", f"{left:.6f}")
        self.config.set("device", "right_stick_deadzone", f"{right:.6f}")

    def get_joystick_invertion(self):
        left_x = self.config.getboolean("device", "left_stick_invert_x", fallback=False)
        left_y = self.config.getboolean("device", "left_stick_invert_y", fallback=False)
        right_x = self.config.getboolean("device", "right_stick_invert_x", fallback=False)
        right_y = self.config.getboolean("device", "right_stick_invert_y", fallback=False)
        return ((left_x, left_y), (right_x, right_y))
    
    def set_joystick_invertion(self, left: tuple, right: tuple):
        if not self.config.has_section("device"):
            self.config.add_section("device")
        self.config.set("device", "left_stick_invert_x", "true" if bool(left[0]) else "false")
        self.config.set("device", "left_stick_invert_y", "true" if bool(left[1]) else "false")
        self.config.set("device", "right_stick_invert_x", "true" if bool(right[0]) else "false")
        self.config.set("device", "right_stick_invert_y", "true" if bool(right[1]) else "false")

    def set_button_invertion(self, invert):
        if not self.config.has_section("device"):
            self.config.add_section("device")
        self.config.set("device", "invert_buttons", "true" if bool(invert) else "false")
    
    def get_button_invertion(self):
        return self.config.getboolean("device", "invert_buttons", fallback=False)

    def get_mouse_mode(self):
        return self.config.getboolean("device", "mouse_mode", fallback=False)
    
    def set_mouse_mode(self, enabled: bool):
        if not self.config.has_section("device"):
            self.config.add_section("device")
        self.config.set("device", "mouse_mode", "true" if enabled else "false")

    def get_mouse_sensitivity(self):
        return self.config.getfloat("device", "mouse_sensitivity", fallback=1.0)
    
    def set_mouse_sensitivity(self, sens: float):
        if not self.config.has_section("device"):
            self.config.add_section("device")
        self.config.set("device", "mouse_sensitivity", f"{float(sens):.6f}")

    def get_mouse_deadzone(self) -> float:
        value = self.config.getfloat("device", "mouse_deadzone", fallback=0.10)
        return max(0.0, min(0.50, value))

    def set_mouse_deadzone(self, deadzone: float) -> None:
        if not self.config.has_section("device"):
            self.config.add_section("device")
        value = max(0.0, min(0.50, float(deadzone)))
        self.config.set("device", "mouse_deadzone", f"{value:.3f}")

    def get_vibration_enabled(self):
        return self.config.getboolean("device", "vibration_enabled", fallback=True)

    def set_vibration_enabled(self, enabled: bool):
        if not self.config.has_section("device"):
            self.config.add_section("device")
        self.config.set("device", "vibration_enabled", "true" if enabled else "false")

    # -------- per-controller DualSense Lightbar --------
    @staticmethod
    def _lightbar_section(controller_id: str) -> str:
        digest = hashlib.sha256(str(controller_id).encode("utf-8")).hexdigest()[:20]
        return f"lightbar_{digest}"

    def has_controller_lightbar_settings(self, controller_id: str) -> bool:
        return self.config.has_section(self._lightbar_section(controller_id))

    def get_controller_lightbar_settings(self, controller_id: str) -> dict:
        section = self._lightbar_section(controller_id)
        if not self.config.has_section(section):
            return {
                "enabled": False,
                "color": "#8B5CF6",
                "battery_mode": False,
                "charging_indication": False,
            }

        color = self.config.get(section, "color", fallback="#8B5CF6").upper()
        if not re.fullmatch(r"#[0-9A-F]{6}", color):
            color = "#8B5CF6"
        return {
            "enabled": self.config.getboolean(section, "enabled", fallback=False),
            "color": color,
            "battery_mode": self.config.getboolean(
                section, "battery_mode", fallback=False
            ),
            "charging_indication": self.config.getboolean(
                section, "charging_indication", fallback=False
            ),
        }

    def set_controller_lightbar_settings(self, controller_id: str, settings: dict):
        section = self._lightbar_section(controller_id)
        if not self.config.has_section(section):
            self.config.add_section(section)

        color = str(settings.get("color", "#8B5CF6")).upper()
        if not re.fullmatch(r"#[0-9A-F]{6}", color):
            color = "#8B5CF6"
        self.config.set(section, "enabled", str(bool(settings.get("enabled", False))).lower())
        self.config.set(section, "color", color)
        self.config.set(
            section, "battery_mode", str(bool(settings.get("battery_mode", False))).lower()
        )
        self.config.set(
            section,
            "charging_indication",
            str(bool(settings.get("charging_indication", False))).lower(),
        )

    # -------- per-controller DualSense Gyro Steering --------
    @staticmethod
    def _gyro_section(controller_id: str) -> str:
        digest = hashlib.sha256(str(controller_id).encode("utf-8")).hexdigest()[:20]
        return f"gyro_{digest}"

    def get_controller_gyro_settings(self, controller_id: str) -> dict:
        section = self._gyro_section(controller_id)
        if not self.config.has_section(section):
            return {
                "enabled": False,
                "sensitivity": 1.0,
                "deadzone_degrees": 2.0,
                "center_gravity": None,
            }
        try:
            center = tuple(
                float(self.config.get(section, f"center_{axis}"))
                for axis in ("x", "y", "z")
            )
            if not all(-1.05 <= value <= 1.05 for value in center):
                center = None
        except (configparser.Error, ValueError):
            center = None
        return {
            "enabled": self.config.getboolean(section, "enabled", fallback=False),
            "sensitivity": max(
                0.25, min(4.0, self.config.getfloat(section, "sensitivity", fallback=1.0))
            ),
            "deadzone_degrees": max(
                0.0, min(15.0, self.config.getfloat(section, "deadzone_degrees", fallback=2.0))
            ),
            "center_gravity": center,
        }

    def set_controller_gyro_settings(self, controller_id: str, settings: dict) -> None:
        section = self._gyro_section(controller_id)
        if not self.config.has_section(section):
            self.config.add_section(section)
        self.config.set(section, "enabled", str(bool(settings.get("enabled", False))).lower())
        sensitivity = max(0.25, min(4.0, float(settings.get("sensitivity", 1.0))))
        deadzone = max(0.0, min(15.0, float(settings.get("deadzone_degrees", 2.0))))
        self.config.set(section, "sensitivity", f"{sensitivity:.3f}")
        self.config.set(section, "deadzone_degrees", f"{deadzone:.3f}")
        center = settings.get("center_gravity")
        if center is not None and len(center) == 3:
            for axis, value in zip(("x", "y", "z"), center):
                self.config.set(section, f"center_{axis}", f"{float(value):.6f}")
        elif self.config.has_option(section, "center_x"):
            for axis in ("x", "y", "z"):
                self.config.remove_option(section, f"center_{axis}")

    # -------- ui --------
    def get_ui_language(self):
        return self.config.get("ui", "language", fallback="eng")

    def set_ui_language(self, lang: str):
        if not self.config.has_section("ui"):
            self.config.add_section("ui")
        self.config.set("ui", "language", str(lang))

    def get_ui_theme(self):
        return self.config.get("ui", "theme", fallback="dark")

    def set_ui_theme(self, theme_name: str):
        if not self.config.has_section("ui"):
            self.config.add_section("ui")
        self.config.set("ui", "theme", str(theme_name))

    def get_ui_reduced_motion(self) -> bool:
        return self.config.getboolean("ui", "reduced_motion", fallback=False)

    def set_ui_reduced_motion(self, enabled: bool) -> None:
        if not self.config.has_section("ui"):
            self.config.add_section("ui")
        self.config.set("ui", "reduced_motion", "true" if enabled else "false")

    # -------- developer --------
    def get_developer_debug(self):
        return self.config.getboolean("developer", "debug", fallback=False)

    def set_developer_debug(self, enabled: bool):
        if not self.config.has_section("developer"):
            self.config.add_section("developer")
        self.config.set("developer", "debug", "true" if enabled else "false")

    def get_raw_hid_debug(self):
        return self.config.getboolean("developer", "raw_hid_debug", fallback=False)

    def set_raw_hid_debug(self, enabled: bool):
        if not self.config.has_section("developer"):
            self.config.add_section("developer")
        self.config.set("developer", "raw_hid_debug", "true" if enabled else "false")

    def get_log_to_file(self):
        return self.config.getboolean("developer", "log_to_file", fallback=False)

    def set_log_to_file(self, enabled: bool):
        if not self.config.has_section("developer"):
            self.config.add_section("developer")
        self.config.set("developer", "log_to_file", "true" if enabled else "false")

    def get_log_file_path(self):
        return self.config.get("developer", "log_file_path", fallback="logs/mapper.log")

    def set_log_file_path(self, path: str):
        if not self.config.has_section("developer"):
            self.config.add_section("developer")
        self.config.set("developer", "log_file_path", str(path))

    # -------- profile --------
    def get_active_profile(self) -> str:
        return self.config.get("profile", "active", fallback="")

    def set_active_profile(self, name: str):
        if not self.config.has_section("profile"):
            self.config.add_section("profile")
        self.config.set("profile", "active", str(name))

    # -------- save/load --------
    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as f:
            self.config.write(f)

    # -------- normalization (ensure all keys exist and sane) --------
    def normalize(self):
        """
        Ensure all expected keys exist with sane values.
        This lets the UI read everything once and know the file is consistent.
        """
        # Device defaults
        if not self.config.has_section("device"):
            self.config.add_section("device")
        # polling rate
        try:
            self.set_poll_interval_ms(self.get_poll_interval_ms())
        except Exception:
            self.set_poll_interval_ms(1.0)
        # auto reconnect
        try:
            _ = self.get_auto_reconnect()
        except Exception:
            self.set_auto_reconnect(True)
        # dpad as mouse
        try:
            _ = self.get_dpad_as_mouse()
        except Exception:
            self.set_dpad_as_mouse(True)
        # deadzones
        try:
            left, right = self.get_deadzones()
            self.set_deadzones(left, right)
        except Exception:
            self.set_deadzones(0.1, 0.1)
        # joystick inversion
        try:
            left_inv, right_inv = self.get_joystick_invertion()
            self.set_joystick_invertion(left_inv, right_inv)
        except Exception:
            self.set_joystick_invertion((False, True), (False, False))
        # button inversion
        try:
            inv_btn = self.get_button_invertion()
            self.set_button_invertion(inv_btn)
        except Exception:
            self.set_button_invertion(False)
        # mouse mode + sensitivity
        try:
            _ = self.get_mouse_mode()
        except Exception:
            self.set_mouse_mode(False)
        try:
            sens = self.get_mouse_sensitivity()
            self.set_mouse_sensitivity(sens)
        except Exception:
            self.set_mouse_sensitivity(1.0)
        try:
            self.set_mouse_deadzone(self.get_mouse_deadzone())
        except Exception:
            self.set_mouse_deadzone(0.10)
        try:
            self.set_vibration_enabled(self.get_vibration_enabled())
        except Exception:
            self.set_vibration_enabled(True)

        # UI defaults
        if not self.config.has_section("ui"):
            self.config.add_section("ui")
        try:
            lang = self.get_ui_language()
            self.set_ui_language(lang)
        except Exception:
            self.set_ui_language("eng")
        try:
            theme = self.get_ui_theme()
            self.set_ui_theme(theme)
        except Exception:
            self.set_ui_theme("dark")
        try:
            self.set_ui_reduced_motion(self.get_ui_reduced_motion())
        except Exception:
            self.set_ui_reduced_motion(False)

        # Developer defaults
        if not self.config.has_section("developer"):
            self.config.add_section("developer")
        try:
            dbg = self.get_developer_debug()
            self.set_developer_debug(dbg)
        except Exception:
            self.set_developer_debug(False)
        try:
            raw = self.get_raw_hid_debug()
            self.set_raw_hid_debug(raw)
        except Exception:
            self.set_raw_hid_debug(False)
        try:
            log = self.get_log_to_file()
            self.set_log_to_file(log)
        except Exception:
            self.set_log_to_file(False)
        try:
            path = self.get_log_file_path()
            self.set_log_file_path(path)
        except Exception:
            self.set_log_file_path("logs/mapper.log")

        # Write back normalized config
        self.save()
