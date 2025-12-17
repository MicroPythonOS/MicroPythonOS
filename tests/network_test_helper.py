"""
Network testing helper module for MicroPythonOS.

This module provides mock implementations of network-related modules
for testing without requiring actual network connectivity.

NOTE: This module re-exports mocks from mpos.testing for backward compatibility.
New code should import directly from mpos.testing.

Usage:
    from network_test_helper import MockNetwork, MockRequests, MockTimer
    
    # Or use the centralized module directly:
    from mpos.testing import MockNetwork, MockRequests, MockTimer
"""

# Re-export all mocks from centralized module for backward compatibility
from mpos.testing import (
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

# For backward compatibility, also provide socket() function
def socket(af=MockSocket.AF_INET, sock_type=MockSocket.SOCK_STREAM):
    """
    Create a mock socket.

    Args:
        af: Address family (default: AF_INET)
        sock_type: Socket type (default: SOCK_STREAM)

    Returns:
        MockSocket instance
    """
    return MockSocket(af, sock_type)


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
    'socket',
]
