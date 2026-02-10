"""Tests for the logging module to ensure logger and handler level filtering works correctly."""

import unittest
import sys
import io
import logging

# Add lib to path so we can import logging
sys.path.insert(0, 'MicroPythonOS/internal_filesystem/lib')

class TestLoggingLevels(unittest.TestCase):
    """Test that logger levels work correctly with handlers."""

    def test_child_logger_info_level_with_root_handlers(self):
        """Test that a child logger can set INFO level and log INFO messages using root handlers."""
        # Capture output
        stream = io.StringIO()
        logging.basicConfig(stream=stream, level=logging.WARNING, force=True)
        
        # Create child logger and set to INFO
        logger = logging.getLogger("test_child")
        logger.setLevel(logging.INFO)
        
        # Log at different levels
        logger.debug("debug message")
        logger.info("info message")
        logger.warning("warning message")
        
        output = stream.getvalue()
        
        # Should NOT have debug (below INFO)
        self.assertTrue("debug message" not in output)
        # Should have info (at INFO level)
        self.assertTrue("info message" in output)
        # Should have warning (above INFO)
        self.assertTrue("warning message" in output)

    def test_root_logger_warning_level(self):
        """Test that root logger at WARNING level filters correctly."""
        stream = io.StringIO()
        logging.basicConfig(stream=stream, level=logging.WARNING, force=True)
        
        logger = logging.getLogger()
        
        logger.debug("debug message")
        logger.info("info message")
        logger.warning("warning message")
        
        output = stream.getvalue()
        
        # Should NOT have debug or info
        self.assertTrue("debug message" not in output)
        self.assertTrue("info message" not in output)
        # Should have warning
        self.assertTrue("warning message" in output)

    def test_child_logger_debug_level(self):
        """Test that a child logger can set DEBUG level."""
        stream = io.StringIO()
        logging.basicConfig(stream=stream, level=logging.WARNING, force=True)
        
        logger = logging.getLogger("test_debug")
        logger.setLevel(logging.DEBUG)
        
        logger.debug("debug message")
        logger.info("info message")
        logger.warning("warning message")
        
        output = stream.getvalue()
        
        # Should have all messages
        self.assertIn("debug message", output)
        self.assertIn("info message", output)
        self.assertIn("warning message", output)

    def test_multiple_child_loggers_different_levels(self):
        """Test that multiple child loggers can have different levels."""
        stream = io.StringIO()
        logging.basicConfig(stream=stream, level=logging.WARNING, force=True)
        
        logger1 = logging.getLogger("app1")
        logger1.setLevel(logging.DEBUG)
        
        logger2 = logging.getLogger("app2")
        logger2.setLevel(logging.ERROR)
        
        logger1.debug("app1 debug")
        logger1.info("app1 info")
        logger2.debug("app2 debug")
        logger2.info("app2 info")
        logger2.error("app2 error")
        
        output = stream.getvalue()
        
        # app1 should log debug and info
        self.assertTrue("app1 debug" in output)
        self.assertTrue("app1 info" in output)
        # app2 should NOT log debug or info
        self.assertTrue("app2 debug" not in output)
        self.assertTrue("app2 info" not in output)
        # app2 should log error
        self.assertTrue("app2 error" in output)

    def test_handler_level_does_not_filter(self):
        """Test that handler level is NOTSET and doesn't filter messages."""
        stream = io.StringIO()
        logging.basicConfig(stream=stream, level=logging.INFO, force=True)
        
        # Get the root logger and check handler level
        root_logger = logging.getLogger()
        self.assertEqual(len(root_logger.handlers), 1)
        handler = root_logger.handlers[0]
        
        # Handler level should be NOTSET (0) so it doesn't filter
        self.assertEqual(handler.level, logging.NOTSET)

    def test_child_logger_notset_level_uses_root_level(self):
        """Test that a child logger with NOTSET level uses root logger's level."""
        stream = io.StringIO()
        logging.basicConfig(stream=stream, level=logging.WARNING, force=True)
        
        logger = logging.getLogger("test_notset")
        # Don't set logger level, it should default to NOTSET
        
        logger.debug("debug message")
        logger.info("info message")
        logger.warning("warning message")
        
        output = stream.getvalue()
        
        # Should use root logger's WARNING level
        self.assertTrue("debug message" not in output)
        self.assertTrue("info message" not in output)
        self.assertTrue("warning message" in output)

