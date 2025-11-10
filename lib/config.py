"""
Configuration management for the transcoding service
"""

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

class Config:
    """Configuration handler with environment variable support"""
    
    def __init__(self, config_path='config.json'):
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self._apply_env_overrides()
    
    def _load_config(self):
        """Load configuration from JSON file"""
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r') as f:
                    config = json.load(f)
                    logger.info(f"Configuration loaded from {self.config_path}")
                    return config
            else:
                logger.warning(f"Config file not found: {self.config_path}, using defaults")
                return {}
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in config file: {e}")
            raise
    
    def _apply_env_overrides(self):
        """Override config with environment variables"""
        # Media directories
        if os.getenv('MEDIA_DIRS'):
            media_dirs = os.getenv('MEDIA_DIRS').split(',')
            self.config['media_directories'] = [d.strip() for d in media_dirs]
            logger.info(f"Media directories from ENV: {media_dirs}")
        
        # Temp directory
        if os.getenv('TEMP_DIR'):
            self.config['temp_directory'] = os.getenv('TEMP_DIR')
        
        # Preserve mode (with backward compatibility for TESTING_MODE)
        if os.getenv('PRESERVE_MODE'):
            self.config['preserve_mode'] = os.getenv('PRESERVE_MODE').lower() in ('true', '1', 'yes')
        elif os.getenv('TESTING_MODE'):
            # Backward compatibility
            self.config['preserve_mode'] = os.getenv('TESTING_MODE').lower() in ('true', '1', 'yes')
        
        # Web port
        if os.getenv('WEB_PORT'):
            if 'web_server' not in self.config:
                self.config['web_server'] = {}
            self.config['web_server']['port'] = int(os.getenv('WEB_PORT'))
        
        # SVT-AV1 preset
        if os.getenv('SVT_AV1_PRESET'):
            if 'transcoding' not in self.config:
                self.config['transcoding'] = {}
            self.config['transcoding']['svt_av1_preset'] = int(os.getenv('SVT_AV1_PRESET'))
        
        # Process priority
        if os.getenv('NICE_LEVEL') or os.getenv('IONICE_CLASS'):
            if 'process_priority' not in self.config:
                self.config['process_priority'] = {}
            if os.getenv('NICE_LEVEL'):
                self.config['process_priority']['nice'] = int(os.getenv('NICE_LEVEL'))
            if os.getenv('IONICE_CLASS'):
                self.config['process_priority']['ionice_class'] = int(os.getenv('IONICE_CLASS'))
        
        # File processing order
        if os.getenv('FILE_ORDER'):
            if 'processing' not in self.config:
                self.config['processing'] = {}
            self.config['processing']['file_order'] = os.getenv('FILE_ORDER').lower()
        
        # Audio transcoding setting
        if os.getenv('SKIP_AUDIO_TRANSCODE'):
            if 'transcoding' not in self.config:
                self.config['transcoding'] = {}
            self.config['transcoding']['skip_audio_transcode'] = os.getenv('SKIP_AUDIO_TRANSCODE').lower() in ('true', '1', 'yes')
        
        # Skip AV1 files setting
        if os.getenv('SKIP_AV1_FILES'):
            if 'transcoding' not in self.config:
                self.config['transcoding'] = {}
            self.config['transcoding']['skip_av1_files'] = os.getenv('SKIP_AV1_FILES').lower() in ('true', '1', 'yes')
    
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
        # Try new key first, fallback to old key
        dirs = self.get('media_directories', self.get('source_directories', []))
        return dirs
    
    def get_temp_directory(self):
        """Get temporary directory for transcoding"""
        temp_dir = Path(self.get('temp_directory', '/tmp/av1_transcoding'))
        temp_dir.mkdir(parents=True, exist_ok=True)
        return temp_dir
    
    def is_preserve_mode(self):
        """Check if running in preserve mode (keeps .bak files instead of deleting originals)"""
        return self.get('preserve_mode', True)
    
    def is_testing_mode(self):
        """Deprecated: Use is_preserve_mode() instead. Kept for backward compatibility."""
        return self.is_preserve_mode()
    
    def get_video_extensions(self):
        """Get list of video file extensions to process"""
        return self.get('video_extensions', ['.mkv', '.mp4', '.avi', '.mov'])
    
    def get_file_order(self):
        """Get file processing order preference"""
        order = self.get('processing.file_order', 'oldest')
        # Valid options: 'oldest', 'newest', 'largest', 'smallest'
        if order not in ['oldest', 'newest', 'largest', 'smallest']:
            logger.warning(f"Invalid file order '{order}', defaulting to 'oldest'")
            return 'oldest'
        return order
    
    def skip_audio_transcode(self):
        """Check if audio transcoding should be skipped (copy audio streams instead)"""
        return self.get('transcoding.skip_audio_transcode', False)
    
    def skip_av1_files(self):
        """Check if AV1-encoded files should be skipped (not added to processing queue)"""
        return self.get('transcoding.skip_av1_files', False)
    
    def reload(self):
        """Reload configuration from file"""
        self.config = self._load_config()
        logger.info("Configuration reloaded")
