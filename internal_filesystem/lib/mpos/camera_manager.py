"""Android-inspired CameraManager for MicroPythonOS.

Provides unified access to camera devices (back-facing, front-facing, external).
Follows singleton pattern with class method delegation.

Example usage:
    from mpos import CameraManager

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


class CameraManager:
    """
    Centralized camera device management service.
    Implements singleton pattern for unified camera access.
    
    Usage:
        from mpos import CameraManager
        
        # Register a camera
        CameraManager.add_camera(CameraManager.Camera(
            lens_facing=CameraManager.CameraCharacteristics.LENS_FACING_BACK,
            name="OV5640"
        ))
        
        # Get all cameras
        cameras = CameraManager.get_cameras()
    """
    
    # Expose inner classes as class attributes
    Camera = Camera
    CameraCharacteristics = CameraCharacteristics
    
    _instance = None
    _cameras = []  # Class-level camera list for singleton
    
    def __init__(self):
        """Initialize CameraManager singleton instance."""
        if CameraManager._instance:
            return
        CameraManager._instance = self
        
        self._initialized = False
        self.init()
    
    @classmethod
    def get(cls):
        """Get or create the singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def init(self):
        """Initialize CameraManager.
        
        Returns:
            bool: True if initialized successfully
        """
        self._initialized = True
        return True
    
    def is_available(self):
        """Check if CameraManager is initialized.

        Returns:
            bool: True if CameraManager is initialized
        """
        return self._initialized
    
    def add_camera(self, camera):
        """Register a camera device.

        Args:
            camera: Camera object to register

        Returns:
            bool: True if camera added successfully
        """
        if not isinstance(camera, Camera):
            print(f"[CameraManager] Error: add_camera() requires Camera object, got {type(camera)}")
            return False

        # Check if camera with same facing already exists
        for existing in CameraManager._cameras:
            if existing.lens_facing == camera.lens_facing:
                print(f"[CameraManager] Warning: Camera with facing {camera.lens_facing} already registered")
                # Still add it (allow multiple cameras with same facing)
        
        CameraManager._cameras.append(camera)
        print(f"[CameraManager] Registered camera: {camera}")
        return True
    
    def get_cameras(self):
        """Get list of all registered cameras.

        Returns:
            list: List of Camera objects (copy of internal list)
        """
        return CameraManager._cameras.copy() if CameraManager._cameras else []
    
    def get_camera_by_facing(self, lens_facing):
        """Get first camera with specified lens facing.

        Args:
            lens_facing: Camera orientation (LENS_FACING_BACK, LENS_FACING_FRONT, etc.)

        Returns:
            Camera object or None if not found
        """
        for camera in CameraManager._cameras:
            if camera.lens_facing == lens_facing:
                return camera
        return None
    
    def has_camera(self):
        """Check if any camera is registered.

        Returns:
            bool: True if at least one camera available
        """
        return len(CameraManager._cameras) > 0
    
    def get_camera_count(self):
        """Get number of registered cameras.

        Returns:
            int: Number of cameras
        """
        return len(CameraManager._cameras)


# ============================================================================
# Class method delegation (at module level)
# ============================================================================

_original_methods = {}
_methods_to_delegate = [
    'init', 'is_available', 'add_camera', 'get_cameras',
    'get_camera_by_facing', 'has_camera', 'get_camera_count'
]

for method_name in _methods_to_delegate:
    _original_methods[method_name] = getattr(CameraManager, method_name)

def _make_class_method(method_name):
    """Create a class method that delegates to the singleton instance."""
    original_method = _original_methods[method_name]
    
    @classmethod
    def class_method(cls, *args, **kwargs):
        instance = cls.get()
        return original_method(instance, *args, **kwargs)
    
    return class_method

for method_name in _methods_to_delegate:
    setattr(CameraManager, method_name, _make_class_method(method_name))


# Initialize on module load
CameraManager.init()
