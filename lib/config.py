"""
Configuration management for the transcoding service
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class Config:
    """Configuration handler with nested key access"""
    
    def __init__(self, config_path='config.json'):
        self.config_path = Path(config_path)
        self.config = self._load_config()
    
    def _load_config(self):
        """Load configuration from JSON file"""
        try:
            with open(self.config_path, 'r') as f:
                config = json.load(f)
                logger.info(f"Configuration loaded from {self.config_path}")
                return config
        except FileNotFoundError:
            logger.error(f"Config file not found: {self.config_path}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in config file: {e}")
            raise
    
    def get(self, key, default=None):
        """
        Get configuration value using dot notation.
        Example: config.get('web_server.port', 8080)
        """
        keys = key.split('.')
        value = self.config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def get_source_directories(self):
        """Get list of source media directories"""
        return self.get('source_directories', [])
    
    def get_temp_directory(self):
        """Get temporary directory for transcoding"""
        temp_dir = Path(self.get('temp_directory', '/tmp/av1_transcoding'))
        temp_dir.mkdir(parents=True, exist_ok=True)
        return temp_dir
    
    def is_testing_mode(self):
        """Check if running in testing mode"""
        return self.get('testing_mode', True)
    
    def get_video_extensions(self):
        """Get list of video file extensions to process"""
        return self.get('video_extensions', ['.mkv', '.mp4', '.avi', '.mov'])
    
    def reload(self):
        """Reload configuration from file"""
        self.config = self._load_config()
        logger.info("Configuration reloaded")
