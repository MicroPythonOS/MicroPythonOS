
import unittest
import sys
import os

import mpos.camera_manager as CameraManager

class TestCameraClass(unittest.TestCase):
    """Test Camera class functionality."""

    def test_camera_creation_with_all_params(self):
        """Test creating a camera with all parameters."""
        cam = CameraManager.Camera(
            lens_facing=CameraManager.CameraCharacteristics.LENS_FACING_BACK,
            name="OV5640",
            vendor="OmniVision",
            version=2
        )
        self.assertEqual(cam.lens_facing, CameraManager.CameraCharacteristics.LENS_FACING_BACK)
        self.assertEqual(cam.name, "OV5640")
        self.assertEqual(cam.vendor, "OmniVision")
        self.assertEqual(cam.version, 2)

    def test_camera_creation_with_defaults(self):
        """Test creating a camera with default parameters."""
        cam = CameraManager.Camera(
            lens_facing=CameraManager.CameraCharacteristics.LENS_FACING_FRONT
        )
        self.assertEqual(cam.lens_facing, CameraManager.CameraCharacteristics.LENS_FACING_FRONT)
        self.assertEqual(cam.name, "Camera")
        self.assertEqual(cam.vendor, "Unknown")
        self.assertEqual(cam.version, 1)

    def test_camera_repr(self):
        """Test Camera __repr__ method."""
        cam = CameraManager.Camera(
            lens_facing=CameraManager.CameraCharacteristics.LENS_FACING_BACK,
            name="TestCam"
        )
        repr_str = repr(cam)
        self.assertIn("TestCam", repr_str)
        self.assertIn("BACK", repr_str)

    def test_camera_repr_front(self):
        """Test Camera __repr__ with front-facing camera."""
        cam = CameraManager.Camera(
            lens_facing=CameraManager.CameraCharacteristics.LENS_FACING_FRONT,
            name="FrontCam"
        )
        repr_str = repr(cam)
        self.assertIn("FrontCam", repr_str)
        self.assertIn("FRONT", repr_str)

    def test_camera_repr_external(self):
        """Test Camera __repr__ with external camera."""
        cam = CameraManager.Camera(
            lens_facing=CameraManager.CameraCharacteristics.LENS_FACING_EXTERNAL,
            name="USBCam"
        )
        repr_str = repr(cam)
        self.assertIn("USBCam", repr_str)
        self.assertIn("EXTERNAL", repr_str)


class TestCameraCharacteristics(unittest.TestCase):
    """Test CameraCharacteristics constants."""

    def test_lens_facing_constants(self):
        """Test that lens facing constants are defined."""
        self.assertEqual(CameraManager.CameraCharacteristics.LENS_FACING_BACK, 0)
        self.assertEqual(CameraManager.CameraCharacteristics.LENS_FACING_FRONT, 1)
        self.assertEqual(CameraManager.CameraCharacteristics.LENS_FACING_EXTERNAL, 2)

    def test_constants_are_unique(self):
        """Test that all constants are unique."""
        constants = [
            CameraManager.CameraCharacteristics.LENS_FACING_BACK,
            CameraManager.CameraCharacteristics.LENS_FACING_FRONT,
            CameraManager.CameraCharacteristics.LENS_FACING_EXTERNAL
        ]
        self.assertEqual(len(constants), len(set(constants)))


class TestCameraManagerFunctionality(unittest.TestCase):
    """Test CameraManager core functionality."""

    def setUp(self):
        """Clear cameras before each test."""
        # Reset the module state
        CameraManager._cameras = []

    def tearDown(self):
        """Clean up after each test."""
        CameraManager._cameras = []

    def test_is_available(self):
        """Test is_available() returns True after initialization."""
        self.assertTrue(CameraManager.is_available())

    def test_add_camera_single(self):
        """Test adding a single camera."""
        cam = CameraManager.Camera(
            lens_facing=CameraManager.CameraCharacteristics.LENS_FACING_BACK,
            name="TestCam"
        )
        result = CameraManager.add_camera(cam)
        self.assertTrue(result)
        self.assertEqual(CameraManager.get_camera_count(), 1)

    def test_add_camera_multiple(self):
        """Test adding multiple cameras."""
        back_cam = CameraManager.Camera(
            lens_facing=CameraManager.CameraCharacteristics.LENS_FACING_BACK,
            name="BackCam"
        )
        front_cam = CameraManager.Camera(
            lens_facing=CameraManager.CameraCharacteristics.LENS_FACING_FRONT,
            name="FrontCam"
        )
        
        CameraManager.add_camera(back_cam)
        CameraManager.add_camera(front_cam)
        
        self.assertEqual(CameraManager.get_camera_count(), 2)

    def test_add_camera_invalid_type(self):
        """Test adding invalid object as camera."""
        result = CameraManager.add_camera("not a camera")
        self.assertFalse(result)
        self.assertEqual(CameraManager.get_camera_count(), 0)

    def test_get_cameras_empty(self):
        """Test getting cameras when none registered."""
        cameras = CameraManager.get_cameras()
        self.assertEqual(len(cameras), 0)
        self.assertIsInstance(cameras, list)

    def test_get_cameras_returns_copy(self):
        """Test that get_cameras() returns a copy, not reference."""
        cam = CameraManager.Camera(
            lens_facing=CameraManager.CameraCharacteristics.LENS_FACING_BACK
        )
        CameraManager.add_camera(cam)
        
        cameras1 = CameraManager.get_cameras()
        cameras2 = CameraManager.get_cameras()
        
        # Should be equal but not the same object
        self.assertEqual(len(cameras1), len(cameras2))
        self.assertIsNot(cameras1, cameras2)

    def test_get_cameras_multiple(self):
        """Test getting multiple cameras."""
        back_cam = CameraManager.Camera(
            lens_facing=CameraManager.CameraCharacteristics.LENS_FACING_BACK,
            name="BackCam"
        )
        front_cam = CameraManager.Camera(
            lens_facing=CameraManager.CameraCharacteristics.LENS_FACING_FRONT,
            name="FrontCam"
        )
        
        CameraManager.add_camera(back_cam)
        CameraManager.add_camera(front_cam)
        
        cameras = CameraManager.get_cameras()
        self.assertEqual(len(cameras), 2)
        names = [c.name for c in cameras]
        self.assertIn("BackCam", names)
        self.assertIn("FrontCam", names)

    def test_get_camera_by_facing_back(self):
        """Test getting back-facing camera."""
        back_cam = CameraManager.Camera(
            lens_facing=CameraManager.CameraCharacteristics.LENS_FACING_BACK,
            name="BackCam"
        )
        CameraManager.add_camera(back_cam)
        
        found = CameraManager.get_camera_by_facing(
            CameraManager.CameraCharacteristics.LENS_FACING_BACK
        )
        self.assertIsNotNone(found)
        self.assertEqual(found.name, "BackCam")

    def test_get_camera_by_facing_front(self):
        """Test getting front-facing camera."""
        front_cam = CameraManager.Camera(
            lens_facing=CameraManager.CameraCharacteristics.LENS_FACING_FRONT,
            name="FrontCam"
        )
        CameraManager.add_camera(front_cam)
        
        found = CameraManager.get_camera_by_facing(
            CameraManager.CameraCharacteristics.LENS_FACING_FRONT
        )
        self.assertIsNotNone(found)
        self.assertEqual(found.name, "FrontCam")

    def test_get_camera_by_facing_not_found(self):
        """Test getting camera that doesn't exist."""
        back_cam = CameraManager.Camera(
            lens_facing=CameraManager.CameraCharacteristics.LENS_FACING_BACK
        )
        CameraManager.add_camera(back_cam)
        
        found = CameraManager.get_camera_by_facing(
            CameraManager.CameraCharacteristics.LENS_FACING_FRONT
        )
        self.assertIsNone(found)

    def test_get_camera_by_facing_returns_first(self):
        """Test that get_camera_by_facing returns first matching camera."""
        # Add two back-facing cameras
        back_cam1 = CameraManager.Camera(
            lens_facing=CameraManager.CameraCharacteristics.LENS_FACING_BACK,
            name="BackCam1"
        )
        back_cam2 = CameraManager.Camera(
            lens_facing=CameraManager.CameraCharacteristics.LENS_FACING_BACK,
            name="BackCam2"
        )
        
        CameraManager.add_camera(back_cam1)
        CameraManager.add_camera(back_cam2)
        
        found = CameraManager.get_camera_by_facing(
            CameraManager.CameraCharacteristics.LENS_FACING_BACK
        )
        self.assertEqual(found.name, "BackCam1")

    def test_has_camera_empty(self):
        """Test has_camera() when no cameras registered."""
        self.assertFalse(CameraManager.has_camera())

    def test_has_camera_with_cameras(self):
        """Test has_camera() when cameras registered."""
        cam = CameraManager.Camera(
            lens_facing=CameraManager.CameraCharacteristics.LENS_FACING_BACK
        )
        CameraManager.add_camera(cam)
        self.assertTrue(CameraManager.has_camera())

    def test_get_camera_count_empty(self):
        """Test get_camera_count() when no cameras."""
        self.assertEqual(CameraManager.get_camera_count(), 0)

    def test_get_camera_count_multiple(self):
        """Test get_camera_count() with multiple cameras."""
        for i in range(3):
            cam = CameraManager.Camera(
                lens_facing=CameraManager.CameraCharacteristics.LENS_FACING_BACK,
                name=f"Camera{i}"
            )
            CameraManager.add_camera(cam)
        
        self.assertEqual(CameraManager.get_camera_count(), 3)


class TestCameraManagerUsagePattern(unittest.TestCase):
    """Test the usage pattern from the task description."""

    def setUp(self):
        """Clear cameras before each test."""
        CameraManager._cameras = []

    def tearDown(self):
        """Clean up after each test."""
        CameraManager._cameras = []

    def test_task_usage_pattern(self):
        """Test the exact usage pattern from the task description."""
        # Register a camera (as done in board init)
        CameraManager.add_camera(CameraManager.Camera(
            lens_facing=CameraManager.CameraCharacteristics.LENS_FACING_BACK
        ))
        
        # App usage pattern
        cam_list = CameraManager.get_cameras()
        
        if len(cam_list) > 0:
            has_camera = True
        else:
            has_camera = False
        
        self.assertTrue(has_camera)

    def test_task_usage_pattern_no_camera(self):
        """Test usage pattern when no camera available."""
        cam_list = CameraManager.get_cameras()
        
        if len(cam_list) > 0:
            has_camera = True
        else:
            has_camera = False
        
        self.assertFalse(has_camera)

