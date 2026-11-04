import struct
import unittest

from core.dualsense_gyro import decode_dualsense_gyro, is_dualsense


class DualSenseGyroReportTests(unittest.TestCase):
    def test_decodes_usb_raw_gyro_axes(self):
        report = bytearray(64)
        report[0] = 0x01
        struct.pack_into("<hhh", report, 16, -1234, 2345, -30000)

        self.assertEqual(decode_dualsense_gyro(report), (-1234, 2345, -30000))

    def test_decodes_bluetooth_raw_gyro_axes(self):
        report = bytearray(78)
        report[0] = 0x31
        struct.pack_into("<hhh", report, 17, 123, -456, 789)

        self.assertEqual(decode_dualsense_gyro(report), (123, -456, 789))

    def test_rejects_unrecognized_or_short_reports(self):
        self.assertIsNone(decode_dualsense_gyro(b""))
        self.assertIsNone(decode_dualsense_gyro(bytes([0x02]) + bytes(64)))
        self.assertIsNone(decode_dualsense_gyro(bytes([0x01]) + bytes(20)))

    def test_matches_only_sony_dualsense_products(self):
        self.assertTrue(is_dualsense(0x054C, 0x0CE6))
        self.assertTrue(is_dualsense(0x054C, 0x0DF2))
        self.assertFalse(is_dualsense(0x054C, 0x05C4))
        self.assertFalse(is_dualsense(0x1234, 0x0CE6))


if __name__ == "__main__":
    unittest.main()
