import vgamepad as vg
import time
import threading
from core.utils.controller_monitor import controllerMonitor
from core.utils.hotkeys import Hotkey
from core.utils.hotkey_commander import HotkeyCommander
from core.dualsense_rumble import DualSenseRumble
from core.dualshock4_rumble import DualShock4Rumble


media_functions = {
                    "volume up": "volume up",
                    "volume down": "volume down",
                    "play/pause media": "play/pause media",
                    "next track": "next track",
                    "previous track": "previous track",
                    "volume mute": "volume mute",
                  }
custom_commands = {}

class ListOfAllControllers:
    controllers_path = []
    controllers_name = []
    lock = threading.RLock()

class EmulateX360:
    def __init__(self, device_path, controller_name, hotkey, rumble_enabled=False,
                 rumble_transport=None, vibration_enabled=True,
                 rumble_controller_key=None, rumble_controller_type="Dualsense"):
        self.device_path = device_path
        self.controller_name = controller_name
        self.hotkey = hotkey
        self.hotkey_commander = HotkeyCommander(media_functions, custom_commands)
        self.is_monitoring = False
        self.could_instantiate = False
        self.rumble = None
        if rumble_enabled:
            rumble_class = DualShock4Rumble if rumble_controller_type == "Dualshock4" else DualSenseRumble
            self.rumble = rumble_class(
                device_path,
                transport=rumble_transport,
                controller_key=rumble_controller_key,
            )
        self._vibration_enabled = bool(vibration_enabled)

        # debounce state for hotkeys
        self._last_hotkey_func = None
        self._last_hotkey_time = 0.0
        self._hotkey_interval = 0.1  # 200 ms

        if not self.instantiate_vg():
            if self.rumble is not None:
                self.rumble.stop()
            raise RuntimeError(
                "ViGEmBus is unavailable. Install/start the ViGEmBus driver "
                "before starting XInput emulation."
            )

        with ListOfAllControllers.lock:
            ListOfAllControllers.controllers_path.append(device_path)
            ListOfAllControllers.controllers_name.append(controller_name)

    def instantiate_vg(self):
        try:
            self.v_x360 = vg.VX360Gamepad()
            if self.rumble is not None:
                try:
                    self.v_x360.register_notification(self._on_xinput_vibration)
                except Exception as exc:
                    print(f"[EmulateX360] Vibration callback unavailable: {exc}")
            self.could_instantiate = True
            return True
        except Exception as exc:
            print(f"[EmulateX360] Could not create virtual Xbox controller: {exc}")
            self.could_instantiate = False
            return False

    @property
    def supports_rumble(self):
        return self.rumble is not None

    @property
    def vibration_enabled(self):
        return self.supports_rumble and self._vibration_enabled

    def set_vibration_enabled(self, enabled):
        self._vibration_enabled = bool(enabled)
        if not self._vibration_enabled and self.rumble is not None:
            self.rumble.set_xinput_vibration(0, 0)

    def set_xinput_vibration(self, left_motor, right_motor):
        """Queue independent Xbox left/right motor values without blocking input."""
        if self.vibration_enabled:
            self.rumble.set_xinput_vibration(left_motor, right_motor)

    def reset_output(self) -> None:
        """Release every virtual control when switching output modes."""
        try:
            self.v_x360.reset()
            self.v_x360.update()
        except Exception as exc:
            print(f"[EmulateX360] Could not reset virtual controller: {exc}")

    def _on_xinput_vibration(self, client, target, large_motor, small_motor, led_number, user_data):
        # vgamepad exposes the ViGEm motor bytes (0..255).  Convert them to
        # the equivalent XInput 16-bit values before applying the common
        # scaling path, preserving both channels and their intensities.
        self.set_xinput_vibration(int(large_motor) * 257, int(small_motor) * 257)

    def _maybe_do_hotkey(self, ok, func):
        """
        Debounce / repeat logic:
        - Execute immediately on first detection of a hotkey.
        - If held (same func), re-execute every _hotkey_interval seconds.
        """
        if not ok or func is None:
            # reset if no valid hotkey
            self._last_hotkey_func = None
            return

        now = time.time()

        # new hotkey -> execute immediately and reset timer
        if func != self._last_hotkey_func:
            self._last_hotkey_func = func
            self._last_hotkey_time = now
            if func in media_functions.keys():
                self.hotkey_commander.do(func, False)
            return

        # same hotkey as last time -> check debounce timer
        if now - self._last_hotkey_time >= self._hotkey_interval:
            self._last_hotkey_time = now
            if func in media_functions.keys():
                self.hotkey_commander.do(func, False)

    def update(self, ljx, ljy, rjx, rjy, a=False, x=False, b=False, y=False,
               rb=False, rt=0, lb=False, lt=0, dpu=False, dpd=False, dpr=False, dpl=False,
               back=False, start=False, l3=False, r3=False):
        
        if self.is_monitoring:
            data = controllerMonitor.monitor(
                a, b, y, x,
                start, back,
                r3, l3,
                dpu, dpd, dpr, dpl,
                rb, lb,
                rt, lt,
                ljx, ljy,
                rjx, rjy
            )
            self._last_monitor = data
            return data
        
        data = controllerMonitor.monitor(
            a, b, y, x,
            start, back,
            r3, l3,
            dpu, dpd, dpr, dpl,
            rb, lb,
            rt, lt,
            ljx, ljy,
            rjx, rjy
        )
        self._last_monitor = data
        binary, rt, lt, jlx, jly, jrx, jry = data

        ok, func, msg = self.hotkey.get_hotkey(binary)

        # debounced hotkey execution
        self._maybe_do_hotkey(ok, func)

        # Joysticks
        self.v_x360.left_joystick(x_value=int(ljx), y_value=int(ljy))
        self.v_x360.right_joystick(x_value=int(rjx), y_value=int(rjy))

        # Triggers
        self.v_x360.left_trigger(value=int(lt))
        self.v_x360.right_trigger(value=int(rt))

        # Face Buttons
        self._press_release(a, vg.XUSB_BUTTON.XUSB_GAMEPAD_A)
        self._press_release(b, vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
        self._press_release(x, vg.XUSB_BUTTON.XUSB_GAMEPAD_X)
        self._press_release(y, vg.XUSB_BUTTON.XUSB_GAMEPAD_Y)
        
        # Shoulders
        self._press_release(lb, vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER)
        self._press_release(rb, vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER)

        # Menu / Stick Clicks
        self._press_release(back, vg.XUSB_BUTTON.XUSB_GAMEPAD_BACK)
        self._press_release(start, vg.XUSB_BUTTON.XUSB_GAMEPAD_START)
        self._press_release(l3, vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_THUMB)
        self._press_release(r3, vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_THUMB)

        # DPad simulation
        self._set_dpad(dpu, dpd, dpl, dpr)

        self.v_x360.update()

    def _press_release(self, pressed, button):
        if pressed:
            self.v_x360.press_button(button=button)
        else:
            self.v_x360.release_button(button=button)

    def _set_dpad(self, up, down, left, right):
        # Reset all D-pad buttons first
        self.v_x360.release_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP)
        self.v_x360.release_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN)
        self.v_x360.release_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_LEFT)
        self.v_x360.release_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT)

        # Press based on state (allowing diagonals)
        if up:
            self.v_x360.press_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP)
        if down:
            self.v_x360.press_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN)
        if left:
            self.v_x360.press_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_LEFT)
        if right:
            self.v_x360.press_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT)

    def shutdown(self):
        if self.rumble is not None:
            self.rumble.stop()

        try:
            virtual = getattr(self, "v_x360", None)
            if virtual is not None:
                unregister = getattr(virtual, "unregister_notification", None)
                if unregister is not None:
                    unregister()
                virtual.reset()
                virtual.update()
        except Exception as e:
            print(f"[EmulateX360] Error on shutdown: {e}")

        # Remove from tracking lists
        try:
            with ListOfAllControllers.lock:
                idx = ListOfAllControllers.controllers_path.index(self.device_path)
                ListOfAllControllers.controllers_path.pop(idx)
                if idx < len(ListOfAllControllers.controllers_name):
                    ListOfAllControllers.controllers_name.pop(idx)
        except ValueError:
            pass
        
class EmulateKeyboard:
    pass
