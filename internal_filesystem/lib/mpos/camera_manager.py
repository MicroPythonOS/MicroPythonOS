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

    def __init__(self, lens_facing, name=None, vendor=None, version=None, init=None, deinit=None, capture=None, apply_settings=None, rotation_degrees=0):
        """Initialize camera metadata.

        Args:
            lens_facing: Camera orientation (LENS_FACING_BACK, LENS_FACING_FRONT, etc.)
            name: Human-readable camera name (e.g., "OV5640", "Front Camera")
            vendor: Camera vendor/manufacturer (e.g., "OmniVision")
            version: Driver version (default 1)
            rotation_degrees: how many degrees the camera is rotated clockwise
        """
        self.lens_facing = lens_facing
        self.name = name or "Camera"
        self.vendor = vendor or "Unknown"
        self.version = version or 1
        self.init_function = init
        self.deinit_function = deinit
        self.capture_function = capture
        self.apply_settings_function = apply_settings
        self.rotation_degrees = rotation_degrees

    def __repr__(self):
        facing_names = {
            CameraCharacteristics.LENS_FACING_BACK: "BACK",
            CameraCharacteristics.LENS_FACING_FRONT: "FRONT",
            CameraCharacteristics.LENS_FACING_EXTERNAL: "EXTERNAL"
        }
        facing_str = facing_names.get(self.lens_facing, f"UNKNOWN({self.lens_facing})")
        return f"Camera({self.name}, facing={facing_str})"

    def init(self, width, height, colormode):
        if self.init_function:
            return self.init_function(width, height, colormode)

    def deinit(self, cam_obj=None):
        if self.deinit_function:
            return self.deinit_function(cam_obj)

    def capture(self, cam_obj, colormode=None):
        if self.capture_function:
            return self.capture_function(cam_obj, colormode)

    def apply_settings(self, cam_obj, prefs):
        if self.apply_settings_function:
            return self.apply_settings_function(cam_obj, prefs)

    def get_rotation_degrees(self):
        return self.rotation_degrees


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

    @staticmethod
    def resolution_to_framesize(width, height):
        """Map resolution (width, height) to FrameSize enum.
        
        Args:
            width: Image width in pixels
            height: Image height in pixels
            
        Returns:
            FrameSize enum value corresponding to the resolution, or R240X240 as default
        """
        try:
            from camera import FrameSize
        except ImportError:
            print("Warning: camera module not available")
            return None
        
        # Format: (width, height): FrameSize
        resolution_map = {
            (96, 96): FrameSize.R96X96,
            (160, 120): FrameSize.QQVGA,
            (128, 128): FrameSize.R128X128,
            (176, 144): FrameSize.QCIF,
            (240, 176): FrameSize.HQVGA,
            (240, 240): FrameSize.R240X240,
            (320, 240): FrameSize.QVGA,
            (320, 320): FrameSize.R320X320,
            (400, 296): FrameSize.CIF,
            (480, 320): FrameSize.HVGA,
            (480, 480): FrameSize.R480X480,
            (640, 480): FrameSize.VGA,
            (640, 640): FrameSize.R640X640,
            (720, 720): FrameSize.R720X720,
            (800, 600): FrameSize.SVGA,
            (800, 800): FrameSize.R800X800,
            (1024, 768): FrameSize.XGA,
            (960, 960): FrameSize.R960X960,
            (1280, 720): FrameSize.HD,
            (1024, 1024): FrameSize.R1024X1024,
            # These are disabled in camera_settings.py because they use a lot of RAM:
            (1280, 1024): FrameSize.SXGA,
            (1280, 1280): FrameSize.R1280X1280,
            (1600, 1200): FrameSize.UXGA,
            (1920, 1080): FrameSize.FHD,
        }
        
        return resolution_map.get((width, height), FrameSize.R240X240)

    @staticmethod
    def ov_apply_camera_settings(cam, prefs):
        if not cam or not prefs:
            print("ov_apply_camera_settings: Skipping because invalid prefs or cam object")
            return
    
        try:
            # Basic image adjustments
            brightness = prefs.get_int("brightness")
            cam.set_brightness(brightness)
    
            contrast = prefs.get_int("contrast")
            cam.set_contrast(contrast)
    
            saturation = prefs.get_int("saturation")
            cam.set_saturation(saturation)

            # Orientation
            hmirror = prefs.get_bool("hmirror")
            cam.set_hmirror(hmirror)

            vflip = prefs.get_bool("vflip")
            cam.set_vflip(vflip)

            # Special effect
            special_effect = prefs.get_int("special_effect")
            cam.set_special_effect(special_effect)

            # Exposure control (apply master switch first, then manual value)
            exposure_ctrl = prefs.get_bool("exposure_ctrl")
            cam.set_exposure_ctrl(exposure_ctrl)

            if not exposure_ctrl:
                aec_value = prefs.get_int("aec_value")
                cam.set_aec_value(aec_value)

            # Mode-specific default comes from constructor
            ae_level = prefs.get_int("ae_level")
            cam.set_ae_level(ae_level)

            aec2 = prefs.get_bool("aec2")
            cam.set_aec2(aec2)
    
            # Gain control (apply master switch first, then manual value)
            gain_ctrl = prefs.get_bool("gain_ctrl")
            cam.set_gain_ctrl(gain_ctrl)

            if not gain_ctrl:
                agc_gain = prefs.get_int("agc_gain")
                cam.set_agc_gain(agc_gain)

            gainceiling = prefs.get_int("gainceiling")
            cam.set_gainceiling(gainceiling)

            # White balance (apply master switch first, then mode)
            whitebal = prefs.get_bool("whitebal")
            cam.set_whitebal(whitebal)

            if not whitebal:
                wb_mode = prefs.get_int("wb_mode")
                cam.set_wb_mode(wb_mode)

            awb_gain = prefs.get_bool("awb_gain")
            cam.set_awb_gain(awb_gain)
    
            # Sensor-specific settings (try/except for unsupported sensors)
            try:
                sharpness = prefs.get_int("sharpness")
                cam.set_sharpness(sharpness)
            except:
                pass  # Not supported on OV2640?

            try:
                denoise = prefs.get_int("denoise")
                cam.set_denoise(denoise)
            except:
                pass  # Not supported on OV2640?

            # Advanced corrections
            colorbar = prefs.get_bool("colorbar")
            cam.set_colorbar(colorbar)

            dcw = prefs.get_bool("dcw")
            cam.set_dcw(dcw)

            bpc = prefs.get_bool("bpc")
            cam.set_bpc(bpc)

            wpc = prefs.get_bool("wpc")
            cam.set_wpc(wpc)

            # Mode-specific default comes from constructor
            raw_gma = prefs.get_bool("raw_gma")
            print(f"applying raw_gma: {raw_gma}")
            cam.set_raw_gma(raw_gma)

            lenc = prefs.get_bool("lenc")
            cam.set_lenc(lenc)
    
            # JPEG quality (only relevant for JPEG format)
            #try:
            #    quality = prefs.get_int("quality", 85)
            #    cam.set_quality(quality)
            #except:
            #    pass  # Not in JPEG mode
    
            print("Camera settings applied successfully")
    
        except Exception as e:
            print(f"Error applying camera settings: {e}")


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
