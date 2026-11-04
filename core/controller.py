import re


_BLUETOOTH_ADDRESS = re.compile(
    r"(?i)(?:^|[^0-9a-f])([0-9a-f]{2}(?:[:-][0-9a-f]{2}){5})(?:$|[^0-9a-f])"
)


def stable_controller_id(vendor_id, product_id, device_path, serial_number=None):
    """Prefer a device serial/Bluetooth address; use the HID path as fallback."""
    try:
        vendor = int(vendor_id, 0) if isinstance(vendor_id, str) else int(vendor_id)
        product = int(product_id, 0) if isinstance(product_id, str) else int(product_id)
    except (TypeError, ValueError):
        vendor, product = 0, 0

    serial = (
        serial_number.decode("utf-8", errors="ignore")
        if isinstance(serial_number, bytes)
        else str(serial_number or "")
    ).strip().lower()
    path = (
        device_path.decode("utf-8", errors="ignore")
        if isinstance(device_path, bytes)
        else str(device_path or "")
    )
    address = _BLUETOOTH_ADDRESS.search(path)
    if serial:
        identity = f"serial:{serial}"
    elif address:
        identity = f"address:{address.group(1).replace('-', ':').lower()}"
    else:
        identity = f"path:{path.lower()}"
    return f"{vendor:04x}:{product:04x}:{identity}"



def _device_number(value):
    """Parse HID enumeration numbers represented as ints or numeric strings."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value, 0) if isinstance(value, str) else int(value)
    except (TypeError, ValueError):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None


def is_preferred_sony_gamepad_interface(device_info):
    """Reject non-gamepad HID collections for wired Sony controllers on USB.

    Windows can expose separate top-level HID collections for one physical
    controller. Only the Generic Desktop / Game Pad collection carries the
    input report consumed by the mapper. Bluetooth and HIDAPI backends without
    collection metadata keep the existing selection path.
    """
    if not isinstance(device_info, dict):
        return True

    vendor_id = _device_number(device_info.get("vendor_id"))
    product_id = _device_number(device_info.get("product_id"))
    if vendor_id != 0x054C or product_id not in (0x05C4, 0x09CC, 0x0CE6, 0x0DF2):
        return True

    transport = device_info.get("transport")
    if transport in (None, "", 0, "0"):
        transport = device_info.get("bus_type")
    transport_text = str(transport or "").strip().upper()
    if transport == 1 or transport_text == "1" or "USB" in transport_text:
        is_usb = True
    elif transport == 2 or transport_text == "2" or "BLUETOOTH" in transport_text or transport_text in {"BT", "BTH"}:
        is_usb = False
    else:
        # HIDAPI commonly marks Bluetooth with interface_number=-1; USB
        # interfaces normally have a non-negative interface number.
        interface_number = _device_number(device_info.get("interface_number"))
        if interface_number is None:
            return True
        is_usb = interface_number != -1

    if not is_usb:
        return True

    usage_page = _device_number(device_info.get("usage_page"))
    usage = _device_number(device_info.get("usage"))
    if usage_page is None or usage is None:
        # Some HIDAPI backends do not expose top-level collection metadata.
        return True

    return usage_page == 0x01 and usage == 0x05


def resolve_sony_input_report_index(controller_type, configured_index, report=None, transport=None):
    """Resolve profile indexes against the native Sony USB/Bluetooth layouts."""
    if configured_index is None or controller_type not in ("Dualsense", "Dualshock4"):
        return configured_index
    try:
        index = int(configured_index)
    except (TypeError, ValueError):
        return configured_index

    report_id = report[0] if report else None
    transport_text = str(transport or "").strip().upper()
    is_bluetooth = (
        transport == 2 or str(transport) == "2"
        or "BLUETOOTH" in transport_text or transport_text in {"BT", "BTH"}
    )
    if controller_type == "Dualsense":
        if report_id == 0x01:
            return max(0, index - 1)
        if report_id == 0x31:
            return index
        is_usb = transport == 1 or str(transport) == "1" or "USB" in transport_text
        return max(0, index - 1) if is_usb else index

    # DS4 full BT 0x11 adds two reserved bytes after report ID.
    # USB 0x01 and minimal Bluetooth 0x01 use the USB profile offsets.
    if report_id == 0x11:
        return index + 2
    if report_id == 0x01:
        return index
    return index + 2 if is_bluetooth else index


def interpret_dualshock4_battery(status_byte):
    """Decode DS4 capacity using the cable-state-dependent status nibble."""
    value = int(status_byte) & 0xFF
    level = value & 0x0F
    if value & 0x10:
        if level <= 10:
            return min(100, level * 10 + 5), True
        if level == 11:
            return 100, False
        return None, False
    return (level * 10 + 5, False) if level <= 9 else (100, False)


class PlayerType:
    def __init__(self, type: str = None):
        self.type = type if type else "CPU"

    def __repr__(self):
        return self.type

class Controller:
    """
    Represents a physical controller.
    The live HID path identifies an open connection; stable_id is for saved
    per-controller preferences across reconnects when HIDAPI exposes a serial.
    """

    NUMBER_OF_CONTROLLERS = 0

    def __new__(cls, *args, **kwargs):
        cls.NUMBER_OF_CONTROLLERS += 1
        return super().__new__(cls)

    def __init__(
        self,
        vendor_id,
        product_id,
        device_path,
        name=None,
        transport=None,
        serial_number=None,
        stable_id=None,
    ):
        self.vendor_id = vendor_id
        self.product_id = product_id
        self.device_path = device_path
        self.name = name or f"Controller-{Controller.NUMBER_OF_CONTROLLERS}"
        self.transport = transport
        self.serial_number = serial_number
        self.sensor_calibration = None
        self.stable_id = stable_id or stable_controller_id(
            vendor_id, product_id, device_path, serial_number
        )

    @property
    def unique_id(self):
        return self.device_path

    def __repr__(self):
        return f"<Controller {self.name} ({self.vendor_id:04X}:{self.product_id:04X})>"
