import unittest
from unittest.mock import patch, MagicMock, AsyncMock
import sys
import os
import asyncio

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class TestDownload(unittest.IsolatedAsyncioTestCase):
    
    @patch('download.pyaarlo')
    @patch('download.listen_for_events', new_callable=AsyncMock)
    @patch('download.asyncio.sleep', new_callable=AsyncMock) # Mock sleep to skip waiting
    async def test_main_connection_flow(self, mock_sleep, mock_listen, mock_pyaarlo):
        """Test the main connection loop and authentication."""
        from download import main
        
        # Setup:
        # 1. First iteration: Connects successfully, calls listen_for_events
        # 2. listen_for_events raises CancelledError to simulate shutdown signal
        mock_listen.side_effect = asyncio.CancelledError()
        
        # Run main
        # It should catch CancelledError, log "Exiting application...", and break the loop
        await main()
        
        # Verify PyArlo was initialized with correct env vars (mocked or from actual env)
        mock_pyaarlo.PyArlo.assert_called_once()
        
        # Verify we entered the event listener
        mock_listen.assert_called_once()

    @patch('download.pyaarlo')
    async def test_listen_for_events_callbacks(self, mock_pyaarlo):
        """Test that callbacks are registered on cameras."""
        from download import listen_for_events
        
        # Setup mock arlo instance with one camera
        mock_arlo = MagicMock()
        mock_camera = MagicMock()
        mock_camera.name = "TestCamera"
        mock_arlo.cameras = [mock_camera]
        
        # We need to interrupt the infinite loop in listen_for_events
        # We can do this by making asyncio.sleep raise an exception or CancelledError
        with patch('download.asyncio.sleep', side_effect=asyncio.CancelledError):
            try:
                await listen_for_events(mock_arlo)
            except asyncio.CancelledError:
                pass
        
        # Verify callback registration
        mock_camera.add_attr_callback.assert_called_with('lastCaptureTime', unittest.mock.ANY)

if __name__ == '__main__':
    unittest.main()