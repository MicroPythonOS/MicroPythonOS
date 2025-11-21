CURRENT_OS_VERSION = "0.4.1"

# Unique string that defines the hardware, used by OSUpdate and the About app
_hardware_id = "missing-hardware-info"

def set_hardware_id(value):
    global _hardware_id
    _hardware_id = value

def get_hardware_id():
    return _hardware_id
