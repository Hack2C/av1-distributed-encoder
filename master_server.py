#!/usr/bin/env python3
"""
Master Server - Coordinates distributed transcoding across multiple workers
"""

import os
import sys
import json
import signal
import logging
import threading
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
    database = Database(db_path)
    logger.info(f"Database initialized at {db_path}")
    
    scanner = MediaScanner(config, database)
    
    coordinator = MasterCoordinator(config, database, socketio, shutdown_event)
    logger.info("Master coordinator initialized")

# Web Routes
@app.route('/')
def index():
    """Serve main web interface"""
    return app.send_static_file('master-new.html')

@app.route('/old')
def old_ui():
    """Serve old web interface"""
    return app.send_static_file('master.html')

@app.route('/api/status')
def api_status():
    """Get overall system status"""
    try:
        stats = database.get_statistics()
        files = database.get_all_files()
        
        # Get workers as dict keyed by worker_id
        workers_dict = {}
        for worker in coordinator.get_workers():
            workers_dict[worker['id']] = worker
        
        return jsonify({
            'success': True,
            'statistics': stats,
            'workers': workers_dict,
            'files': files,
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
    """Worker heartbeat"""
    try:
        data = request.json
        coordinator.update_worker_heartbeat(worker_id, data)
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error processing heartbeat: {e}", exc_info=True)
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
            'eta': data.get('eta')
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
        
        # Check if file was uploaded
        if 'file' not in request.files:
            logger.error(f"No file provided in upload request for file {file_id}")
            return jsonify({'success': False, 'error': 'No file provided'}), 400
        
        uploaded_file = request.files['file']
        original_path = Path(file_info['path'])
        
        logger.info(f"Receiving transcoded file {file_id} for {original_path}")
        
        # Save to temp location first
        temp_dir = Path(config.get_temp_directory())
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_output = temp_dir / f"{original_path.stem}_result{original_path.suffix}"
        
        logger.info(f"Saving uploaded file to: {temp_output}")
        uploaded_file.save(str(temp_output))
        
        # Get file sizes for statistics
        # Use size from database for original (file may not be accessible from master)
        original_size = file_info.get('size_bytes', 0)
        new_size = temp_output.stat().st_size
        
        logger.info(f"Original size: {original_size}, New size: {new_size}")
        
        # Ensure target directory exists and is writable
        original_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Replace original file
        if config.is_testing_mode():
            backup_path = original_path.with_suffix(original_path.suffix + '.bak')
            if backup_path.exists():
                logger.info(f"Removing old backup: {backup_path}")
                backup_path.unlink()
            if original_path.exists():
                original_path.rename(backup_path)
                logger.info(f"Backup created: {backup_path}")
        else:
            if original_path.exists():
                logger.info(f"Removing original file: {original_path}")
                original_path.unlink()
        
        # Move result to original location
        logger.info(f"Moving {temp_output} to {original_path}")
        temp_output.rename(original_path)
        logger.info(f"File replaced: {original_path}")
        
        # Calculate savings
        savings_mb = (original_size - new_size) / 1_000_000
        savings_percent = ((original_size - new_size) / original_size * 100) if original_size > 0 else 0
        
        logger.info(f"Transcoding complete: {savings_percent:.1f}% savings ({savings_mb:.1f} MB)")
        
        return jsonify({
            'success': True,
            'original_size': original_size,
            'new_size': new_size,
            'savings_percent': savings_percent
        })
    
    except Exception as e:
        logger.error(f"Error receiving file result for file {file_id}: {e}", exc_info=True)
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
