from core.controller import (
    is_preferred_sony_gamepad_interface,
    resolve_sony_input_report_index,
)


def test_wired_sony_controllers_select_only_the_gamepad_hid_collection():
    base = {
        "vendor_id": 0x054C,
        "product_id": 0x0CE6,
        "bus_type": 1,
    }

    assert is_preferred_sony_gamepad_interface(
        {**base, "usage_page": 0x01, "usage": 0x05}
    )
    assert not is_preferred_sony_gamepad_interface(
        {**base, "usage_page": 0xFF00, "usage": 0x01}
    )
    assert not is_preferred_sony_gamepad_interface(
        {
            **base,
            "product_id": 0x05C4,
            "usage_page": 0x09,
            "usage": 0x01,
        }
    )


def test_bluetooth_and_unknown_usb_collection_metadata_keep_existing_selection():
    bluetooth = {
        "vendor_id": 0x054C,
        "product_id": 0x09CC,
        "transport": 2,
        "usage_page": 0xFF00,
        "usage": 0x01,
    }
    metadata_missing = {
        "vendor_id": 0x054C,
        "product_id": 0x0DF2,
        "transport": 1,
    }
    interface_fallback_usb = {
        "vendor_id": 0x054C,
        "product_id": 0x0CE6,
        "interface_number": 0,
        "usage_page": 0x01,
        "usage": 0x05,
    }
    interface_fallback_bt = {
        "vendor_id": 0x054C,
        "product_id": 0x0CE6,
        "interface_number": -1,
        "usage_page": 0xFF00,
        "usage": 0x01,
    }

    assert is_preferred_sony_gamepad_interface(bluetooth)
    assert is_preferred_sony_gamepad_interface(metadata_missing)
    assert is_preferred_sony_gamepad_interface(interface_fallback_usb)
    assert is_preferred_sony_gamepad_interface(interface_fallback_bt)


def test_dualsense_usb_input_fields_use_usb_offsets():
    usb_report = bytes([0x01]) + bytes(63)

    assert resolve_sony_input_report_index("Dualsense", 2, usb_report, 1) == 1
    assert resolve_sony_input_report_index("Dualsense", 3, usb_report, 1) == 2
    assert resolve_sony_input_report_index("Dualsense", 6, usb_report, 1) == 5
    assert resolve_sony_input_report_index("Dualsense", 9, usb_report, 1) == 8
    assert resolve_sony_input_report_index("Dualsense", 10, usb_report, 1) == 9
    assert resolve_sony_input_report_index("Dualsense", 54, usb_report, 1) == 53


def test_dualsense_bluetooth_input_offsets_remain_unchanged():
    bluetooth_report = bytes([0x31]) + bytes(77)

    # Report ID remains authoritative even if USB transport metadata is stale.
    assert resolve_sony_input_report_index("Dualsense", 2, bluetooth_report, 1) == 2
    assert resolve_sony_input_report_index("Dualsense", 9, bluetooth_report, 1) == 9
    assert resolve_sony_input_report_index("Dualsense", 54, bluetooth_report, 1) == 54


def test_transport_fallback_and_dualshock4_offsets_remain_unchanged():
    assert resolve_sony_input_report_index("Dualsense", 2, None, 1) == 1
    usb_report = bytes([0x01]) + bytes(63)
    bluetooth_report = bytes([0x11]) + bytes(77)

    # The DualShock 4 profile already matches its native USB report layout.
    # Its Bluetooth input path is deliberately not altered in this fix.
    assert resolve_sony_input_report_index("Dualshock4", 1, usb_report, 1) == 1
    assert resolve_sony_input_report_index("Dualshock4", 5, usb_report, 1) == 5
    assert resolve_sony_input_report_index("Dualshock4", 1, bluetooth_report, 2) == 1
