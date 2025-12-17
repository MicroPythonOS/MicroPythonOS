"""
MicroPythonOS Testing Module

Provides mock implementations for testing without actual hardware.
These mocks work on both desktop (unit tests) and device (integration tests).

Usage:
    from mpos.testing import MockMachine, MockTaskManager, MockNetwork
    
    # Inject mocks before importing modules that use hardware
    import sys
    sys.modules['machine'] = MockMachine()
    
    # Or use the helper function
    from mpos.testing import inject_mocks
    inject_mocks(['machine', 'mpos.task_manager'])
"""

from .mocks import (
    # Hardware mocks
    MockMachine,
    MockPin,
    MockPWM,
    MockI2S,
    MockTimer,
    MockSocket,
    
    # MPOS mocks
    MockTaskManager,
    MockTask,
    MockDownloadManager,
    
    # Threading mocks
    MockThread,
    MockApps,
    
    # Network mocks
    MockNetwork,
    MockRequests,
    MockResponse,
    MockRaw,
    
    # Utility mocks
    MockTime,
    MockJSON,
    MockModule,
    
    # Helper functions
    inject_mocks,
    create_mock_module,
)

__all__ = [
    # Hardware mocks
    'MockMachine',
    'MockPin',
    'MockPWM',
    'MockI2S',
    'MockTimer',
    'MockSocket',
    
    # MPOS mocks
    'MockTaskManager',
    'MockTask',
    'MockDownloadManager',
    
    # Threading mocks
    'MockThread',
    'MockApps',
    
    # Network mocks
    'MockNetwork',
    'MockRequests',
    'MockResponse',
    'MockRaw',
    
    # Utility mocks
    'MockTime',
    'MockJSON',
    'MockModule',
    
    # Helper functions
    'inject_mocks',
    'create_mock_module',
]