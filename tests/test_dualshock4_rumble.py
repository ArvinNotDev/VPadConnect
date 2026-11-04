import threading
from unittest import mock

from core.dualshock4_rumble import (
    DualShock4Rumble, build_usb_report, build_bt_report,
    dualshock4_bt_crc, xinput_to_dualshock4_intensity,
)


def test_ds4_rumble_report_layouts_and_crc():
    usb = build_usb_report(22, 201)
    assert len(usb) == 32
    assert usb[0] == 0x05 and usb[1] == 0x01
    assert usb[4:6] == bytes((201, 22))
    bt = build_bt_report(22, 201)
    assert len(bt) == 78 and bt[0] == 0x11 and bt[1] == 0xC0
    assert bt[3] == 0x01 and bt[6:8] == bytes((201, 22))
    assert int.from_bytes(bt[-4:], "little") == dualshock4_bt_crc(bt[:-4])


def test_ds4_rumble_scaling_and_usb_worker_stop():
    assert xinput_to_dualshock4_intensity(0) == 0
    assert xinput_to_dualshock4_intensity(65535) == 255
    writes, started = [], threading.Event()

    class FakeDevice:
        def open_path(self, path): pass
        def write(self, report):
            writes.append(bytes(report)); started.set(); return len(report)
        def close(self): pass

    with mock.patch("core.dualshock4_rumble.hid.device", return_value=FakeDevice()):
        rumble = DualShock4Rumble(b"ds4-usb", transport="USB")
        rumble.set_xinput_vibration(0x4000, 0xC000)
        assert started.wait(1.0)
        rumble.stop()
    assert len(writes) >= 2
    assert writes[0][4] == xinput_to_dualshock4_intensity(0xC000)
    assert writes[0][5] == xinput_to_dualshock4_intensity(0x4000)
    assert writes[-1][4:6] == b"\x00\x00"


def test_ds4_bluetooth_rumble_worker_uses_bt_crc_and_stops():
    writes, started = [], threading.Event()

    class FakeDevice:
        def open_path(self, path): pass
        def write(self, report):
            writes.append(bytes(report)); started.set(); return len(report)
        def close(self): pass

    with mock.patch("core.dualshock4_rumble.hid.device", return_value=FakeDevice()):
        rumble = DualShock4Rumble(b"ds4-bt", transport="Bluetooth")
        rumble.set_xinput_vibration(0x3000, 0xD000)
        assert started.wait(1.0)
        rumble.stop()
    assert len(writes) >= 2
    assert int.from_bytes(writes[0][-4:], "little") == dualshock4_bt_crc(writes[0][:-4])
    assert writes[-1][6:8] == b"\x00\x00"
