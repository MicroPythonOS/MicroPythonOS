"""
DeviceInfo - Device hardware information
"""


class DeviceInfo:
    """Device hardware information."""

    hardware_id = "missing-hardware-info"

    @classmethod
    def set_hardware_id(cls, device_id):
        """
        Set the device/hardware identifier (called during boot).

        Args:
            device_id: The hardware identifier string
        """
        cls.hardware_id = device_id

    @classmethod
    def get_hardware_id(cls):
        """
        Get the hardware identifier.

        Returns:
            str: The hardware identifier
        """
        return cls.hardware_id
