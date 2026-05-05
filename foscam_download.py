import os
import asyncio
import time
import logging
import requests
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
FOSCAM_IP = os.getenv("FOSCAM_IP", "192.168.1.100")
FOSCAM_PORT = int(os.getenv("FOSCAM_PORT", "88"))
FOSCAM_USERNAME = os.getenv("FOSCAM_USERNAME", "admin")
FOSCAM_PASSWORD = os.getenv("FOSCAM_PASSWORD", "")
DOWNLOAD_DIR = Path(os.getenv("DOWNLOAD_DIR", "C:/Users/geoff/Videos/Foscam"))
LOG_FILE = Path(os.getenv("LOG_FILE", "C:/Users/geoff/OneDrive/Documents/ArloAgain/foscam.log"))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Create download directory if it doesn't exist
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

class FoscamCamera:
    """Foscam camera interface using CGI API."""

    def __init__(self, ip, port=88, username="admin", password=""):
        self.ip = ip
        self.port = port
        self.username = username
        self.password = password
        self.base_url = f"http://{ip}:{port}"
        self.session = requests.Session()
        self.session.auth = (username, password)

    def _cgi_request(self, cmd, params=None):
        """Make a CGI request to the camera."""
        url = f"{self.base_url}/cgi-bin/CGIProxy.fcgi"
        data = {"cmd": cmd}
        if params:
            data.update(params)

        try:
            response = self.session.get(url, params=data, timeout=10)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            logger.error(f"CGI request failed: {e}")
            return None

    def get_dev_info(self):
        """Get device information."""
        return self._cgi_request("getDevInfo")

    def get_motion_detect_config(self):
        """Get motion detection configuration."""
        return self._cgi_request("getMotionDetectConfig")

    def set_motion_detect_config(self, enabled=True, sensitivity=4, trigger_interval=5):
        """Configure motion detection.

        Args:
            enabled: Enable/disable motion detection
            sensitivity: Sensitivity level (0-6, higher = more sensitive)
            trigger_interval: Minimum interval between triggers in seconds
        """
        params = {
            "isEnable": 1 if enabled else 0,
            "sensitivity": sensitivity,
            "triggerInterval": trigger_interval
        }
        return self._cgi_request("setMotionDetectConfig", params)

    def get_alarm_record_config(self):
        """Get alarm recording configuration."""
        return self._cgi_request("getAlarmRecordConfig")

    def set_alarm_record_config(self, enabled=True, record_seconds=30):
        """Configure alarm recording.

        Args:
            enabled: Enable/disable alarm recording
            record_seconds: Recording duration in seconds
        """
        params = {
            "isEnablePreRecord": 1 if enabled else 0,
            "preRecordSecs": record_seconds
        }
        return self._cgi_request("setAlarmRecordConfig", params)

    def snapshot(self):
        """Take a snapshot and return image data."""
        url = f"{self.base_url}/cgi-bin/CGIProxy.fcgi"
        params = {"cmd": "snapPicture2"}

        try:
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.content
        except requests.RequestException as e:
            logger.error(f"Snapshot failed: {e}")
            return None

    def get_video_stream_url(self, stream="main"):
        """Get RTSP or HTTP video stream URL.

        Args:
            stream: "main" or "sub" for different quality streams
        """
        # For HTTP stream
        return f"{self.base_url}/cgi-bin/CGIStream.cgi?cmd=GetMJStream&usr={self.username}&pwd={self.password}"

        # For RTSP (if supported):
        # return f"rtsp://{self.username}:{self.password}@{self.ip}:{self.port}/videoMain"  # or videoSub

    def download_recording(self, filename=None):
        """Download the latest recording or snapshot."""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"foscam_{timestamp}.jpg"

        filepath = DOWNLOAD_DIR / filename

        try:
            image_data = self.snapshot()
            if image_data:
                with open(filepath, 'wb') as f:
                    f.write(image_data)
                logger.info(f"Downloaded snapshot to: {filepath}")
                return str(filepath)
            else:
                logger.error("Failed to download snapshot")
                return None
        except Exception as e:
            logger.error(f"Error downloading recording: {e}")
            return None

def check_motion_status(camera):
    """Check if motion detection is currently active."""
    config = camera.get_motion_detect_config()
    if config and "isEnable" in config:
        return "isEnable=1" in config
    return False

async def monitor_motion_events(camera):
    """Monitor for motion events and download recordings."""
    logger.info("Starting Foscam motion monitoring...")

    # Ensure motion detection is enabled
    camera.set_motion_detect_config(enabled=True, sensitivity=4)
    camera.set_alarm_record_config(enabled=True, record_seconds=30)

    last_motion_time = 0
    check_interval = 5  # Check every 5 seconds

    try:
        while True:
            # Check motion status (this is a simplified approach)
            # In a real implementation, you might need to poll alarm status
            # or use the camera's alarm callback mechanism

            current_time = time.time()

            # For demonstration, we'll simulate motion detection by checking
            # if we should download a snapshot periodically
            # In practice, you'd want to check the camera's alarm status

            if current_time - last_motion_time > 60:  # Download every minute for demo
                logger.info("Checking for motion events...")
                filename = camera.download_recording()
                if filename:
                    logger.info(f"Motion event recorded: {filename}")
                    last_motion_time = current_time

            await asyncio.sleep(check_interval)

    except KeyboardInterrupt:
        logger.info("Stopping motion monitoring...")
        raise
    except Exception as e:
        logger.error(f"Error in motion monitoring: {e}")

async def main():
    """Main entry point for Foscam monitoring."""
    while True:
        try:
            logger.info("Connecting to Foscam camera...")

            camera = FoscamCamera(
                ip=FOSCAM_IP,
                port=FOSCAM_PORT,
                username=FOSCAM_USERNAME,
                password=FOSCAM_PASSWORD
            )

            # Test connection
            info = camera.get_dev_info()
            if info:
                logger.info("Successfully connected to Foscam camera")
                logger.info(f"Device info: {info[:100]}...")  # Log first 100 chars
            else:
                logger.error("Failed to connect to camera")
                await asyncio.sleep(60)
                continue

            await monitor_motion_events(camera)

        except (KeyboardInterrupt, asyncio.CancelledError):
            logger.info("Exiting application...")
            break
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            logger.info("Retrying in 60 seconds...")
            await asyncio.sleep(60)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass</content>
<parameter name="filePath">c:\Users\geoff\OneDrive\Documents\ArloAgain\foscam_download.py