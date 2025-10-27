#!/usr/bin/env python3
"""
Initialize configuration directory with default lookup tables
Copies defaults to /data/config if they don't exist
"""

import os
import shutil
import logging
from pathlib import Path

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

def init_config():
    """Initialize config directory with defaults"""
    config_dir = Path(os.environ.get('CONFIG_DIR', '/data/config'))
    app_dir = Path('/app')
    
    # Create config directory if it doesn't exist
    config_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Config directory: {config_dir}")
    
    # Files to copy
    config_files = [
        'quality_lookup.json',
        'audio_codec_lookup.json'
    ]
    
    for filename in config_files:
        src = app_dir / filename
        dst = config_dir / filename
        
        if not dst.exists() and src.exists():
            logger.info(f"Copying default {filename} to config directory")
            shutil.copy2(src, dst)
        elif dst.exists():
            logger.info(f"Using existing {filename} from config directory")
        else:
            logger.warning(f"Default {filename} not found in {app_dir}")
    
    return config_dir

if __name__ == '__main__':
    init_config()
