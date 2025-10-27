#!/usr/bin/env python3
"""
Master Server - Coordinates distributed transcoding across multiple workers
"""

import os
import sys
import signal
import logging
import threading
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, jsonify, request
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
    
    database = Database('transcoding.db')
    logger.info("Database initialized")
    
    scanner = MediaScanner(config, database)
    
    coordinator = MasterCoordinator(config, database, socketio, shutdown_event)
    logger.info("Master coordinator initialized")

# Web Routes
@app.route('/')
def index():
    """Serve main web interface"""
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
