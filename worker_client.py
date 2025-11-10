#!/usr/bin/env python3
"""
Worker Client - Connects to master server and processes transcoding jobs
"""

__version__ = "2.2.10"

import os
import sys
import time
import signal
import logging
import socket
import requests
import threading
import psutil
from datetime import datetime
from pathlib import Path
from datetime import datetime

# Add lib directory to path
sys.path.insert(0, str(Path(__file__).parent))

from lib.config import Config
from lib.probe import MediaProbe
from lib.quality import QualityLookup
from lib.transcoder import TranscodingEngine

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class WorkerClient:
    """Worker client that processes jobs from master server"""
    
    def __init__(self, master_url):
        self.master_url = master_url.rstrip('/')
        self.worker_id = None
        self.hostname = socket.gethostname()
        self.config = Config()
        self.is_running = False
        self.shutdown_event = threading.Event()
        self.current_job = None
        self.current_speed = 0.0  # Current FPS
        self.current_eta = 0  # Current ETA in seconds
        self.current_phase = 'idle'  # Track current activity: 'idle', 'downloading', 'processing', 'uploading'
        
        # Prime CPU monitoring
        psutil.cpu_percent(interval=None)
        
        logger.info(f"Worker initialized: {self.hostname}")
        logger.info(f"Master server: {self.master_url}")
        
        # Clean up temp directory from previous runs
        self._cleanup_temp_directory()
        
        # Fetch quality lookup from master or use local
        self.quality_lookup = self._init_quality_lookup()
    
    def _cleanup_temp_directory(self):
        """Clean up temporary files from previous worker runs"""
        try:
            temp_dir = Path(self.config.get_temp_directory())
            if temp_dir.exists():
                logger.info(f"Cleaning up temp directory: {temp_dir}")
                file_count = 0
                for item in temp_dir.iterdir():
                    try:
                        if item.is_file():
                            item.unlink()
                            file_count += 1
                        elif item.is_dir():
                            import shutil
                            shutil.rmtree(item)
                            file_count += 1
                    except Exception as e:
                        logger.warning(f"Failed to delete {item}: {e}")
                
                if file_count > 0:
                    logger.info(f"Removed {file_count} items from temp directory")
                else:
                    logger.info("Temp directory is clean")
            else:
                logger.info(f"Creating temp directory: {temp_dir}")
                temp_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.error(f"Error cleaning temp directory: {e}", exc_info=True)
    
    def _retry_failed_uploads(self):
        """Check for and retry failed uploads"""
        try:
            failed_uploads_dir = Path(self.config.get_temp_directory()) / 'failed_uploads'
            if not failed_uploads_dir.exists():
                return
            
            # Look for transcoded files with metadata
            for transcoded_file in failed_uploads_dir.glob('*.mkv'):
                metadata_file = transcoded_file.with_suffix('.metadata')
                if not metadata_file.exists():
                    continue
                
                # Read metadata
                metadata = {}
                try:
                    with open(metadata_file, 'r') as f:
                        for line in f:
                            if '=' in line:
                                key, value = line.strip().split('=', 1)
                                metadata[key] = value
                except Exception as e:
                    logger.warning(f"Failed to read metadata for {transcoded_file}: {e}")
                    continue
                
                job_id = metadata.get('job_id')
                original_path = metadata.get('original_path')
                failed_at = metadata.get('failed_at')
                
                if not job_id or not original_path:
                    logger.warning(f"Incomplete metadata for {transcoded_file}")
                    continue
                
                logger.info(f"Retrying upload for job {job_id} (failed at {failed_at})")
                
                try:
                    # Attempt to upload the file
                    with open(transcoded_file, 'rb') as f:
                        files = {'file': (transcoded_file.name, f, 'application/octet-stream')}
                        response = requests.post(
                            f"{self.master_url}/api/file/{job_id}/result",
                            files=files,
                            timeout=300  # 5 minutes for upload
                        )
                    
                    if response.status_code == 200:
                        result = response.json()
                        if result.get('success'):
                            logger.info(f"Successfully retried upload for job {job_id}")
                            
                            # Clean up the failed upload files
                            transcoded_file.unlink()
                            metadata_file.unlink()
                            
                            # Report completion
                            output_size = result.get('new_size', 0)
                            original_size = result.get('original_size', 0)
                            self.report_completion(int(job_id), output_size, original_size)
                            
                        else:
                            logger.warning(f"Master rejected retry upload for job {job_id}: {result.get('error')}")
                    else:
                        logger.warning(f"Retry upload failed for job {job_id}: HTTP {response.status_code}")
                
                except Exception as e:
                    logger.warning(f"Failed to retry upload for job {job_id}: {e}")
                    
        except Exception as e:
            logger.error(f"Error during failed upload retry: {e}", exc_info=True)
    
    def _init_quality_lookup(self):
        """Initialize quality lookup - fetch from master or use local config"""
        try:
            # Try to fetch from master
            logger.info("Fetching quality lookup from master...")
            quality_response = requests.get(f"{self.master_url}/api/config/quality_lookup.json", timeout=10)
            audio_response = requests.get(f"{self.master_url}/api/config/audio_codec_lookup.json", timeout=10)
            
            if quality_response.status_code == 200 and audio_response.status_code == 200:
                # Save to temp config directory
                config_dir = Path(os.environ.get('CONFIG_DIR', '/data/config'))
                config_dir.mkdir(parents=True, exist_ok=True)
                
                quality_file = config_dir / 'quality_lookup.json'
                audio_file = config_dir / 'audio_codec_lookup.json'
                
                with open(quality_file, 'w') as f:
                    f.write(quality_response.text)
                
                with open(audio_file, 'w') as f:
                    f.write(audio_response.text)
                
                logger.info("Successfully fetched and saved config from master")
                return QualityLookup(config_dir)
            else:
                logger.warning(f"Failed to fetch config from master (status: {quality_response.status_code})")
                return QualityLookup()
        
        except Exception as e:
            logger.warning(f"Could not fetch config from master: {e}")
            logger.info("Using local quality lookup configuration")
            return QualityLookup()

    
    def register(self):
        """Register with master server"""
        try:
            capabilities = {
                'cpu_count': psutil.cpu_count(),
                'memory_total': psutil.virtual_memory().total,
                'has_gpu': False  # TODO: Detect GPU
            }
            
            response = requests.post(
                f"{self.master_url}/api/worker/register",
                json={
                    'hostname': self.hostname,
                    'capabilities': capabilities,
                    'version': __version__
                },
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                if data['success']:
                    self.worker_id = data['worker_id']
                    logger.info(f"Registered as {self.worker_id}")
                    return True
                else:
                    logger.error(f"Registration failed: {data.get('error')}")
                    return False
            else:
                logger.error(f"Registration failed with status {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Registration error: {e}", exc_info=True)
            return False
    
    def send_heartbeat(self):
        """Send heartbeat to master"""
        try:
            cpu_percent = psutil.cpu_percent(interval=None)  # Non-blocking, uses previous call
            memory_percent = psutil.virtual_memory().percent
            
            status = self.current_phase if self.current_job else 'idle'
            
            heartbeat_data = {
                'status': status,
                'cpu_percent': cpu_percent,
                'memory_percent': memory_percent,
                'current_speed': self.current_speed,
                'current_eta': self.current_eta
            }
            
            # Include current job info for reconnection recovery
            if self.current_job:
                heartbeat_data['current_job'] = {
                    'file_id': self.current_job['file_id'],
                    'filename': self.current_job['filename'],
                    'file_path': self.current_job.get('path'),      # Absolute path for validation
                    'file_size': self.current_job.get('size_bytes'), # File size for integrity check
                    'progress_percent': getattr(self, 'current_progress', 0),
                    'started_at': getattr(self, 'job_start_time', None),
                    'is_completed': getattr(self, 'job_completed_but_not_reported', False)
                }
            
            response = requests.post(
                f"{self.master_url}/api/worker/{self.worker_id}/heartbeat",
                json=heartbeat_data,
                timeout=5
            )
            
            # Handle reconnection if worker was lost
            if response.status_code == 404:
                logger.warning("Worker not found on master, attempting to re-register...")
                if self.register():
                    # Retry heartbeat after successful registration
                    response = requests.post(
                        f"{self.master_url}/api/worker/{self.worker_id}/heartbeat",
                        json=heartbeat_data,
                        timeout=5
                    )
            
            return response.status_code == 200
            
        except Exception as e:
            logger.warning(f"Heartbeat error: {e}")
            return False
    
    def request_job(self):
        """Request next job from master"""
        try:
            response = requests.get(
                f"{self.master_url}/api/worker/{self.worker_id}/job/request",
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                if data['success'] and data.get('job'):
                    return data['job']
            
            return None
            
        except Exception as e:
            logger.error(f"Error requesting job: {e}")
            return None
    
    def report_progress(self, file_id, percent, speed=None, eta=None, status=None):
        """Report progress to master"""
        try:
            # Update current progress and stats for heartbeat
            self.current_progress = percent
            if speed is not None:
                self.current_speed = speed
            if eta is not None:
                self.current_eta = eta
                
            progress_data = {
                'percent': percent,
                'speed': speed,
                'eta': eta
            }
            
            # Add status message if provided
            if status is not None:
                progress_data['status'] = status
                
            requests.post(
                f"{self.master_url}/api/worker/{self.worker_id}/job/{file_id}/progress",
                json=progress_data,
                timeout=5
            )
        except Exception as e:
            logger.warning(f"Error reporting progress: {e}")
    
    def report_completion(self, file_id, output_size, original_size):
        """Report job completion to master with retries"""
        completion_data = {
            'output_size': output_size,
            'original_size': original_size
        }
        
        # Keep trying to report completion - this work is valuable!
        max_retries = 100  # Try for a long time
        retry_delay = 30   # Wait 30 seconds between retries
        
        for attempt in range(max_retries):
            try:
                response = requests.post(
                    f"{self.master_url}/api/worker/{self.worker_id}/job/{file_id}/complete",
                    json=completion_data,
                    timeout=10
                )
                
                if response.status_code == 200:
                    logger.info(f"Successfully reported completion for job {file_id}")
                    return True
                elif response.status_code == 404:
                    # Worker not registered, try to re-register
                    logger.warning(f"Worker not found when reporting completion, re-registering...")
                    if self.register():
                        continue  # Retry with new registration
                else:
                    logger.warning(f"Completion report failed with status {response.status_code}, retrying...")
                    
            except Exception as e:
                logger.warning(f"Error reporting completion (attempt {attempt + 1}/{max_retries}): {e}")
            
            if attempt < max_retries - 1:
                logger.info(f"Retrying completion report in {retry_delay} seconds...")
                time.sleep(retry_delay)
        
        logger.error(f"Failed to report completion after {max_retries} attempts")
        return False
    
    def report_failure(self, file_id, error_message):
        """Report job failure to master"""
        try:
            requests.post(
                f"{self.master_url}/api/worker/{self.worker_id}/job/{file_id}/failed",
                json={'error': error_message},
                timeout=10
            )
        except Exception as e:
            logger.error(f"Error reporting failure: {e}")
    
    def process_job(self, job):
        """Process a transcoding job"""
        file_id = job['file_id']
        file_path = Path(job['path'])
        original_size = job['size_bytes']
        
        logger.info(f"Processing job {file_id}: {file_path}")
        logger.info("Downloading file from master...")
        self.current_phase = 'downloading'
        
        self.current_job = job
        self.job_start_time = datetime.now().isoformat()
        self.current_progress = 0
        
        try:
            # Create temp directory
            temp_dir = Path(self.config.get_temp_directory())
            temp_dir.mkdir(parents=True, exist_ok=True)
            
            temp_input = temp_dir / file_path.name
            
            # Download file from master
            logger.info(f"Downloading file {file_id} from master...")
            self.report_progress(file_id, 0, status="Starting download...", speed="-- MB/s", eta="--:--")
            
            # Optimized download with connection settings
            response = requests.get(
                f"{self.master_url}/api/worker/{self.worker_id}/file/{file_id}/download",
                stream=True,
                timeout=300,  # 5 minutes for large files
                headers={'Connection': 'keep-alive'}
            )
            
            if response.status_code != 200:
                raise Exception(f"Failed to download file: HTTP {response.status_code}")
            
            # Get file size from Content-Length header if available
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            # Save streamed file with progress tracking
            last_report_time = time.time()
            with open(temp_input, 'wb') as f:
                # Use larger chunk size for better performance (1MB chunks)
                for chunk in response.iter_content(chunk_size=1024*1024):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        # Report download progress with proper percentages
                        current_time = time.time()
                        if total_size > 0 and (current_time - last_report_time > 1.0):  # Update every 1 second
                            download_percent_actual = (downloaded / total_size) * 100
                            
                            # Calculate download speed and ETA
                            if hasattr(self, '_download_start_time'):
                                elapsed = current_time - self._download_start_time
                                if elapsed > 0:
                                    speed_bps = downloaded / elapsed
                                    speed_mbps = speed_bps / (1024 * 1024)
                                    eta_seconds = (total_size - downloaded) / speed_bps if speed_bps > 0 else 0
                                    
                                    # Format download speed for display
                                    download_speed = f"{speed_mbps:.1f} MB/s"
                                    
                                    # Format ETA for display  
                                    if eta_seconds > 0:
                                        eta_mins = int(eta_seconds // 60)
                                        eta_secs = int(eta_seconds % 60)
                                        download_eta = f"{eta_mins:02d}:{eta_secs:02d}"
                                    else:
                                        download_eta = "--:--"
                                    
                                    status_msg = f"Downloading {download_percent_actual:.1f}%"
                                else:
                                    download_speed = "-- MB/s"
                                    download_eta = "--:--"
                                    status_msg = f"Downloading {download_percent_actual:.1f}%"
                            else:
                                self._download_start_time = current_time
                                download_speed = "-- MB/s"
                                download_eta = "--:--"
                                status_msg = f"Downloading {download_percent_actual:.1f}%"
                            
                            # Report download progress - full 0-100% range for downloading phase
                            self.report_progress(file_id, download_percent_actual, 
                                               speed=download_speed,
                                               eta=download_eta,
                                               status=status_msg)
                            last_report_time = current_time
            
            logger.info(f"File downloaded successfully: {temp_input}")
            
            # Clean up download tracking
            if hasattr(self, '_download_start_time'):
                delattr(self, '_download_start_time')
            
            # Download complete - 100% for download phase
            self.report_progress(file_id, 100, status="Download complete", speed=None, eta=None)

            
            # Probe file
            logger.info("Probing file metadata...")
            self.report_progress(file_id, 0, status="Analyzing file...")
            metadata = MediaProbe.probe_file(temp_input)
            
            if not metadata or not metadata.get('video'):
                raise Exception("Failed to probe file or no video stream found")
            
            # Debug HDR metadata for troubleshooting
            hdr_debug = self._debug_hdr_metadata(metadata)
            
            # Check for dynamic HDR that cannot be preserved
            video = metadata['video']
            hdr_type = video.get('hdr', 'SDR')
            has_dynamic_hdr = video.get('hdr_dynamic', False)
            
            # Skip Dolby Vision (always dynamic) and dynamic HDR10+
            should_skip = False
            skip_reason = ""
            
            if hdr_type == 'Dolby Vision':
                should_skip = True
                skip_reason = "Dolby Vision dynamic metadata cannot be preserved (quality protection)"
            elif hdr_type == 'HDR10+' and has_dynamic_hdr:
                should_skip = True  
                skip_reason = "HDR10+ dynamic metadata cannot be preserved (quality protection)"
            
            if should_skip:
                error_msg = f"Skipped: {skip_reason}"
                logger.warning(f"Skipping file: Contains {hdr_type} - {skip_reason}")
                
                # Report as failed with skip reason
                response = requests.put(f"{self.master_url}/api/file/{file_id}/complete", json={
                    'success': False,
                    'error': error_msg,
                    'worker_id': self.worker_id
                })
                return
            
            # Determine settings
            settings = self._determine_settings(metadata)
            logger.info(f"Encoding settings: CRF={settings['crf']}, Opus={settings['opus_bitrate']}k")
            
            # Get transcoding settings from job (with fallback to environment variables)
            transcoding_settings = job.get('transcoding_settings', {})
            skip_audio_transcode = transcoding_settings.get('skip_audio_transcode', 
                                                          os.getenv('SKIP_AUDIO_TRANSCODE', 'false').lower() == 'true')
            
            if skip_audio_transcode:
                logger.info("Audio transcoding disabled - will copy all audio streams")
            else:
                logger.info("Audio transcoding enabled - will transcode to Opus")
            
            # Switch to processing phase when transcoding starts
            self.current_phase = 'processing'
            
            # Transcode with progress callback - start processing phase at 0%
            self.report_progress(file_id, 0, status="Starting transcoding...", speed=0.0, eta=None)
            temp_output = self._transcode(temp_input, metadata, settings, file_id, transcoding_settings)
            upload_failed = False  # Track upload status for cleanup
            
            if not temp_output or not temp_output.exists():
                raise Exception("Transcoding failed")
            
            # Check if worthwhile
            output_size = temp_output.stat().st_size
            savings_bytes = original_size - output_size
            savings_percent = (savings_bytes / original_size * 100) if original_size > 0 else 0
            
            if output_size >= original_size or savings_percent < 5:
                logger.warning(f"Not worth transcoding: {savings_percent:.1f}% savings")
                self.report_failure(file_id, f"Not worth transcoding: Output would be {abs(savings_percent):.1f}% {'larger' if output_size > original_size else 'smaller'}")
                return
            
            # Upload result to master
                logger.info(f"Uploading result to master...")
                
                # Start uploading phase at 0%
                self.current_phase = 'uploading'
                self.report_progress(file_id, 0, status="Uploading result...")
                
                upload_success = False
                file_size = temp_output.stat().st_size
                upload_start_time = time.time()
                
                # Create a custom upload function with progress tracking
                def upload_with_progress():
                    # Keep reference to worker client for progress reporting
                    worker_client = self
                    
                    with open(temp_output, 'rb') as f:
                        # Read file in chunks and track progress
                        uploaded = 0
                        chunk_size = 8192  # 8KB chunks
                        
                        class ProgressFile:
                            def __init__(self, file_obj):
                                self.file_obj = file_obj
                                self.uploaded = 0
                            
                            def read(self, size=-1):
                                chunk = self.file_obj.read(size)
                                if chunk:
                                    self.uploaded += len(chunk)
                                    progress = min(100, (self.uploaded / file_size) * 100)
                                    
                                    # Calculate upload speed and ETA
                                    elapsed = time.time() - upload_start_time
                                    if elapsed > 0:
                                        speed = self.uploaded / elapsed  # bytes per second
                                        speed_mb = speed / (1024 * 1024)  # MB/s
                                        
                                        if speed > 0:
                                            remaining_bytes = file_size - self.uploaded
                                            eta_seconds = remaining_bytes / speed
                                            eta_str = f"{int(eta_seconds//60):02d}:{int(eta_seconds%60):02d}"
                                        else:
                                            eta_str = "--:--"
                                        
                                        status_msg = f"Uploading: {speed_mb:.1f} MB/s, ETA: {eta_str}"
                                    else:
                                        status_msg = "Uploading result..."
                                    
                                    worker_client.report_progress(file_id, progress, status=status_msg)
                                
                                return chunk
                        
                        progress_file = ProgressFile(f)
                        files = {'file': (temp_output.name, progress_file, 'application/octet-stream')}
                        
                        return requests.post(
                            f"{worker_client.master_url}/api/file/{file_id}/result",
                            files=files,
                            timeout=300  # 5 minutes for upload
                        )
                
                response = upload_with_progress()
                
                if response.status_code == 200:
                    result = response.json()
                    if result.get('success'):
                        logger.info(f"File uploaded successfully, master confirmed save")
                        upload_success = True
                        
                        # Only delete temp output after successful upload
                        if temp_output.exists():
                            logger.debug(f"Removing temp output after successful upload: {temp_output}")
                            temp_output.unlink()
                        
                        # Report upload completion - 100% for uploading phase
                        self.report_progress(file_id, 100, status="Upload completed!")
                        completion_success = self.report_completion(file_id, output_size, original_size)
                        
                        if completion_success:
                            logger.info(f"Job {file_id} completed successfully ({savings_percent:.1f}% savings)")
                        else:
                            logger.error(f"Job {file_id} completed but could not notify master - will retry via heartbeat")
                            # Mark job as completed but not reported for heartbeat recovery
                            self.job_completed_but_not_reported = True
                    else:
                        upload_failed = True
                        raise Exception(f"Master reported upload failure: {result.get('error', 'Unknown error')}")
                else:
                    upload_failed = True
                    raise Exception(f"Failed to upload result: HTTP {response.status_code}")

            
        except Exception as e:
            logger.error(f"Job {file_id} failed: {e}", exc_info=True)
            self.report_failure(file_id, str(e))
        
        finally:
            self.current_job = None
            self.current_phase = 'idle'
            self.current_progress = 0
            self.job_start_time = None
            self.job_completed_but_not_reported = False
            # Cleanup temp files
            try:
                if temp_input.exists():
                    logger.debug(f"Removing temp input: {temp_input}")
                    temp_input.unlink()
                # Preserve transcoded files if upload failed
                if 'temp_output' in locals() and temp_output.exists():
                    # Check if we're in an error state (upload failed)
                    if 'upload_failed' in locals() and upload_failed:
                        # Move to failed_uploads directory instead of deleting
                        failed_uploads_dir = Path(self.config.get_temp_directory()) / 'failed_uploads'
                        failed_uploads_dir.mkdir(exist_ok=True)
                        
                        # Include job ID and timestamp in filename
                        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                        failed_filename = f"job_{file_id}_{timestamp}_{temp_output.name}"
                        failed_path = failed_uploads_dir / failed_filename
                        
                        logger.warning(f"Upload failed - preserving transcoded file: {temp_output} -> {failed_path}")
                        temp_output.rename(failed_path)
                        
                        # Create metadata file with job info
                        metadata_path = failed_path.with_suffix('.metadata')
                        with open(metadata_path, 'w') as f:
                            f.write(f"job_id={file_id}\n")
                            f.write(f"original_path={file_path}\n")
                            f.write(f"failed_at={datetime.now().isoformat()}\n")
                            f.write(f"worker_id={self.worker_id}\n")
                        
                        logger.info(f"Transcoded file preserved for retry: {failed_path}")
                    else:
                        # Normal cleanup - file was successfully processed or upload succeeded
                        logger.debug(f"Removing temp output: {temp_output}")
                        temp_output.unlink()                # Clean up any other files left in temp directory
                temp_dir = Path(self.config.get_temp_directory())
                if temp_dir.exists():
                    for item in temp_dir.iterdir():
                        try:
                            # Only clean up files, not the directory itself
                            if item.is_file():
                                logger.debug(f"Removing leftover file: {item}")
                                item.unlink()
                        except Exception as cleanup_error:
                            logger.warning(f"Failed to cleanup {item}: {cleanup_error}")
            except Exception as e:
                logger.warning(f"Error during cleanup: {e}")
    
    def _determine_settings(self, metadata):
        """Determine encoding settings based on metadata"""
        # Video settings
        codec = metadata['video'].get('codec', 'h264')
        bitdepth = metadata['video'].get('bitdepth', 8)
        hdr_raw = metadata['video'].get('hdr', 'SDR')
        resolution = metadata['video']['resolution']
        bitrate = metadata['video'].get('bitrate', 0)
        
        # Map specific HDR types to generic categories for quality lookup
        if hdr_raw in ['HDR10', 'HDR10+', 'HLG']:
            hdr = 'HDR'
        else:
            hdr = hdr_raw  # 'SDR' or other
        
        # Determine bitrate category
        bitrate_mbps = bitrate / 1_000_000 if bitrate else 5
        if bitrate_mbps < 1.5:
            bitrate_category = '1M'
        elif bitrate_mbps < 3:
            bitrate_category = '2M'
        elif bitrate_mbps < 5:
            bitrate_category = '4M'
        elif bitrate_mbps < 7:
            bitrate_category = '6M'
        elif bitrate_mbps < 9:
            bitrate_category = '8M'
        elif bitrate_mbps < 12:
            bitrate_category = '10M'
        elif bitrate_mbps < 17:
            bitrate_category = '15M'
        elif bitrate_mbps < 25:
            bitrate_category = '20M'
        elif bitrate_mbps < 35:
            bitrate_category = '30M'
        else:
            bitrate_category = '40M+'
        
        # Debug logging for quality lookup
        logger.info(f"Quality lookup: codec={codec}, bitdepth={bitdepth}bit, hdr={hdr}, resolution={resolution}, bitrate={bitrate_mbps:.1f}M->category={bitrate_category}")
        
        # Get CRF from lookup table
        crf = self.quality_lookup.get_video_crf(codec, bitdepth, hdr, resolution, bitrate_category)
        
        # Audio settings
        audio_codec = metadata['audio'][0]['codec'] if metadata['audio'] else 'aac'
        audio_channels = metadata['audio'][0]['channels'] if metadata['audio'] else 2
        audio_bitrate = metadata['audio'][0].get('bitrate', 0) if metadata['audio'] else 0
        audio_bitrate_mbps = audio_bitrate / 1000 if audio_bitrate else 128
        
        # Determine audio bitrate category
        if audio_bitrate_mbps < 96:
            audio_category = '64k'
        elif audio_bitrate_mbps < 160:
            audio_category = '128k'
        elif audio_bitrate_mbps < 224:
            audio_category = '192k'
        elif audio_bitrate_mbps < 320:
            audio_category = '256k'
        elif audio_bitrate_mbps < 450:
            audio_category = '384k'
        else:
            audio_category = '512k'
        
        opus_bitrate = self.quality_lookup.get_opus_bitrate(audio_codec, audio_channels, audio_category)
        
        return {
            'crf': crf,
            'opus_bitrate': opus_bitrate
        }
    
    def _transcode(self, input_file, metadata, settings, file_id, transcoding_settings=None):
        """Transcode video with enhanced HDR support and error handling"""
        if transcoding_settings is None:
            transcoding_settings = {}
        output_file = input_file.parent / f"{input_file.stem}_av1{input_file.suffix}"
        
        # Build ffmpeg command with selective stream mapping
        preset = str(self.config.get('transcoding.svt_av1_preset', 0))  # Default to 0 (highest quality)
        
        # Check if audio transcoding should be skipped
        skip_audio_transcode = transcoding_settings.get('skip_audio_transcode', 
                                                       os.getenv('SKIP_AUDIO_TRANSCODE', 'false').lower() == 'true')
        
        # Get audio info for channel mapping
        audio_channels = metadata.get('audio', [{}])[0].get('channels', 2) if metadata.get('audio') else 2
        audio_streams_count = len(metadata.get('audio', []))
        
        cmd = [
            'ffmpeg', '-i', str(input_file),
            # Map only the first video stream (avoid thumbnails/attachments)
            '-map', '0:V:0',  # First video stream
        ]
        
        # Audio handling - either copy all or transcode first stream
        if skip_audio_transcode:
            # Copy all audio streams without transcoding
            cmd.extend([
                '-map', '0:a',  # Map all audio streams
                '-c:a', 'copy',  # Copy audio without transcoding
            ])
            logger.info(f"Copying {audio_streams_count} audio stream(s) without transcoding (SKIP_AUDIO_TRANSCODE=true)")
        else:
            # Original transcoding behavior - map and transcode first audio stream
            cmd.extend([
                '-map', '0:a:0?',  # First audio stream (optional)
                '-c:a', 'libopus',
                '-b:a', f"{settings['opus_bitrate']}k",
            ])
            logger.info(f"Transcoding first audio stream to Opus {settings['opus_bitrate']}k")
        
        # Add subtitles and video encoding
        cmd.extend([
            '-map', '0:s?',    # All subtitle streams (optional)
            # Video encoding
            '-c:v', 'libsvtav1',
            '-preset', preset,
            '-crf', str(settings['crf']),
        ])
        
        # Handle problematic audio channel layouts (only when transcoding audio)
        if not skip_audio_transcode and audio_channels > 2:
            # Force stereo downmix for complex layouts to avoid libopus issues
            logger.info(f"Audio has {audio_channels} channels, downmixing to stereo to avoid libopus layout issues")
            cmd.extend(['-ac', '2', '-af', 'pan=stereo|FL=0.5*FL+0.707*FC+0.5*BL+0.5*SL|FR=0.5*FR+0.707*FC+0.5*BR+0.5*SR'])
        elif not skip_audio_transcode:
            logger.info(f"Audio has {audio_channels} channels, using direct Opus encoding")
        
        # Frame rate validation for SVT-AV1
        video_info = metadata.get('video', {})
        fps = video_info.get('fps', 0)
        if fps > 240:
            logger.warning(f"Frame rate {fps} fps exceeds SVT-AV1 limit, capping at 60fps")
            cmd.extend(['-r', '60'])
        elif fps > 120:
            logger.warning(f"High frame rate {fps} fps detected, limiting to 120fps for stability")  
            cmd.extend(['-r', '120'])
        
        # Add subtitle and metadata handling
        cmd.extend([
            '-c:s', 'copy',
            '-map_metadata', '0',
            # Enable progress reporting
            '-stats',
            '-stats_period', '2'
        ])
        
        # HDR parameters will be inserted here if needed
        # Output file will be added at the very end
        
        # Add HDR color parameters if needed with validation
        video_info = metadata.get('video', {})
        hdr_type = video_info.get('hdr', 'SDR')
        color_transfer = video_info.get('color_transfer', '')
        color_space = video_info.get('color_space', '')
        
        # Validate and normalize HDR parameters
        hdr_params_added = False
        if hdr_type in ['HDR10', 'HDR10+']:
            logger.info(f"Processing {hdr_type} content: transfer={color_transfer}, space={color_space}")
            
            # Validate color parameters
            valid_transfers = ['smpte2084', 'arib-std-b67', 'smpte428', 'bt2020-10', 'bt2020-12']
            valid_spaces = ['bt2020nc', 'bt2020c', 'bt2020_ncl', 'bt2020_cl']
            
            # Normalize and validate color_transfer
            normalized_transfer = color_transfer.lower().replace('-', '').replace('_', '')
            if any(normalized_transfer in vt.replace('-', '').replace('_', '') for vt in valid_transfers):
                # Use smpte2084 for PQ (most common HDR10)
                if 'smpte2084' in normalized_transfer or 'pq' in normalized_transfer:
                    color_transfer = 'smpte2084'
                # Use arib-std-b67 for HLG
                elif 'arib' in normalized_transfer or 'hlg' in normalized_transfer:
                    color_transfer = 'arib-std-b67'
                else:
                    color_transfer = 'smpte2084'  # Default to PQ
                    
                # Normalize and validate color_space  
                normalized_space = color_space.lower().replace('-', '').replace('_', '')
                if any(normalized_space in vs.replace('-', '').replace('_', '') for vs in valid_spaces):
                    if 'nc' in normalized_space:
                        color_space = 'bt2020nc'
                    else:
                        color_space = 'bt2020nc'  # Default to non-constant
                else:
                    color_space = 'bt2020nc'  # Default
                
                # Add validated HDR parameters
                cmd.extend([
                    '-color_primaries', 'bt2020',
                    '-color_trc', color_transfer,
                    '-colorspace', color_space
                ])
                hdr_params_added = True
                logger.info(f"Added validated HDR parameters for {hdr_type}: primaries=bt2020, trc={color_transfer}, space={color_space}")
            else:
                logger.warning(f"Invalid HDR parameters detected for {hdr_type}, encoding as SDR: transfer={color_transfer}, space={color_space}")
        
        # Log HDR processing decision
        if hdr_type not in ['SDR']:
            if hdr_params_added:
                logger.info(f"HDR encoding enabled for {hdr_type}")
            else:
                logger.warning(f"HDR content detected ({hdr_type}) but encoding as SDR due to parameter issues")
        
        # Log encoding details for debugging
        logger.info(f"Encoding {input_file.name}: HDR={hdr_type}, bitdepth={video_info.get('bitdepth', 8)}, preset={preset}, CRF={settings['crf']}")
        
        # Add output file at the very end
        cmd.extend(['-y', str(output_file)])
        
        import subprocess
        duration = metadata['format']['duration']
        
        # Log the FFmpeg command for debugging
        logger.info(f"FFmpeg command: {' '.join(cmd)}")
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1
        )
        
        # Monitor progress and collect stderr
        last_report = 0
        current_fps = 0.0
        stderr_lines = []
        
        # Add timeout and activity tracking
        import time
        start_time = time.time()
        last_activity = start_time
        
        # Count lines to see if FFmpeg is producing any output at all
        line_count = 0
        
        for line in process.stderr:
            line_count += 1
            stderr_lines.append(line)
            last_activity = time.time()
            
            # Log first 10 lines and every 100 lines to see FFmpeg activity
            if line_count <= 10 or line_count % 100 == 0:
                logger.info(f"FFmpeg line #{line_count}: {line.strip()}")
            
            # Debug: Log any line that might be progress-related
            if any(keyword in line.lower() for keyword in ['time=', 'frame=', 'fps=', 'speed=', 'progress']):
                logger.info(f"FFmpeg PROGRESS #{line_count}: {line.strip()}")
            
            # Check for FFmpeg hanging (no output for 60 seconds)
            if time.time() - last_activity > 60:
                logger.error(f"FFmpeg appears to be hanging - no output for 60 seconds (total lines: {line_count})")
                process.terminate()
                break
            
            # Try to parse progress from either time= or frame= 
            if 'time=' in line or 'frame=' in line:
                try:
                    percent = 0
                    current_fps = 0.0
                    speed_multiplier = 1.0
                    eta_seconds = 0
                    
                    # Parse FPS from FFmpeg output
                    if 'fps=' in line:
                        fps_str = line.split('fps=')[1].split()[0].strip()
                        current_fps = float(fps_str)
                    
                    # Parse speed multiplier
                    if 'speed=' in line and 'N/A' not in line.split('speed=')[1].split()[0]:
                        speed_str = line.split('speed=')[1].split('x')[0].strip()
                        speed_multiplier = float(speed_str)
                    
                    # Try time-based progress first
                    if 'time=' in line and 'N/A' not in line.split('time=')[1].split()[0]:
                        time_str = line.split('time=')[1].split()[0]
                        if ':' in time_str:  # Format: HH:MM:SS.ss
                            h, m, s = time_str.split(':')
                            current_time = int(h) * 3600 + int(m) * 60 + float(s)
                            percent = min(100, (current_time / duration * 100))
                            
                            # Calculate ETA based on time
                            remaining_time = duration - current_time
                            eta_seconds = int(remaining_time / speed_multiplier) if speed_multiplier > 0 else 0
                    
                    # Fallback to frame-based progress if time is N/A
                    elif 'frame=' in line:
                        frame_str = line.split('frame=')[1].split()[0].strip()
                        current_frame = int(frame_str)
                        
                        # Estimate progress based on frames (assuming 24fps average)
                        video_fps = metadata.get('video', {}).get('fps', 24)
                        total_frames = int(duration * video_fps)
                        if total_frames > 0:
                            percent = min(100, (current_frame / total_frames * 100))
                            
                            # Calculate ETA based on current fps
                            if current_fps > 0:
                                remaining_frames = total_frames - current_frame
                                eta_seconds = int(remaining_frames / current_fps)
                    
                    # Report every 2 seconds or 1% change
                    current_time_check = time.time()
                    if current_time_check - last_report > 2 or abs(percent - self.current_progress) > 1:
                        self.report_progress(file_id, percent, speed=current_fps, eta=eta_seconds)
                        last_report = current_time_check
                        logger.info(f"Progress reported: {percent:.1f}% at {current_fps:.1f} fps, ETA: {eta_seconds}s")
                        
                except Exception as e:
                    logger.debug(f"Error parsing progress line: {e} - Line: {line.strip()}")
        
        returncode = process.wait()
        
        if returncode != 0:
            stderr_output = ''.join(stderr_lines)
            logger.error(f"FFmpeg failed with return code {returncode}")
            logger.error(f"FFmpeg stderr output: {stderr_output}")
            
            # Check for specific error patterns
            hdr_error_patterns = [
                'color_trc', 'color_primaries', 'colorspace', 'color_range',
                'Invalid color', 'Unsupported color', 'color transfer',
                'bt2020', 'smpte2084', 'arib-std-b67'
            ]
            
            audio_error_patterns = [
                'Invalid channel layout', 'libopus', 'mapping family',
                'channel layout', 'audio encoder', 'Invalid argument'
            ]
            
            framerate_error_patterns = [
                'maximum allowed frame rate', 'frame rate is 240 fps',
                'fps exceeds', 'framerate'
            ]
            
            is_hdr_error = any(pattern in stderr_output.lower() for pattern in hdr_error_patterns)
            is_audio_error = any(pattern in stderr_output.lower() for pattern in audio_error_patterns)
            is_framerate_error = any(pattern in stderr_output.lower() for pattern in framerate_error_patterns)
            used_hdr_params = hdr_params_added and hdr_type in ['HDR10', 'HDR10+']
            
            # Analyze error type and determine retry strategy
            should_retry = False
            retry_reason = ""
            
            if used_hdr_params and (is_hdr_error or returncode in [1, 234]):
                should_retry = True
                retry_reason = f"HDR parameter incompatibility (code: {returncode})"
            elif is_audio_error and not skip_audio_transcode:
                # Audio errors when transcoding - try fallback with same settings
                logger.error(f"Audio encoding error detected: {stderr_output}")
                retry_reason = "Audio channel layout incompatibility"
                should_retry = True
            elif is_framerate_error:
                # Frame rate errors should be fixed by our rate limiting
                logger.error(f"Frame rate error detected: {stderr_output}")
                retry_reason = "Frame rate exceeds encoder limits"
                
            if should_retry:
                logger.warning(f"FFmpeg error {returncode}: {retry_reason}")
                logger.warning(f"Error types detected - HDR: {is_hdr_error}, Audio: {is_audio_error}, FPS: {is_framerate_error}")
                logger.warning(f"Retrying with fallback encoding...")
                return self._transcode_fallback(input_file, metadata, settings, file_id, transcoding_settings)
            
            # Enhanced error message with context
            error_context = []
            if hdr_type != 'SDR':
                error_context.append(f"HDR_TYPE={hdr_type}")
            if used_hdr_params:
                error_context.append(f"HDR_PARAMS=enabled")
            
            context_str = f" ({', '.join(error_context)})" if error_context else ""
            raise Exception(f"FFmpeg failed with code {returncode}{context_str}: {stderr_output}")
        
        return output_file
    
    def _transcode_fallback(self, input_file, metadata, settings, file_id, transcoding_settings=None):
        """Fallback transcoding without HDR parameters"""
        if transcoding_settings is None:
            transcoding_settings = {}
        logger.info("=== HDR FALLBACK TRANSCODING ===")
        video_info = metadata.get('video', {})
        hdr_type = video_info.get('hdr', 'SDR')
        logger.warning(f"Transcoding {hdr_type} content as SDR due to FFmpeg HDR parameter issues")
        logger.warning(f"Original color info: transfer={video_info.get('color_transfer')}, space={video_info.get('color_space')}")
        
        output_file = input_file.parent / f"{input_file.stem}_av1{input_file.suffix}"
        
        # Build basic ffmpeg command without HDR parameters (same mapping as main method)
        preset = str(self.config.get('transcoding.svt_av1_preset', 0))  # Default to 0 (highest quality)
        
        # Check if audio transcoding should be skipped (same as main method)
        skip_audio_transcode = transcoding_settings.get('skip_audio_transcode', 
                                                       os.getenv('SKIP_AUDIO_TRANSCODE', 'false').lower() == 'true')
        
        # Get audio info for channel mapping  
        audio_channels = metadata.get('audio', [{}])[0].get('channels', 2) if metadata.get('audio') else 2
        audio_streams_count = len(metadata.get('audio', []))
        
        cmd = [
            'ffmpeg', '-i', str(input_file),
            # Map only the first video stream (avoid thumbnails/attachments)
            '-map', '0:V:0',  # First video stream
        ]
        
        # Audio handling - either copy all or transcode first stream (same as main method)
        if skip_audio_transcode:
            # Copy all audio streams without transcoding
            cmd.extend([
                '-map', '0:a',  # Map all audio streams
                '-c:a', 'copy',  # Copy audio without transcoding
            ])
            logger.info(f"Fallback: Copying {audio_streams_count} audio stream(s) without transcoding")
        else:
            # Original transcoding behavior - map and transcode first audio stream
            cmd.extend([
                '-map', '0:a:0?',  # First audio stream (optional)
                '-c:a', 'libopus',
                '-b:a', f"{settings['opus_bitrate']}k",
            ])
            logger.info(f"Fallback: Transcoding first audio stream to Opus {settings['opus_bitrate']}k")
        
        # Add subtitles and video encoding
        cmd.extend([
            '-map', '0:s?',    # All subtitle streams (optional)
            # Video encoding
            '-c:v', 'libsvtav1',
            '-preset', preset,
            '-crf', str(settings['crf']),
        ])
        
        # Handle problematic audio channel layouts (only when transcoding audio)
        if not skip_audio_transcode and audio_channels > 2:
            # Force stereo downmix for complex layouts to avoid libopus issues
            logger.info(f"Fallback: Audio has {audio_channels} channels, downmixing to stereo")
            cmd.extend(['-ac', '2', '-af', 'pan=stereo|FL=0.5*FL+0.707*FC+0.5*BL+0.5*SL|FR=0.5*FR+0.707*FC+0.5*BR+0.5*SR'])
        
        # Frame rate validation for SVT-AV1 (same as main method)
        fps = video_info.get('fps', 0)
        if fps > 240:
            logger.warning(f"Fallback: Frame rate {fps} fps exceeds SVT-AV1 limit, capping at 60fps")
            cmd.extend(['-r', '60'])
        elif fps > 120:
            logger.warning(f"Fallback: High frame rate {fps} fps detected, limiting to 120fps")  
            cmd.extend(['-r', '120'])
        
        # Add subtitle and metadata handling
        cmd.extend([
            '-c:s', 'copy',
            '-map_metadata', '0',
            '-y', str(output_file)
        ])
        
        import subprocess
        duration = metadata['format']['duration']
        
        logger.info(f"Fallback FFmpeg command: {' '.join(cmd)}")
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1
        )
        
        # Monitor progress and collect stderr
        last_report = 0
        current_fps = 0.0
        stderr_lines = []
        
        for line in process.stderr:
            stderr_lines.append(line)
            if 'time=' in line:
                try:
                    # Parse time
                    time_str = line.split('time=')[1].split()[0]
                    h, m, s = time_str.split(':')
                    current_time = int(h) * 3600 + int(m) * 60 + float(s)
                    # Fallback processing phase uses full 0-100% range  
                    percent = min(100, (current_time / duration * 100))
                    
                    # Parse speed (fps)
                    if 'speed=' in line:
                        speed_str = line.split('speed=')[1].split('x')[0].strip()
                        speed_multiplier = float(speed_str)
                        current_fps = speed_multiplier * 25
                    
                    # Calculate ETA
                    remaining_time = duration - current_time
                    eta_seconds = int(remaining_time / speed_multiplier) if speed_multiplier > 0 else 0
                    
                    # Report every 2 seconds
                    if time.time() - last_report > 2:
                        self.report_progress(file_id, percent, speed=current_fps, eta=eta_seconds)
                        last_report = time.time()
                except Exception as e:
                    pass
        
        returncode = process.wait()
        
        if returncode != 0:
            stderr_output = ''.join(stderr_lines)
            logger.error(f"Fallback FFmpeg stderr output: {stderr_output}")
            raise Exception(f"Fallback FFmpeg also failed with code {returncode}: {stderr_output}")
        
        return output_file
    
    def _debug_hdr_metadata(self, metadata):
        """Debug HDR metadata for troubleshooting"""
        video_info = metadata.get('video', {})
        
        debug_info = {
            'hdr_type': video_info.get('hdr', 'SDR'),
            'hdr_dynamic': video_info.get('hdr_dynamic', False),
            'color_transfer': video_info.get('color_transfer', ''),
            'color_space': video_info.get('color_space', ''),
            'bitdepth': video_info.get('bitdepth', 8),
            'codec': video_info.get('codec', ''),
            'resolution': video_info.get('resolution', ''),
        }
        
        # Only show debug info for HDR content or if debug is enabled
        hdr_debug_enabled = os.getenv('HDR_DEBUG', 'false').lower() == 'true'
        
        if debug_info['hdr_type'] != 'SDR' or hdr_debug_enabled:
            logger.info("=== HDR DEBUG INFO ===")
            for key, value in debug_info.items():
                logger.info(f"{key}: {value}")
        
        # Check for problematic combinations
        warnings = []
        if debug_info['hdr_type'] != 'SDR':
            if not debug_info['color_transfer']:
                warnings.append("Missing color_transfer for HDR content")
            if not debug_info['color_space']:
                warnings.append("Missing color_space for HDR content")
            if debug_info['bitdepth'] == 8:
                warnings.append("HDR content with 8-bit depth (unusual)")
                
        if warnings:
            logger.warning("HDR metadata warnings:")
            for warning in warnings:
                logger.warning(f"  - {warning}")
                
        return debug_info
    
    def run(self):
        """Main worker loop"""
        # Register with master
        if not self.register():
            logger.error("Failed to register with master")
            return
        
        self.is_running = True
        
        # Start heartbeat thread
        heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        heartbeat_thread.start()
        
        # Check for failed uploads to retry
        logger.info("Checking for failed uploads to retry...")
        self._retry_failed_uploads()
        
        logger.info("Worker started, waiting for jobs...")
        
        while not self.shutdown_event.is_set() and self.is_running:
            try:
                # Request job if idle
                if not self.current_job:
                    job = self.request_job()
                    if job:
                        self.process_job(job)
                    else:
                        time.sleep(5)  # Wait before requesting again
                
            except Exception as e:
                logger.error(f"Error in worker loop: {e}", exc_info=True)
                time.sleep(5)
        
        logger.info("Worker stopped")
    
    def _heartbeat_loop(self):
        """Background thread for sending heartbeats"""
        retry_counter = 0
        while not self.shutdown_event.is_set() and self.is_running:
            try:
                # Call cpu_percent to update for next heartbeat
                psutil.cpu_percent(interval=None)
                time.sleep(10)  # Wait 10 seconds
                self.send_heartbeat()
                
                # Check for failed uploads to retry every 10 heartbeats (100 seconds)
                retry_counter += 1
                if retry_counter >= 10:
                    retry_counter = 0
                    self._retry_failed_uploads()
                    
            except Exception as e:
                logger.warning(f"Heartbeat loop error: {e}")
                time.sleep(10)

def main():
    """Main entry point"""
    if len(sys.argv) < 2:
        print("Usage: worker_client.py <master_url>")
        print("Example: worker_client.py http://192.168.1.100:8090")
        sys.exit(1)
    
    master_url = sys.argv[1]
    
    worker = WorkerClient(master_url)
    
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        worker.shutdown_event.set()
        worker.is_running = False
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    worker.run()

if __name__ == '__main__':
    main()
