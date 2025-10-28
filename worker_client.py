#!/usr/bin/env python3
"""
Worker Client - Connects to master server and processes transcoding jobs
"""

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
                    'version': '1.0.0'
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
            
            status = 'processing' if self.current_job else 'idle'
            
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
                    'progress_percent': getattr(self, 'current_progress', 0),
                    'started_at': getattr(self, 'job_start_time', None)
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
    
    def report_progress(self, file_id, percent, speed=None, eta=None):
        """Report progress to master"""
        try:
            # Update current progress and stats for heartbeat
            self.current_progress = percent
            if speed is not None:
                self.current_speed = speed
            if eta is not None:
                self.current_eta = eta
                
            requests.post(
                f"{self.master_url}/api/worker/{self.worker_id}/job/{file_id}/progress",
                json={
                    'percent': percent,
                    'speed': speed,
                    'eta': eta
                },
                timeout=5
            )
        except Exception as e:
            logger.warning(f"Error reporting progress: {e}")
    
    def report_completion(self, file_id, output_size, original_size):
        """Report job completion to master"""
        try:
            response = requests.post(
                f"{self.master_url}/api/worker/{self.worker_id}/job/{file_id}/complete",
                json={
                    'output_size': output_size,
                    'original_size': original_size
                },
                timeout=10
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Error reporting completion: {e}")
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
        
        # Check if file distribution mode is enabled
        file_distribution_mode = os.environ.get('FILE_DISTRIBUTION_MODE', 'false').lower() == 'true'
        
        logger.info(f"Processing job {file_id}: {file_path}")
        if file_distribution_mode:
            logger.info("File distribution mode: will download file from master")
        self.current_job = job
        self.job_start_time = datetime.now().isoformat()
        self.current_progress = 0
        
        try:
            # Create temp directory
            temp_dir = Path(self.config.get_temp_directory())
            temp_dir.mkdir(parents=True, exist_ok=True)
            
            temp_input = temp_dir / file_path.name
            
            # In file distribution mode, download from master
            if file_distribution_mode:
                logger.info(f"Downloading file {file_id} from master...")
                self.report_progress(file_id, 2)
                
                response = requests.get(
                    f"{self.master_url}/api/worker/{self.worker_id}/file/{file_id}/download",
                    stream=True,
                    timeout=300  # 5 minutes for large files
                )
                
                if response.status_code != 200:
                    raise Exception(f"Failed to download file: HTTP {response.status_code}")
                
                # Save streamed file
                with open(temp_input, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                
                logger.info(f"File downloaded successfully: {temp_input}")
            else:
                # Shared storage mode - copy from network share
                logger.info(f"Copying to temp: {file_path} -> {temp_input}")
                
                import shutil
                shutil.copy2(file_path, temp_input)

            
            # Probe file
            logger.info("Probing file metadata...")
            self.report_progress(file_id, 5)
            metadata = MediaProbe.probe_file(temp_input)
            
            if not metadata or not metadata.get('video'):
                raise Exception("Failed to probe file or no video stream found")
            
            # Determine settings
            settings = self._determine_settings(metadata)
            logger.info(f"Encoding settings: CRF={settings['crf']}, Opus={settings['opus_bitrate']}k")
            
            # Transcode with progress callback
            self.report_progress(file_id, 0)  # Start at 0%
            temp_output = self._transcode(temp_input, metadata, settings, file_id)
            
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
            
            # File distribution mode: upload result to master
            if file_distribution_mode:
                logger.info(f"Uploading result to master...")
                self.report_progress(file_id, 95)
                
                upload_success = False
                with open(temp_output, 'rb') as f:
                    files = {'file': (temp_output.name, f, 'application/octet-stream')}
                    response = requests.post(
                        f"{self.master_url}/api/file/{file_id}/result",
                        files=files,
                        timeout=300  # 5 minutes for upload
                    )
                
                if response.status_code == 200:
                    result = response.json()
                    if result.get('success'):
                        logger.info(f"File uploaded successfully, master confirmed save")
                        upload_success = True
                        
                        # Only delete temp output after successful upload
                        if temp_output.exists():
                            logger.debug(f"Removing temp output after successful upload: {temp_output}")
                            temp_output.unlink()
                        
                        # Report completion
                        self.report_progress(file_id, 100)
                        self.report_completion(file_id, output_size, original_size)
                        logger.info(f"Job {file_id} completed successfully ({savings_percent:.1f}% savings)")
                    else:
                        raise Exception(f"Master reported upload failure: {result.get('error', 'Unknown error')}")
                else:
                    raise Exception(f"Failed to upload result: HTTP {response.status_code}")
            
            else:
                # Shared storage mode: replace file locally
                self.report_progress(file_id, 95)
                self._replace_original(file_path, temp_output)
                
                # Report completion
                self.report_progress(file_id, 100)
                self.report_completion(file_id, output_size, original_size)
                
                logger.info(f"Job {file_id} completed successfully ({savings_percent:.1f}% savings)")

            
        except Exception as e:
            logger.error(f"Job {file_id} failed: {e}", exc_info=True)
            self.report_failure(file_id, str(e))
        
        finally:
            self.current_job = None
            self.current_progress = 0
            self.job_start_time = None
            # Cleanup temp files
            try:
                if temp_input.exists():
                    logger.debug(f"Removing temp input: {temp_input}")
                    temp_input.unlink()
                # Only delete temp_output if it still exists (not already deleted after successful upload)
                if 'temp_output' in locals() and temp_output.exists():
                    logger.warning(f"Removing temp output (upload may have failed): {temp_output}")
                    temp_output.unlink()
                
                # Clean up any other files left in temp directory
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
        bitdepth = metadata['video'].get('bit_depth', 8)
        hdr = metadata['video'].get('hdr', 'SDR')
        resolution = metadata['video']['resolution']
        bitrate = metadata['video'].get('bitrate', 0)
        
        # Determine bitrate category
        bitrate_mbps = bitrate / 1_000_000 if bitrate else 5
        if bitrate_mbps < 2:
            bitrate_category = '1M'
        elif bitrate_mbps < 6:
            bitrate_category = '4M'
        elif bitrate_mbps < 15:
            bitrate_category = '10M'
        elif bitrate_mbps < 40:
            bitrate_category = '25M'
        else:
            bitrate_category = '50M'
        
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
    
    def _transcode(self, input_file, metadata, settings, file_id):
        """Transcode file with progress reporting"""
        output_file = input_file.parent / f"{input_file.stem}_av1{input_file.suffix}"
        
        # Build ffmpeg command
        cmd = [
            'ffmpeg', '-i', str(input_file),
            '-map', '0',
            '-c:v', 'libsvtav1',
            '-preset', '0',
            '-crf', str(settings['crf']),
            '-c:a', 'libopus',
            '-b:a', f"{settings['opus_bitrate']}k",
            '-c:s', 'copy',
            '-map_metadata', '0',
            '-y', str(output_file)
        ]
        
        import subprocess
        duration = metadata['format']['duration']
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1
        )
        
        # Monitor progress
        last_report = 0
        current_fps = 0.0
        for line in process.stderr:
            if 'time=' in line:
                try:
                    # Parse time
                    time_str = line.split('time=')[1].split()[0]
                    h, m, s = time_str.split(':')
                    current_time = int(h) * 3600 + int(m) * 60 + float(s)
                    percent = min(95, (current_time / duration * 100))  # Scale to 0-95%
                    
                    # Parse speed (fps)
                    if 'speed=' in line:
                        speed_str = line.split('speed=')[1].split('x')[0].strip()
                        speed_multiplier = float(speed_str)
                        # fps = frame / elapsed_time, but we can estimate from speed multiplier
                        current_fps = speed_multiplier * 25  # Rough estimate, 25fps * speed
                    
                    # Calculate ETA
                    remaining_time = duration - current_time
                    eta_seconds = int(remaining_time / speed_multiplier) if speed_multiplier > 0 else 0
                    
                    # Report every 2 seconds or 1% change
                    if time.time() - last_report > 2 or percent - last_report > 1:
                        self.report_progress(file_id, percent, speed=current_fps, eta=eta_seconds)
                        last_report = time.time()
                except Exception as e:
                    pass
        
        returncode = process.wait()
        
        if returncode != 0:
            stderr = process.stderr.read()
            raise Exception(f"FFmpeg failed with code {returncode}: {stderr}")
        
        return output_file
    
    def _replace_original(self, original_path, transcoded_path):
        """Replace original file with transcoded version"""
        import shutil
        
        # Copy to original location
        output_path = original_path.parent / transcoded_path.name
        shutil.copy2(transcoded_path, output_path)
        
        # Rename original to .bak
        backup_path = original_path.with_suffix(original_path.suffix + '.bak')
        original_path.rename(backup_path)
        
        # Rename transcoded to original name
        output_path.rename(original_path)
        
        # Delete backup if not in testing mode
        if not self.config.is_testing_mode():
            backup_path.unlink()
        else:
            logger.info(f"Testing mode: keeping backup {backup_path}")
    
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
        while not self.shutdown_event.is_set() and self.is_running:
            try:
                # Call cpu_percent to update for next heartbeat
                psutil.cpu_percent(interval=None)
                time.sleep(10)  # Wait 10 seconds
                self.send_heartbeat()
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
