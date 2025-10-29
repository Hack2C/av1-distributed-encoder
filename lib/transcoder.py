"""
Core transcoding engine - handles the actual video encoding process
"""

import os
import re
import shutil
import subprocess
import logging
import time
from pathlib import Path
from threading import Lock

from lib.probe import MediaProbe
from lib.quality import QualityLookup

logger = logging.getLogger(__name__)

class TranscodingEngine:
    """Main transcoding engine that processes files one at a time"""
    
    def __init__(self, config, database, shutdown_event):
        self.config = config
        self.db = database
        self.shutdown_event = shutdown_event
        self.socketio = None
        self.current_file = None
        self.current_process = None  # Track current FFmpeg process
        self.is_running = False
        self.is_paused = False
        self.lock = Lock()
        
        self.quality_lookup = QualityLookup()
        self.temp_dir = config.get_temp_directory()
        
        logger.info("Transcoding engine initialized")
    
    def set_socketio(self, socketio):
        """Set Socket.IO instance for progress updates"""
        self.socketio = socketio
    
    def abort_current_file(self):
        """Abort the currently processing file"""
        with self.lock:
            if self.current_process and self.current_process.poll() is None:
                logger.info("Aborting current transcoding process")
                try:
                    self.current_process.terminate()
                    time.sleep(2)
                    if self.current_process.poll() is None:
                        self.current_process.kill()
                    logger.info("Process aborted successfully")
                    return True
                except Exception as e:
                    logger.error(f"Error aborting process: {e}", exc_info=True)
                    return False
            return False
    
    def run(self):
        """Main processing loop"""
        self.is_running = True
        logger.info("Transcoding engine started")
        
        while not self.shutdown_event.is_set():
            if self.is_paused:
                time.sleep(1)
                continue
            
            # Get next file to process
            file_record = self.db.get_next_pending_file()
            
            if not file_record:
                # No files to process, wait a bit
                time.sleep(5)
                continue
            
            # Process the file
            try:
                self.process_file(file_record)
            except Exception as e:
                logger.error(f"Unexpected error processing file: {e}", exc_info=True)
                self.db.mark_file_failed(file_record['id'], str(e))
            
            # Small delay between files
            time.sleep(2)
        
        logger.info("Transcoding engine stopped")
        self.is_running = False
    
    def process_file(self, file_record):
        """Process a single file through the complete transcoding workflow"""
        file_id = file_record['id']
        file_path = Path(file_record['path'])
        
        logger.info(f"Processing: {file_path}")
        self.current_file = file_record
        self._emit_progress('processing_started', {'file': str(file_path)})
        
        # Step 1: Check if source file exists
        if not file_path.exists():
            logger.error(f"Source file not found: {file_path}")
            self.db.mark_file_failed(file_id, "Source file not found")
            self._emit_progress('error', {'message': 'Source file not found'})
            return
        
        # Step 2: Create .av1.inprogress marker
        marker_path = file_path.parent / f"{file_path.name}.av1.inprogress"
        try:
            marker_path.touch()
            logger.debug(f"Created marker: {marker_path}")
        except Exception as e:
            logger.error(f"Failed to create marker: {e}")
            self.db.mark_file_failed(file_id, f"Failed to create marker: {e}")
            return
        
        try:
            # Step 3: Mark as processing in database
            self.db.mark_file_processing(file_id)
            
            # Step 4: Copy to temp directory
            temp_input = self._copy_to_temp(file_path)
            if not temp_input:
                raise Exception("Failed to copy file to temp directory")
            
            # Step 5: Probe file metadata
            self._emit_progress('probing', {'file': str(file_path)})
            metadata = MediaProbe.probe_file(temp_input)
            if not metadata or not metadata.get('video'):
                raise Exception("Failed to probe file or no video stream found")
            
            logger.info(f"Metadata: {metadata}")
            
            # Step 5.5: Check for dynamic HDR that cannot be preserved
            video = metadata['video']
            hdr_type = video.get('hdr', 'SDR')
            has_dynamic_hdr = video.get('hdr_dynamic', False)
            
            if has_dynamic_hdr and hdr_type in ['HDR10+', 'Dolby Vision']:
                logger.warning(f"Skipping {file_path}: Contains {hdr_type} with dynamic metadata")
                logger.warning(f"Dynamic HDR metadata cannot be preserved in AV1 - would harm perceptive quality")
                
                error_msg = f"Skipped: {hdr_type} dynamic metadata cannot be preserved (quality protection)"
                self.db.skip_file(file_id)
                self.db.update_file_error(file_id, error_msg)
                
                self._emit_progress('skipped', {
                    'file': str(file_path),
                    'reason': error_msg,
                    'hdr_type': hdr_type
                })
                return
            
            # Log HDR10 static metadata (can be preserved)
            if hdr_type == 'HDR10':
                logger.info(f"Processing HDR10 content: {file_path}")
                logger.info(f"Static HDR10 metadata will be preserved (transfer: {video.get('color_transfer')}, space: {video.get('color_space')})")
            
            # Step 6: Determine optimal settings
            settings = self._determine_settings(metadata)
            logger.info(f"Encoding settings: CRF={settings['crf']}, Opus={settings['opus_bitrate']}k")
            
            # Update database with source info and target settings
            self.db.update_file_status(file_id, 'processing',
                source_codec=metadata['video']['codec'],
                source_bitrate=metadata['video']['bitrate'],
                source_resolution=metadata['video']['resolution'],
                source_bitdepth=metadata['video']['bitdepth'],
                source_hdr=metadata['video']['hdr'],
                source_audio_codec=metadata['audio'][0]['codec'] if metadata['audio'] else None,
                source_audio_channels=metadata['audio'][0]['channels'] if metadata['audio'] else 0,
                source_audio_bitrate=metadata['audio'][0]['bitrate'] if metadata['audio'] else 0,
                target_crf=settings['crf'],
                target_opus_bitrate=settings['opus_bitrate']
            )
            
            # Step 7: Transcode
            self._emit_progress('transcoding', {'file': str(file_path), 'settings': settings})
            temp_output = self._transcode(temp_input, metadata, settings, file_id)
            if not temp_output or not temp_output.exists():
                raise Exception("Transcoding failed")
            
            # Step 8: Verify output
            self._emit_progress('verifying', {'file': str(temp_output)})
            if not self._verify_output(temp_output):
                raise Exception("Output verification failed")
            
            # Step 9: Check if transcoding is worthwhile
            output_size = temp_output.stat().st_size
            original_size = file_record['size_bytes']
            savings_bytes = original_size - output_size
            savings_percent = (savings_bytes / original_size * 100) if original_size > 0 else 0
            
            # If output is larger or savings are negligible (less than 5%), skip replacement
            if output_size >= original_size or savings_percent < 5:
                logger.warning(f"Transcoding not worthwhile: {file_path}")
                logger.warning(f"Size: {original_size:,} -> {output_size:,} bytes ({savings_percent:.1f}% savings)")
                
                # Mark as completed but with special message
                error_msg = f"Not worth transcoding: Output would be {abs(savings_percent):.1f}% {'larger' if output_size > original_size else 'smaller'} (minimum 5% savings required)"
                self.db.skip_file(file_id)
                self.db.update_file_error(file_id, error_msg)
                
                self._emit_progress('skipped', {
                    'file': str(file_path),
                    'reason': error_msg,
                    'original_size': original_size,
                    'output_size': output_size
                })
                return
            
            # Step 10: Safe file replacement (only if worthwhile)
            self._emit_progress('replacing', {'file': str(file_path)})
            self._replace_original(file_path, temp_output)
            
            logger.info(f"Completed: {file_path}")
            logger.info(f"Size: {original_size:,} -> {output_size:,} bytes ({savings_percent:.1f}% savings)")
            
            # Step 11: Mark as completed
            self.db.mark_file_completed(file_id, output_size, savings_bytes, savings_percent)
            self._emit_progress('completed', {
                'file': str(file_path),
                'original_size': original_size,
                'output_size': output_size,
                'savings_percent': savings_percent
            })
        
        except Exception as e:
            logger.error(f"Failed to process {file_path}: {e}", exc_info=True)
            self.db.mark_file_failed(file_id, str(e))
            self._emit_progress('error', {'file': str(file_path), 'error': str(e)})
        
        finally:
            # Clean up marker
            try:
                if marker_path.exists():
                    marker_path.unlink()
                    logger.debug(f"Removed marker: {marker_path}")
            except Exception as e:
                logger.warning(f"Failed to remove marker: {e}")
            
            # Clean up temp files
            self._cleanup_temp_files()
            
            self.current_file = None
    
    def _copy_to_temp(self, source_path):
        """Copy source file to temporary directory"""
        try:
            temp_file = self.temp_dir / source_path.name
            logger.info(f"Copying to temp: {source_path} -> {temp_file}")
            
            shutil.copy2(source_path, temp_file)
            
            logger.debug(f"Copied {temp_file.stat().st_size:,} bytes")
            return temp_file
        
        except Exception as e:
            logger.error(f"Failed to copy to temp: {e}", exc_info=True)
            return None
    
    def _determine_settings(self, metadata):
        """Determine optimal encoding settings based on metadata"""
        video = metadata['video']
        audio = metadata['audio'][0] if metadata['audio'] else None
        
        # Get video CRF
        bitrate_cat = MediaProbe.get_bitrate_category(video['bitrate'])
        crf = self.quality_lookup.get_video_crf(
            codec=video['codec'],
            bitdepth=video['bitdepth'],
            hdr=video['hdr'],
            resolution=video['resolution'],
            bitrate_category=bitrate_cat
        )
        
        # Get audio Opus bitrate
        opus_bitrate = 128  # Default
        if audio:
            audio_bitrate_cat = MediaProbe.get_audio_bitrate_category(
                audio['bitrate'], audio['codec']
            )
            channel_count = audio['channels']
            opus_bitrate = self.quality_lookup.get_opus_bitrate(
                source_codec=audio['codec'],
                channels=channel_count,
                source_bitrate_category=audio_bitrate_cat
            )
        
        return {
            'crf': crf,
            'opus_bitrate': opus_bitrate,
            'preset': self.config.get('transcoding.svt_av1_preset', 0)
        }
    
    def _transcode(self, input_file, metadata, settings, file_id):
        """Perform the actual transcoding with SVT-AV1 and Opus"""
        output_file = self.temp_dir / f"{input_file.stem}_av1.mkv"
        
        # Build ffmpeg command
        cmd = self._build_ffmpeg_command(input_file, output_file, metadata, settings)
        
        logger.info(f"Starting transcode: {' '.join(cmd)}")
        
        try:
            # Set process priority
            nice_value = self.config.get('process_priority.nice', 19)
            ionice_class = self.config.get('process_priority.ionice_class', 3)
            
            # Prepend nice and ionice
            cmd = ['nice', '-n', str(nice_value), 'ionice', '-c', str(ionice_class)] + cmd
            
            # Run ffmpeg with progress monitoring
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                bufsize=1
            )
            
            # Track current process for abort capability
            with self.lock:
                self.current_process = process
            
            try:
                # Monitor progress
                duration = metadata['format']['duration']
                self._monitor_ffmpeg_progress(process, duration, file_id)
                
                # Wait for completion
                returncode = process.wait()
                
                if returncode != 0:
                    stderr = process.stderr.read()
                    logger.error(f"ffmpeg failed with code {returncode}: {stderr}")
                    return None
                
                logger.info(f"Transcode completed: {output_file}")
                return output_file
            finally:
                # Clear current process
                with self.lock:
                    self.current_process = None
        
        except Exception as e:
            logger.error(f"Transcoding error: {e}", exc_info=True)
            return None
    
    def _build_ffmpeg_command(self, input_file, output_file, metadata, settings):
        """Build the ffmpeg command with all parameters"""
        cmd = [
            'ffmpeg',
            '-i', str(input_file),
            '-map', '0',  # Map all streams
            '-c:v', 'libsvtav1',  # AV1 video codec
            '-preset', str(settings['preset']),
            '-crf', str(settings['crf']),
        ]
        
        # Enhanced HDR10 handling
        video = metadata['video']
        hdr_type = video.get('hdr', 'SDR')
        
        if hdr_type == 'HDR10':
            # Preserve color space and transfer characteristics
            color_transfer = video.get('color_transfer', 'smpte2084')
            color_space = video.get('color_space', 'bt2020nc')
            
            cmd.extend([
                '-color_primaries', 'bt2020',
                '-color_trc', color_transfer if color_transfer in ['smpte2084', 'arib-std-b67'] else 'smpte2084',
                '-colorspace', color_space if 'bt2020' in color_space else 'bt2020nc',
            ])
            
            # Enable HDR in SVT-AV1
            svt_params = ['enable-hdr=1']
            cmd.extend(['-svtav1-params', ':'.join(svt_params)])
            
            logger.info(f"HDR10 metadata preservation enabled (transfer={color_transfer}, space={color_space})")
        
        # Audio encoding - convert all to Opus
        cmd.extend([
            '-c:a', 'libopus',
            '-b:a', f"{settings['opus_bitrate']}k",
        ])
        
        # Copy subtitles if configured
        if self.config.get('transcoding.copy_subtitles', True):
            cmd.extend(['-c:s', 'copy'])
        
        # Copy metadata
        if self.config.get('transcoding.copy_metadata', True):
            cmd.extend(['-map_metadata', '0'])
        
        # Output file
        cmd.extend([
            '-y',  # Overwrite output
            str(output_file)
        ])
        
        return cmd
    
    def _monitor_ffmpeg_progress(self, process, total_duration, file_id):
        """Monitor ffmpeg progress and update database/socketio"""
        progress_pattern = re.compile(r'time=(\d+):(\d+):(\d+\.\d+)')
        last_update_time = 0
        last_progress = -1  # Start at -1 to ensure first update always happens
        
        for line in process.stderr:
            # Check for shutdown
            if self.shutdown_event.is_set():
                process.terminate()
                logger.info("Transcoding interrupted by shutdown")
                return
            
            # Parse progress
            match = progress_pattern.search(line)
            if match and total_duration > 0:
                hours, minutes, seconds = match.groups()
                current_time = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
                progress_percent = min((current_time / total_duration) * 100, 100)
                
                current_timestamp = time.time()
                
                # Only update if:
                # 1. At least 2 seconds have passed since last update, OR
                # 2. Progress changed by at least 1.0% (to avoid micro-updates)
                time_threshold = 2.0  # Update every 2 seconds max
                progress_threshold = 1.0  # Update only for 1%+ changes
                
                should_update = (
                    current_timestamp - last_update_time >= time_threshold or
                    abs(progress_percent - last_progress) >= progress_threshold
                )
                
                if should_update:
                    # Update database
                    self.db.update_file_status(file_id, 'processing', 
                                              progress_percent=progress_percent)
                    
                    # Emit to websocket
                    self._emit_progress('progress', {
                        'file_id': file_id,
                        'percent': progress_percent
                    })
                    
                    last_progress = progress_percent
                    last_update_time = current_timestamp
    
    def _verify_output(self, output_file):
        """Verify that output file is valid and playable"""
        if not output_file.exists():
            logger.error("Output file does not exist")
            return False
        
        if output_file.stat().st_size < 1000:
            logger.error("Output file is too small")
            return False
        
        # Quick probe to verify it's valid
        metadata = MediaProbe.probe_file(output_file)
        if not metadata or not metadata.get('video'):
            logger.error("Output file verification failed - no video stream")
            return False
        
        logger.info("Output file verified successfully")
        return True
    
    def _replace_original(self, original_path, transcoded_path):
        """Safely replace original file with transcoded version"""
        try:
            # Copy transcoded file back to original directory
            output_path = original_path.parent / transcoded_path.name
            shutil.copy2(transcoded_path, output_path)
            logger.debug(f"Copied transcoded file to: {output_path}")
            
            # Rename original to .bak
            backup_path = original_path.with_suffix(original_path.suffix + '.bak')
            original_path.rename(backup_path)
            logger.debug(f"Renamed original to: {backup_path}")
            
            # Rename transcoded to original name
            final_path = original_path
            output_path.rename(final_path)
            logger.info(f"Renamed transcoded to original name: {final_path}")
            
            # Delete backup if not in preserve mode
            if not self.config.is_preserve_mode():
                backup_path.unlink()
                logger.info(f"Deleted backup: {backup_path}")
            else:
                logger.info(f"Preserve mode: keeping backup {backup_path}")
        
        except Exception as e:
            logger.error(f"Failed to replace original file: {e}", exc_info=True)
            raise
    
    def _cleanup_temp_files(self):
        """Clean up temporary files"""
        try:
            for temp_file in self.temp_dir.glob('*'):
                if temp_file.is_file():
                    temp_file.unlink()
                    logger.debug(f"Removed temp file: {temp_file}")
        except Exception as e:
            logger.warning(f"Failed to clean up temp files: {e}")
    
    def _emit_progress(self, event, data):
        """Emit progress update via SocketIO"""
        if self.socketio:
            try:
                self.socketio.emit(event, data)
            except Exception as e:
                logger.warning(f"Failed to emit progress: {e}")
    
    def pause(self):
        """Pause processing"""
        with self.lock:
            self.is_paused = True
            logger.info("Transcoding paused")
    
    def resume(self):
        """Resume processing"""
        with self.lock:
            self.is_paused = False
            logger.info("Transcoding resumed")
    
    def stop(self):
        """Stop the engine"""
        logger.info("Stopping transcoding engine...")
        self.shutdown_event.set()
    
    def get_status(self):
        """Get current engine status"""
        return {
            'is_running': self.is_running,
            'is_paused': self.is_paused,
            'current_file': self.current_file
        }
