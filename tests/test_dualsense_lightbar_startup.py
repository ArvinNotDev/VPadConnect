import threading

import pytest

from core.dualsense_lightbar import (
    BATTERY_CRITICAL_COLOR,
    BATTERY_HIGH_COLOR,
    BATTERY_LOW_COLOR,
    BATTERY_MEDIUM_COLOR,
    CHARGING_LIGHTBAR_COLOR,
    DualSenseLightbar,
    resolve_lightbar_color,
)


def test_battery_lightbar_uses_clear_saturated_status_colors():
    settings = {
        "enabled": True,
        "color": "#8B5CF6",
        "battery_mode": True,
        "charging_indication": True,
    }

    assert resolve_lightbar_color(settings, (100, False))[0] == BATTERY_HIGH_COLOR
    assert resolve_lightbar_color(settings, (70, False))[0] == BATTERY_HIGH_COLOR
    assert resolve_lightbar_color(settings, (69, False))[0] == BATTERY_MEDIUM_COLOR
    assert resolve_lightbar_color(settings, (40, False))[0] == BATTERY_MEDIUM_COLOR
    assert resolve_lightbar_color(settings, (39, False))[0] == BATTERY_LOW_COLOR
    assert resolve_lightbar_color(settings, (20, False))[0] == BATTERY_LOW_COLOR
    assert resolve_lightbar_color(settings, (19, False))[0] == BATTERY_CRITICAL_COLOR
    assert resolve_lightbar_color(settings, (0, False))[0] == BATTERY_CRITICAL_COLOR
    assert resolve_lightbar_color(settings, (15, True))[0] == CHARGING_LIGHTBAR_COLOR


@pytest.mark.parametrize("failure_stage", ("open", "reset_write"))
def test_lightbar_retries_transient_startup_failures(monkeypatch, failure_stage):
    import core.dualsense_lightbar as lightbar_module

    open_attempts = 0
    reset_attempts = 0
    reports = []
    color_sent = threading.Event()

    class FakeDevice:
        def open_path(self, path):
            nonlocal open_attempts
            open_attempts += 1
            if failure_stage == "open" and open_attempts == 1:
                raise OSError("controller output interface is not ready")

        def write(self, report):
            nonlocal reset_attempts
            report = bytes(report)
            is_reset = report[41] == 0x02 and report[44] == 0x02
            if is_reset:
                reset_attempts += 1
                if failure_stage == "reset_write" and reset_attempts == 1:
                    raise OSError("controller rejected its first setup report")
            reports.append(report)
            if report[4] == 0x04:
                color_sent.set()
            return len(report)

        def close(self):
            pass

    monkeypatch.setattr(lightbar_module.hid, "device", FakeDevice)
    output = DualSenseLightbar(
        b"test-bluetooth-lightbar-startup",
        transport="Bluetooth",
    )
    try:
        output.set_color(BATTERY_HIGH_COLOR)
        assert color_sent.wait(timeout=3.0), "Lightbar color was not applied after retry"
    finally:
        output.stop()

    assert open_attempts >= 2
    assert reset_attempts >= 1
    assert len(reports) == 2
    assert reports[0][41] == 0x02
    assert reports[0][44] == 0x02
    assert reports[1][4] == 0x04
    assert reports[1][47:50] == bytes(BATTERY_HIGH_COLOR)
