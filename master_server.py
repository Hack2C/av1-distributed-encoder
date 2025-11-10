#!/usr/bin/env python3
"""
Master Server - Coordinates distributed transcoding across multiple workers
"""

__version__ = "2.2.1"

import os
import sys
import json
import signal
import logging
import threading
import shutil
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, jsonify, request, send_file
from flask_socketio import SocketIO, emit
from flask_cors import CORS

# Add lib directory to path
sys.path.insert(0, str(Path(__file__).parent))

from lib.config import Config
from lib.database import Database
from lib.scanner import MediaScanner
from lib.master_coordinator import MasterCoordinator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__, 
            static_folder='web',
            static_url_path='')
app.config['SECRET_KEY'] = 'av1-master-secret-key'
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Global components
config = None
database = None
scanner = None
coordinator = None
shutdown_event = threading.Event()

def signal_handler(signum, frame):
    """Handle shutdown signals"""
    logger.info(f"Received signal {signum}")
    shutdown_event.set()
    if coordinator:
        coordinator.stop()
    sys.exit(0)

def init_components():
    """Initialize all components"""
    global config, database, scanner, coordinator
    
    config = Config()
    logger.info("Configuration loaded from config.json")
    
    db_path = os.environ.get('DB_PATH', '/data/transcoding.db')
    database = Database(db_path, config)
    logger.info(f"Database initialized at {db_path}")
    
    scanner = MediaScanner(config, database)
    
    coordinator = MasterCoordinator(config, database, socketio, shutdown_event)
    logger.info("Master coordinator initialized")

# Web Routes
@app.route('/')
def index():
    """Serve main web interface"""
    return app.send_static_file('master.html')

@app.route('/old')
def old_ui():
    """Serve old web interface"""
    return app.send_static_file('master.html')

@app.route('/version')
def version():
    """Get server version"""
    return jsonify({'version': __version__})

@app.route('/api/status')
def api_status():
    """Get overall system status"""
    try:
        stats = database.get_statistics()
        files = database.get_all_files()
        
        # Get workers as dict keyed by worker_id (use display names as keys for human readability)
        workers_dict = {}
        for worker in coordinator.get_workers():
            display_name = worker.get('display_name', worker['id'][:8])
            worker_info = dict(worker)
            worker_info['display_name'] = display_name
            workers_dict[display_name] = worker_info
        
        # Enhance files with worker display names
        enhanced_files = []
        for file_record in files:
            enhanced_file = dict(file_record)
            if file_record.get('assigned_worker_id'):
                display_name = coordinator.get_worker_display_name(file_record['assigned_worker_id'])
                enhanced_file['assigned_worker_display_name'] = display_name
            if file_record.get('preferred_worker_id'):
                display_name = coordinator.get_worker_display_name(file_record['preferred_worker_id'])
                enhanced_file['preferred_worker_display_name'] = display_name
            enhanced_files.append(enhanced_file)
        
        return jsonify({
            'success': True,
            'statistics': stats,
            'workers': workers_dict,
            'files': enhanced_files,
            'last_update': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Error getting status: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/files')
def api_files():
    """Get all files"""
    try:
        files = database.get_all_files()
        return jsonify({'success': True, 'files': files})
    except Exception as e:
        logger.error(f"Error getting files: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/scan', methods=['POST'])
def api_scan():
    """Trigger a new scan of media directories"""
    try:
        count = scanner.rescan()
        return jsonify({
            'success': True, 
            'message': f'Scan completed. Found {count} files.'
        })
    except Exception as e:
        logger.error(f"Error scanning: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/workers')
def api_workers():
    """Get all workers"""
    try:
        workers = coordinator.get_workers()
        return jsonify({'success': True, 'workers': workers})
    except Exception as e:
        logger.error(f"Error getting workers: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

# Worker API endpoints
@app.route('/api/worker/register', methods=['POST'])
def api_worker_register():
    """Register a new worker"""
    try:
        data = request.json
        worker_id = coordinator.register_worker(
            hostname=data.get('hostname'),
            capabilities=data.get('capabilities', {}),
            version=data.get('version')
        )
        logger.info(f"Worker registered: {worker_id} ({data.get('hostname')})")
        return jsonify({'success': True, 'worker_id': worker_id})
    except Exception as e:
        logger.error(f"Error registering worker: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/worker/<worker_id>/heartbeat', methods=['POST'])
def api_worker_heartbeat(worker_id):
    """Worker heartbeat with reconnection recovery"""
    try:
        data = request.json
        
        # Check if worker exists, if not return 404 to trigger re-registration
        if worker_id not in coordinator.workers:
            logger.warning(f"Heartbeat from unknown worker {worker_id}, triggering re-registration")
            return jsonify({'success': False, 'error': 'Worker not registered'}), 404
        
        # Handle job recovery if worker reconnected with current job
        current_job = data.get('current_job')
        if current_job and worker_id not in coordinator.worker_jobs:
            file_id = current_job['file_id']
            progress = current_job.get('progress_percent', 0)
            claimed_path = current_job.get('file_path')  # Worker should send absolute path
            claimed_size = current_job.get('file_size')   # Worker should send file size
            
            # Validate that the file exists in master database and paths match
            file_record = database.get_file_by_id(file_id)
            if not file_record:
                logger.warning(f"Worker {worker_id} claims to process file {file_id} but file not found in database")
                return jsonify({'success': False, 'error': 'File not found'}), 400
            
            if file_record['status'] not in ['processing', 'pending']:
                logger.warning(f"Worker {worker_id} claims to process file {file_id} but file status is {file_record['status']}")
                return jsonify({'success': False, 'error': 'File not in processable state'}), 400
            
            # Validate file path matches (security check)
            if claimed_path and claimed_path != file_record['path']:
                logger.warning(f"Worker {worker_id} claims to process file with path {claimed_path} but database has {file_record['path']}")
                return jsonify({'success': False, 'error': 'File path mismatch'}), 400
            
            # Validate file size matches (integrity check)
            if claimed_size and claimed_size != file_record['size_bytes']:
                logger.warning(f"Worker {worker_id} claims to process file {file_id} with size {claimed_size} but database has {file_record['size_bytes']}")
                return jsonify({'success': False, 'error': 'File size mismatch'}), 400
            
            # Validate job timing - allow long-running jobs but reject truly stale ones
            job_start_time = current_job.get('started_at')
            if job_start_time:
                try:
                    start_time = datetime.fromisoformat(job_start_time.replace('Z', '+00:00'))
                    job_age = datetime.now() - start_time
                    
                    # Only reject jobs that are extremely old (30 days) AND have made no progress
                    # This allows week-long transcodes but prevents truly abandoned work
                    if job_age > timedelta(days=30) and progress < 10:
                        logger.warning(f"Worker {worker_id} job {file_id} too stale to recover (started {job_start_time}, {progress}% progress)")
                        return jsonify({'success': False, 'error': 'Job too stale to recover'}), 400
                    
                    logger.info(f"Accepting job recovery - age: {job_age}, progress: {progress}%")
                except Exception as e:
                    logger.warning(f"Could not parse job start time {job_start_time}: {e}")
            
            # Check if worker claims job is completed but not reported
            is_completed = current_job.get('is_completed', False)
            
            if is_completed:
                logger.info(f"Worker {worker_id} has completed job {file_id} but hadn't reported it - accepting as completed")
                # Mark as completed - worker will need to report detailed completion info separately
                database.update_file_status(file_id, 'completed',
                                          progress_percent=100,
                                          completed_at=datetime.now().isoformat(),
                                          assigned_worker_id=worker_id)
                
                # Clear worker's current job since it's done
                if worker_id in coordinator.worker_jobs:
                    del coordinator.worker_jobs[worker_id]
                coordinator.workers[worker_id]['status'] = 'idle'
                coordinator.workers[worker_id]['current_file'] = None
            else:
                logger.info(f"Recovering job {file_id} ({file_record['filename']}) for reconnected worker {worker_id} at {progress}% progress")
                
                # Update database to reflect current state
                database.update_file_status(file_id, 'processing', 
                                          progress_percent=progress,
                                          assigned_worker_id=worker_id)
                
                # Update coordinator state
                coordinator.worker_jobs[worker_id] = file_id
                coordinator.workers[worker_id]['current_file'] = file_record['filename']
                coordinator.workers[worker_id]['status'] = 'processing'
        
        coordinator.update_worker_heartbeat(worker_id, data)
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error processing heartbeat: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/worker/<worker_id>/fade_out', methods=['POST'])
def api_worker_fade_out(worker_id):
    """Toggle fade out status for a worker"""
    try:
        result = coordinator.toggle_worker_fade_out(worker_id)
        if result['success']:
            logger.info(f"Worker fade out toggled: {result['display_name']} -> {'enabled' if result['fade_out'] else 'disabled'}")
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error toggling worker fade out: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/config/quality_lookup.json')
def api_config_quality_lookup():
    """Serve quality lookup JSON to workers"""
    try:
        config_dir = Path(os.environ.get('CONFIG_DIR', '/data/config'))
        config_file = config_dir / 'quality_lookup.json'
        
        # Fallback to app directory if config doesn't exist
        if not config_file.exists():
            config_file = Path('/app/quality_lookup.json')
        
        if not config_file.exists():
            return jsonify({'success': False, 'error': 'Config file not found'}), 404
        
        with open(config_file, 'r') as f:
            data = json.load(f)
        
        return jsonify(data)
    except Exception as e:
        logger.error(f"Error serving quality_lookup.json: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/config/audio_codec_lookup.json')
def api_config_audio_codec_lookup():
    """Serve audio codec lookup JSON to workers"""
    try:
        config_dir = Path(os.environ.get('CONFIG_DIR', '/data/config'))
        config_file = config_dir / 'audio_codec_lookup.json'
        
        # Fallback to app directory if config doesn't exist
        if not config_file.exists():
            config_file = Path('/app/audio_codec_lookup.json')
        
        if not config_file.exists():
            return jsonify({'success': False, 'error': 'Config file not found'}), 404
        
        with open(config_file, 'r') as f:
            data = json.load(f)
        
        return jsonify(data)
    except Exception as e:
        logger.error(f"Error serving audio_codec_lookup.json: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/worker/<worker_id>/job/request', methods=['GET'])
def api_worker_request_job(worker_id):
    """Worker requests next job"""
    try:
        job = coordinator.assign_job(worker_id)
        if job:
            return jsonify({'success': True, 'job': job})
        else:
            return jsonify({'success': True, 'job': None, 'message': 'No jobs available'})
    except Exception as e:
        logger.error(f"Error assigning job: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/worker/<worker_id>/job/<int:file_id>/progress', methods=['POST'])
def api_worker_job_progress(worker_id, file_id):
    """Worker reports job progress"""
    try:
        data = request.json
        coordinator.update_job_progress(worker_id, file_id, data)
        
        # Broadcast progress via WebSocket
        socketio.emit('progress', {
            'worker_id': worker_id,
            'file_id': file_id,
            'percent': data.get('percent', 0),
            'speed': data.get('speed'),
            'eta': data.get('eta'),
            'status': data.get('status')
        })
        
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error updating progress: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/worker/<worker_id>/job/<int:file_id>/complete', methods=['POST'])
def api_worker_job_complete(worker_id, file_id):
    """Worker reports job completion"""
    try:
        data = request.json
        coordinator.complete_job(worker_id, file_id, data)
        
        # Broadcast completion via WebSocket
        socketio.emit('completed', {
            'worker_id': worker_id,
            'file_id': file_id,
            'output_size': data.get('output_size'),
            'savings_percent': data.get('savings_percent')
        })
        
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error completing job: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/worker/<worker_id>/job/<int:file_id>/failed', methods=['POST'])
def api_worker_job_failed(worker_id, file_id):
    """Worker reports job failure"""
    try:
        data = request.json
        coordinator.fail_job(worker_id, file_id, data.get('error'))
        
        # Broadcast error via WebSocket
        socketio.emit('error', {
            'worker_id': worker_id,
            'file_id': file_id,
            'error': data.get('error')
        })
        
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error marking job failed: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

# File Distribution Mode Endpoints
@app.route('/api/worker/<worker_id>/file/<int:file_id>/download', methods=['GET'])
def api_worker_file_download(worker_id, file_id):
    """Send file to worker for processing (file distribution mode)"""
    try:
        # Get file info from database
        file_info = database.get_file_by_id(file_id)
        if not file_info:
            return jsonify({'success': False, 'error': 'File not found'}), 404
        
        file_path = Path(file_info['path'])
        if not file_path.exists():
            return jsonify({'success': False, 'error': 'File does not exist on disk'}), 404
        
        logger.info(f"Sending file {file_id} to worker {worker_id}: {file_path}")
        
        # Stream the file
        return send_file(
            file_path,
            as_attachment=True,
            download_name=file_path.name,
            mimetype='application/octet-stream'
        )
    
    except Exception as e:
        logger.error(f"Error sending file to worker: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/file/<int:file_id>/result', methods=['POST'])
def api_file_result_upload(file_id):
    """Receive transcoded file from worker (file distribution mode)"""
    try:
        # Get file info
        file_info = database.get_file_by_id(file_id)
        if not file_info:
            logger.error(f"File {file_id} not found in database")
            return jsonify({'success': False, 'error': 'File not found'}), 404
        
        # Check job status - allow upload for processing or failed jobs (worker completed despite network issues)
        file_status = file_info.get('status', 'pending')
        logger.info(f"Upload attempt for file {file_id} with status: {file_status}")
        
        if file_status == 'completed':
            logger.warning(f"Upload attempt for already completed file {file_id} - ignoring")
            return jsonify({'success': True, 'message': 'File already completed'}), 200
        elif file_status not in ['processing', 'failed']:
            logger.error(f"Invalid upload attempt for file {file_id} with status {file_status}")
            return jsonify({'success': False, 'error': f'Invalid job status: {file_status}'}), 400
        
        # Check if file was uploaded
        if 'file' not in request.files:
            logger.error(f"No file provided in upload request for file {file_id}")
            return jsonify({'success': False, 'error': 'No file provided'}), 400
        
        uploaded_file = request.files['file']
        original_path = Path(file_info['path'])
        
        logger.info(f"Receiving transcoded file {file_id} for {original_path}")
        
        # Ensure target directory exists and is writable
        logger.info(f"Target directory: {original_path.parent}")
        original_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Check directory permissions before saving
        if not os.access(original_path.parent, os.W_OK):
            raise Exception(f"Directory not writable: {original_path.parent}")
        
        # Save directly to final location with .av1 extension
        av1_path = original_path.with_suffix('.av1')
        logger.info(f"Saving uploaded file to: {av1_path}")
        
        # Check if we have enough disk space
        stat = os.statvfs(original_path.parent)
        free_space = stat.f_frsize * stat.f_bavail
        logger.info(f"Available disk space: {free_space / 1_000_000_000:.2f} GB")
        
        uploaded_file.save(str(av1_path))
        logger.info(f"File saved successfully: {av1_path.stat().st_size} bytes")
        
        # Set correct ownership on the .av1 file
        uid = int(os.environ.get('PUID', '1000'))
        gid = int(os.environ.get('PGID', '1000'))
        os.chown(str(av1_path), uid, gid)
        
        # Get file sizes for statistics
        original_size = file_info.get('size_bytes', 0)
        new_size = av1_path.stat().st_size
        
        logger.info(f"Original size: {original_size}, New size: {new_size}")
        
        # Rename original to .bak
        backup_path = original_path.with_suffix(original_path.suffix + '.bak')
        if backup_path.exists():
            logger.info(f"Removing old backup: {backup_path}")
            backup_path.unlink()
        
        if original_path.exists():
            logger.info(f"Renaming original to backup: {original_path} -> {backup_path}")
            original_path.rename(backup_path)
        
        # Rename .av1 to .mkv (or original extension)
        logger.info(f"Renaming transcoded file: {av1_path} -> {original_path}")
        av1_path.rename(original_path)
        
        # Set correct ownership on final file
        os.chown(str(original_path), uid, gid)
        
        # Remove backup if not in preserve mode
        if not config.is_preserve_mode():
            if backup_path.exists():
                logger.info(f"Removing backup (not in preserve mode): {backup_path}")
                backup_path.unlink()
        
        logger.info(f"File replaced: {original_path}")
        
        # Calculate savings
        savings_mb = (original_size - new_size) / 1_000_000
        savings_percent = ((original_size - new_size) / original_size * 100) if original_size > 0 else 0
        
        # Mark job as completed in database
        database.update_file_status(file_id, 'completed', 
                                   completed_at=datetime.now().isoformat(),
                                   output_size_bytes=new_size,
                                   savings_bytes=(original_size - new_size),
                                   savings_percent=savings_percent)
        
        logger.info(f"Transcoding complete: {savings_percent:.1f}% savings ({savings_mb:.1f} MB)")
        
        return jsonify({
            'success': True,
            'original_size': original_size,
            'new_size': new_size,
            'savings_percent': savings_percent
        })
    
    except Exception as e:
        logger.error(f"Error receiving file result for file {file_id}: {e}", exc_info=True)
        
        # Log additional diagnostics for troubleshooting
        try:
            if file_info:
                original_path = Path(file_info['path'])
                logger.error(f"Upload failure details:")
                logger.error(f"  Original path: {original_path}")
                logger.error(f"  Parent exists: {original_path.parent.exists()}")
                logger.error(f"  Parent writable: {os.access(original_path.parent, os.W_OK)}")
                
                # Check disk space
                stat = os.statvfs(original_path.parent)
                free_space = stat.f_frsize * stat.f_bavail
                logger.error(f"  Free disk space: {free_space / 1_000_000_000:.2f} GB")
                
        except Exception as diag_error:
            logger.error(f"Failed to get upload diagnostics: {diag_error}")
        
        return jsonify({'success': False, 'error': str(e)}), 500

# Job Control Endpoints
@app.route('/api/file/<int:file_id>/cancel', methods=['POST'])
def api_cancel_file(file_id):
    """Cancel a job"""
    try:
        # Get file info to check if it's being processed
        file_info = database.get_file(file_id)
        if not file_info:
            return jsonify({'success': False, 'error': 'File not found'}), 404
        
        if file_info['status'] == 'processing' and file_info.get('assigned_worker_id'):
            # TODO: Send cancel signal to worker
            logger.info(f"Cancelling job {file_id} on worker {file_info['assigned_worker_id']}")
        
        # Reset to pending
        database.reset_file(file_id)
        coordinator._broadcast_status()
        
        return jsonify({'success': True, 'message': 'Job cancelled and reset to pending'})
    except Exception as e:
        logger.error(f"Error cancelling file: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/file/<int:file_id>/retry', methods=['POST'])
def api_retry_file(file_id):
    """Retry a failed or stuck job"""
    try:
        database.retry_file(file_id)
        coordinator._broadcast_status()
        return jsonify({'success': True, 'message': 'Job reset to pending'})
    except Exception as e:
        logger.error(f"Error retrying file: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/file/<int:file_id>/skip', methods=['POST'])
def api_skip_file(file_id):
    """Skip a file"""
    try:
        database.skip_file(file_id)
        coordinator._broadcast_status()
        return jsonify({'success': True, 'message': 'File skipped'})
    except Exception as e:
        logger.error(f"Error skipping file: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/file/<int:file_id>/delete', methods=['POST'])
def api_delete_file(file_id):
    """Delete a file from queue"""
    try:
        database.delete_file(file_id)
        coordinator._broadcast_status()
        return jsonify({'success': True, 'message': 'File deleted from queue'})
    except Exception as e:
        logger.error(f"Error deleting file: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/file/<int:file_id>/priority', methods=['POST'])
def set_file_priority_endpoint(file_id):
    """Set file priority and preferred worker"""
    try:
        data = request.get_json()
        preferred_worker_id = data.get('preferred_worker_id')
        
        # Validate worker exists if specified
        if preferred_worker_id:
            if preferred_worker_id not in coordinator.workers:
                return jsonify({'error': f'Worker {preferred_worker_id} not found'}), 400
        
        # Set high priority (higher number = higher priority)
        priority = 1000  # High priority value
        
        # Use database method to set priority
        database.set_file_priority(file_id, priority, preferred_worker_id)
        
        # Get updated file info
        updated_file = database.get_file_by_id(file_id)
        
        return jsonify({
            'success': True, 
            'message': 'File priority set',
            'priority': priority,
            'preferred_worker_id': preferred_worker_id,
            'file': updated_file
        })
    
    except Exception as e:
        logger.error(f"Error setting file priority: {e}")
        return jsonify({'error': str(e)}), 500
    """Set file priority for specific worker"""
    try:
        data = request.get_json()
        worker_id = data.get('worker_id')
        priority = data.get('priority', 'high')
        
        if not worker_id:
            return jsonify({'success': False, 'error': 'Worker ID required'}), 400
        
        # Check if file exists and is in pending/failed status
        file_info = database.get_file(file_id)
        if not file_info:
            return jsonify({'success': False, 'error': 'File not found'}), 404
        
        if file_info['status'] not in ['pending', 'failed']:
            return jsonify({'success': False, 'error': 'File must be pending or failed to prioritize'}), 400
        
        # Check if worker exists and is active
        if worker_id not in coordinator.workers:
            return jsonify({'success': False, 'error': 'Worker not found or not active'}), 404
        
        # Set priority and preferred worker
        database.set_file_priority(file_id, priority, worker_id)
        
        # Reset status to pending if it was failed
        if file_info['status'] == 'failed':
            database.reset_file(file_id)
        
        coordinator._broadcast_status()
        
        logger.info(f"File {file_id} prioritized for worker {worker_id}")
        return jsonify({'success': True, 'message': f'File prioritized for worker {worker_id}'})
    except Exception as e:
        logger.error(f"Error setting file priority: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

def main():
    """Main entry point"""
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logger.info("Starting AV1 Master Server...")
    
    # Initialize components
    init_components()
    logger.info("Master server initialized")
    
    # Start coordinator
    coordinator.start()
    logger.info("Coordinator started")
    
    # Initial scan
    logger.info("Performing initial media library scan...")
    count = scanner.rescan()
    logger.info(f"Initial scan found {count} files")
    
    # Get configuration
    host = config.get('master.host', '0.0.0.0')
    port = config.get('master.port', 8090)
    
    logger.info(f"Starting master web interface at http://{host}:{port}")
    
    # Start Flask app with SocketIO
    try:
        socketio.run(app, host=host, port=port, debug=False, allow_unsafe_werkzeug=True)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        shutdown_event.set()
        coordinator.stop()

if __name__ == '__main__':
    main()
