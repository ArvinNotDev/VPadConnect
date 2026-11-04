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
