import unittest
from unittest.mock import patch, MagicMock, ANY
import sys
import os

# Add parent directory to path to allow importing processor
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock ultralytics before importing processor to prevent model loading during import
with patch.dict('sys.modules', {'ultralytics': MagicMock()}):
    from processor import FileHandler

class TestFileHandler(unittest.TestCase):
    def setUp(self):
        self.handler = FileHandler()

    @patch('processor.FileHandler.process_file')
    def test_on_created_mp4(self, mock_process):
        """Test that .mp4 files trigger processing."""
        event = MagicMock()
        event.is_directory = False
        event.src_path = "C:/Videos/test.mp4"
        
        self.handler.on_created(event)
        mock_process.assert_called_with("C:/Videos/test.mp4")

    @patch('processor.FileHandler.process_file')
    def test_on_created_ignore_other_files(self, mock_process):
        """Test that non-mp4 files are ignored."""
        event = MagicMock()
        event.is_directory = False
        event.src_path = "C:/Videos/test.txt"
        
        self.handler.on_created(event)
        mock_process.assert_not_called()

    @patch('processor.time.sleep')
    @patch('processor.cv2')
    @patch('processor.model')
    @patch('processor.WebClient')
    @patch('processor.SLACK_API_TOKEN', 'fake_token')
    def test_process_file_person_detected(self, mock_slack_class, mock_model, mock_cv2, mock_sleep):
        """Test processing when a person is detected."""
        # Setup VideoCapture
        mock_cap = MagicMock()
        mock_cv2.VideoCapture.return_value = mock_cap
        mock_cap.isOpened.return_value = True
        
        # Setup frames: 
        # We need enough frames to pass the frame_skip (5).
        # read() returns (success, frame)
        mock_frame = MagicMock()
        # Return success 6 times, then False (end of video)
        mock_cap.read.side_effect = [(True, mock_frame)] * 6 + [(False, None)]
        
        # Setup Model inference result
        # The code checks: if len(results[0].boxes) > 0
        mock_result = MagicMock()
        mock_result.boxes = [1] # Simulate detection
        mock_model.return_value = [mock_result]
        
        # Run
        self.handler.process_file("video.mp4")
        
        # Assertions
        mock_cv2.VideoCapture.assert_called_with("video.mp4")
        # Verify inference was called
        mock_model.assert_called()
        # Verify image was saved
        mock_cv2.imwrite.assert_called()
        # Verify Slack upload initiated
        mock_slack_instance = mock_slack_class.return_value
        mock_slack_instance.files_upload_v2.assert_called()
        
        # Verify cleanup
        mock_cap.release.assert_called()

    @patch('processor.time.sleep')
    @patch('processor.cv2')
    @patch('processor.model')
    @patch('processor.WebClient')
    def test_process_file_no_person(self, mock_slack_class, mock_model, mock_cv2, mock_sleep):
        """Test processing when no person is detected."""
        mock_cap = MagicMock()
        mock_cv2.VideoCapture.return_value = mock_cap
        mock_cap.isOpened.return_value = True
        
        # 6 frames, then stop
        mock_frame = MagicMock()
        mock_cap.read.side_effect = [(True, mock_frame)] * 6 + [(False, None)]
        
        # Empty boxes (no detection)
        mock_result = MagicMock()
        mock_result.boxes = [] 
        mock_model.return_value = [mock_result]
        
        self.handler.process_file("video.mp4")
        
        # Verify NO image saved or uploaded
        mock_cv2.imwrite.assert_not_called()
        mock_slack_class.return_value.files_upload_v2.assert_not_called()
        mock_cap.release.assert_called()

if __name__ == '__main__':
    unittest.main()