"""
Media file scanner - discovers video files in configured directories
"""

import os
import logging
from pathlib import Path
from lib.probe import MediaProbe

logger = logging.getLogger(__name__)

class MediaScanner:
    """Scans directories for media files and populates database"""
    
    def __init__(self, config, database):
        self.config = config
        self.db = database
        self.video_extensions = set(config.get_video_extensions())
    
    def scan_all(self):
        """Scan all configured source directories"""
        directories = self.config.get_source_directories()
        total_found = 0
        
        logger.info(f"Scanning {len(directories)} directories...")
        
        for directory in directories:
            dir_path = Path(directory)
            
            if not dir_path.exists():
                logger.warning(f"Directory not found: {directory}")
                continue
            
            if not dir_path.is_dir():
                logger.warning(f"Not a directory: {directory}")
                continue
            
            count = self.scan_directory(dir_path)
            total_found += count
            logger.info(f"Found {count} files in {directory}")
        
        logger.info(f"Total files found: {total_found}")
        return total_found
    
    def scan_directory(self, directory):
        """Recursively scan a directory for video files"""
        count = 0
        
        try:
            for root, dirs, files in os.walk(directory):
                # Skip trickplay directories and other metadata folders
                dirs[:] = [d for d in dirs if not d.endswith('.trickplay') 
                          and d not in ['.', '..', '@eaDir', '.DS_Store']]
                
                for filename in files:
                    file_path = Path(root) / filename
                    
                    # Skip if not a video file
                    if file_path.suffix.lower() not in self.video_extensions:
                        continue
                    
                    # Skip if already has .av1.inprogress marker
                    if (file_path.parent / f"{file_path.name}.av1.inprogress").exists():
                        logger.debug(f"Skipping file in progress: {file_path}")
                        continue
                    
                    # Skip if it's a backup file
                    if file_path.suffix == '.bak':
                        continue
                    
                    # Get file size
                    try:
                        size_bytes = file_path.stat().st_size
                    except OSError as e:
                        logger.error(f"Cannot stat file {file_path}: {e}")
                        continue
                    
                    # Probe file metadata
                    metadata = None
                    try:
                        logger.info(f"Probing {file_path.name}...")
                        metadata = MediaProbe.probe_file(file_path)
                        if metadata and metadata.get('video'):
                            logger.info(f"  Resolution: {metadata['video'].get('resolution')}, Codec: {metadata['video'].get('codec')}")
                    except Exception as e:
                        logger.warning(f"Failed to probe {file_path}: {e}")
                    
                    # Add to database
                    file_info = {
                        'path': str(file_path),
                        'directory': str(file_path.parent),
                        'filename': file_path.name,
                        'size_bytes': size_bytes
                    }
                    
                    # Add metadata if available
                    if metadata and metadata.get('video'):
                        video = metadata['video']
                        file_info['source_codec'] = video.get('codec')
                        file_info['source_bitrate'] = video.get('bitrate')
                        file_info['source_resolution'] = video.get('resolution')
                        file_info['source_bitdepth'] = video.get('bitdepth')
                        file_info['source_hdr'] = video.get('hdr')
                        file_info['hdr_dynamic'] = video.get('hdr_dynamic')
                        file_info['color_transfer'] = video.get('color_transfer')
                        file_info['color_space'] = video.get('color_space')
                        
                        if metadata.get('audio') and len(metadata['audio']) > 0:
                            audio = metadata['audio'][0]
                            file_info['source_audio_codec'] = audio.get('codec')
                            file_info['source_audio_channels'] = audio.get('channels')
                            file_info['source_audio_bitrate'] = audio.get('bitrate')
                    
                    self.db.add_file(file_info)
                    count += 1
                    
                    if count % 100 == 0:
                        logger.debug(f"Scanned {count} files...")
        
        except PermissionError as e:
            logger.error(f"Permission denied accessing {directory}: {e}")
        except Exception as e:
            logger.error(f"Error scanning {directory}: {e}", exc_info=True)
        
        return count
    
    def rescan(self):
        """Trigger a new scan of all directories"""
        logger.info("Starting rescan of media libraries")
        return self.scan_all()
