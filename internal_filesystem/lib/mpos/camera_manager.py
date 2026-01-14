"""Android-inspired CameraManager for MicroPythonOS.

Provides unified access to camera devices (back-facing, front-facing, external).
Follows module-level singleton pattern (like SensorManager, AudioFlinger).

Example usage:
    import mpos.camera_manager as CameraManager

    # In board init file:
    CameraManager.add_camera(CameraManager.Camera(
        lens_facing=CameraManager.CameraCharacteristics.LENS_FACING_BACK,
        name="OV5640",
        vendor="OmniVision"
    ))

    # In app:
    cam_list = CameraManager.get_cameras()
    if len(cam_list) > 0:
        print("we have a camera!")

MIT License
Copyright (c) 2024 MicroPythonOS contributors
"""

try:
    import _thread
    _lock = _thread.allocate_lock()
except ImportError:
    _lock = None


# Camera lens facing constants (matching Android Camera2 API)
class CameraCharacteristics:
    """Camera characteristics and constants."""
    LENS_FACING_BACK = 0       # Back-facing camera (primary)
    LENS_FACING_FRONT = 1      # Front-facing camera (selfie)
    LENS_FACING_EXTERNAL = 2   # External USB camera


class Camera:
    """Camera metadata (lightweight data class, Android-inspired).
    
    Represents a camera device with its characteristics.
    """

    def __init__(self, lens_facing, name=None, vendor=None, version=None):
        """Initialize camera metadata.

        Args:
            lens_facing: Camera orientation (LENS_FACING_BACK, LENS_FACING_FRONT, etc.)
            name: Human-readable camera name (e.g., "OV5640", "Front Camera")
            vendor: Camera vendor/manufacturer (e.g., "OmniVision")
            version: Driver version (default 1)
        """
        self.lens_facing = lens_facing
        self.name = name or "Camera"
        self.vendor = vendor or "Unknown"
        self.version = version or 1

    def __repr__(self):
        facing_names = {
            CameraCharacteristics.LENS_FACING_BACK: "BACK",
            CameraCharacteristics.LENS_FACING_FRONT: "FRONT",
            CameraCharacteristics.LENS_FACING_EXTERNAL: "EXTERNAL"
        }
        facing_str = facing_names.get(self.lens_facing, f"UNKNOWN({self.lens_facing})")
        return f"Camera({self.name}, facing={facing_str})"


# Module state
_initialized = False
_cameras = []  # List of Camera objects


def init():
    """Initialize CameraManager.
    
    Returns:
        bool: True if initialized successfully
    """
    global _initialized
    _initialized = True
    return True


def is_available():
    """Check if CameraManager is initialized.

    Returns:
        bool: True if CameraManager is initialized
    """
    return _initialized


def add_camera(camera):
    """Register a camera device.

    Args:
        camera: Camera object to register

    Returns:
        bool: True if camera added successfully
    """
    if not isinstance(camera, Camera):
        print(f"[CameraManager] Error: add_camera() requires Camera object, got {type(camera)}")
        return False

    if _lock:
        _lock.acquire()

    try:
        # Check if camera with same facing already exists
        for existing in _cameras:
            if existing.lens_facing == camera.lens_facing:
                print(f"[CameraManager] Warning: Camera with facing {camera.lens_facing} already registered")
                # Still add it (allow multiple cameras with same facing)
        
        _cameras.append(camera)
        print(f"[CameraManager] Registered camera: {camera}")
        return True
    finally:
        if _lock:
            _lock.release()


def get_cameras():
    """Get list of all registered cameras.

    Returns:
        list: List of Camera objects (copy of internal list)
    """
    if _lock:
        _lock.acquire()

    try:
        return _cameras.copy() if _cameras else []
    finally:
        if _lock:
            _lock.release()


def get_camera_by_facing(lens_facing):
    """Get first camera with specified lens facing.

    Args:
        lens_facing: Camera orientation (LENS_FACING_BACK, LENS_FACING_FRONT, etc.)

    Returns:
        Camera object or None if not found
    """
    if _lock:
        _lock.acquire()

    try:
        for camera in _cameras:
            if camera.lens_facing == lens_facing:
                return camera
        return None
    finally:
        if _lock:
            _lock.release()


def has_camera():
    """Check if any camera is registered.

    Returns:
        bool: True if at least one camera available
    """
    if _lock:
        _lock.acquire()

    try:
        return len(_cameras) > 0
    finally:
        if _lock:
            _lock.release()


def get_camera_count():
    """Get number of registered cameras.

    Returns:
        int: Number of cameras
    """
    if _lock:
        _lock.acquire()

    try:
        return len(_cameras)
    finally:
        if _lock:
            _lock.release()


# Initialize on module load
init()
