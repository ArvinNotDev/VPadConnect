from PySide6.QtCore import QObject, QThread, Signal
import hid
import threading


class HIDWorker(QObject):
    data_received = Signal(bytes)
    sensor_calibration = Signal(bytes)
    error = Signal(str)
    finished = Signal()

    def __init__(self, controller, poll_interval=0.008):
        super().__init__()
        self.controller = controller
        # Never allow a zero/negative delay to turn the HID loop into a busy
        # loop. One millisecond is fast enough for responsive input while
        # keeping CPU usage bounded.
        try:
            self.poll_interval = max(0.001, float(poll_interval))
        except (TypeError, ValueError):
            self.poll_interval = 0.001
        self._running = True
        self._stop_event = threading.Event()

    def stop(self):
        self._running = False
        self._stop_event.set()

    def _is_dualsense(self) -> bool:
        """Return True only for the supported Sony DualSense (PS5) HID device."""
        return (
            self.controller.vendor_id == 0x054C
            and self.controller.product_id in (0x0CE6, 0x0DF2)
        )

    def run(self):
        ds = hid.device()
        try:
            ds.open_path(self.controller.device_path)
            # for rid in [0x05, 0x09, 0x20]:
            #     try:
            #         data = ds.get_feature_report(rid, 65)
            #         print(hex(rid), data)
            #     except Exception as e:
            #         print("fail", hex(rid), e)
            # This report enables additional reports (battery, etc.) on the
            # DualSense. Sending it to a DualShock 4 can leave the controller
            # stuck in its yellow light state, so keep it strictly PS5-only.
            if self._is_dualsense():
                calibration = ds.get_feature_report(0x05, 65)
                if calibration:
                    calibration = bytes(calibration)
                    self.controller.sensor_calibration = calibration
                    self.sensor_calibration.emit(calibration)
        except Exception as e:
            self.error.emit(f"Failed to open {self.controller}: {e}")
            self.finished.emit()
            return

        try:
            idle_cycles = 0
            read_timeout_ms = max(1, int(round(self.poll_interval * 1000.0)))
            while self._running and not self._stop_event.is_set():
                try:
                    try:
                        # Let hidapi block while idle. Once a report arrives,
                        # immediately return to read again; adding a sleep
                        # after an active report creates avoidable input lag.
                        report = ds.read(65, timeout_ms=read_timeout_ms)
                        # for i, r in enumerate(report):
                        #     if not r:
                        #         report = report[:i] + report[i+1:]
                        # print(report)
                    except TypeError:
                        report = ds.read(65, timeout=1)

                    if report:
                        idle_cycles = 0
                        self.data_received.emit(bytes(report))
                        continue

                    # Some hidapi backends can return immediately with an
                    # empty report. Back off only after repeated idle reads so
                    # that such a backend cannot spin at 100% CPU, while the
                    # active input path remains sleep-free.
                    idle_cycles = min(idle_cycles + 1, 4)
                    if idle_cycles >= 2:
                        self._stop_event.wait(
                            min(0.003, self.poll_interval * (idle_cycles - 1))
                        )

                except Exception as e:
                    self.error.emit(str(e))
                    break

        finally:
            ds.close()
            self.finished.emit()
