"""Raw DualSense gyroscope input report decoding helpers."""

import struct


DUALSENSE_VENDOR_ID = 0x054C
DUALSENSE_PRODUCT_IDS = (0x0CE6, 0x0DF2)


def decode_dualsense_gyro(report: bytes) -> tuple[int, int, int] | None:
    """Return the three signed raw gyro values from a USB or Bluetooth report.

    Offsets follow the DualSense input report layout: USB report 0x01 has the
    common body starting after its report ID; Bluetooth report 0x31 has a
    two-byte sequence/tag header before that same body.
    """
    report = bytes(report)
    if not report:
        return None

    if report[0] == 0x01:
        gyro_offset = 16
    elif report[0] == 0x31:
        gyro_offset = 17
    else:
        return None

    if len(report) < gyro_offset + 6:
        return None
    return struct.unpack_from("<hhh", report, gyro_offset)


def is_dualsense(vendor_id, product_id) -> bool:
    try:
        return int(vendor_id) == DUALSENSE_VENDOR_ID and int(product_id) in DUALSENSE_PRODUCT_IDS
    except (TypeError, ValueError):
        return False
