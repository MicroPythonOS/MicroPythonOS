class DeviceInfo:

    hardware_id = "missing-hardware-info"

    @classmethod
    def set_hardware_id(cls, device_id):
        cls.hardware_id = device_id

    @classmethod
    def get_hardware_id(cls):
        return cls.hardware_id
