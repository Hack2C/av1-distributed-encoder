"""
Master Coordinator - Manages workers and job distribution
"""

import logging
import threading
import time
from datetime import datetime, timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)

class MasterCoordinator:
    """Coordinates job distribution across multiple workers"""
    
    def __init__(self, config, database, socketio, shutdown_event):
        self.config = config
        self.db = database
        self.socketio = socketio
        self.shutdown_event = shutdown_event
        
        # Worker management
        self.workers = {}  # worker_id -> worker_info
        self.worker_jobs = {}  # worker_id -> current_file_id
        self.lock = threading.Lock()
        
        # Background thread
        self.monitor_thread = None
        self.is_running = False
        
        logger.info("Master coordinator initialized")
    
    def start(self):
        """Start the coordinator"""
        self.is_running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        logger.info("Coordinator monitor started")
    
    def stop(self):
        """Stop the coordinator"""
        self.is_running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        logger.info("Coordinator stopped")
    
    def _monitor_loop(self):
        """Background monitoring loop"""
        while not self.shutdown_event.is_set() and self.is_running:
            try:
                self._check_worker_health()
                self._broadcast_status()
            except Exception as e:
                logger.error(f"Error in monitor loop: {e}", exc_info=True)
            
            time.sleep(5)
    
    def _check_worker_health(self):
        """Check worker health and mark jobs as failed if workers time out"""
        with self.lock:
            now = datetime.now()
            timeout = timedelta(seconds=30)
            
            for worker_id, worker in list(self.workers.items()):
                last_seen = datetime.fromisoformat(worker['last_seen'])
                if now - last_seen > timeout:
                    logger.warning(f"Worker {worker_id} ({worker['hostname']}) timed out")
                    worker['status'] = 'offline'
                    
                    # Mark current job as failed if worker was processing
                    if worker_id in self.worker_jobs:
                        file_id = self.worker_jobs[worker_id]
                        self.db.mark_file_failed(file_id, "Worker disconnected")
                        del self.worker_jobs[worker_id]
            
            # Check for orphaned files in processing state without an assigned worker
            processing_files = self.db.get_all_files(status='processing')
            active_worker_ids = set(self.worker_jobs.keys())
            
            for file_record in processing_files:
                file_id = file_record['id']
                assigned_worker = file_record.get('assigned_worker_id')
                
                # If file is processing but no worker is assigned or worker is not active
                if not assigned_worker or assigned_worker not in active_worker_ids:
                    logger.warning(f"Found orphaned file {file_id} in processing state, marking as failed")
                    self.db.mark_file_failed(file_id, "No active worker assigned")
    
    def _broadcast_status(self):
        """Broadcast status update to all connected clients"""
        try:
            stats = self.db.get_statistics()
            workers_dict = self.get_workers_dict()  # Get actual worker objects as dict
            
            self.socketio.emit('status_update', {
                'statistics': stats,
                'workers': workers_dict,
                'timestamp': datetime.now().isoformat()
            })
        except Exception as e:
            logger.error(f"Error broadcasting status: {e}")
    
    def register_worker(self, hostname, capabilities, version):
        """Register a new worker"""
        with self.lock:
            # Generate worker ID
            worker_id = f"worker-{len(self.workers) + 1}"
            
            self.workers[worker_id] = {
                'id': worker_id,
                'hostname': hostname,
                'capabilities': capabilities,
                'version': version,
                'status': 'idle',
                'registered_at': datetime.now().isoformat(),
                'last_seen': datetime.now().isoformat(),
                'jobs_completed': 0,
                'jobs_failed': 0,
                'total_bytes_processed': 0
            }
            
            logger.info(f"Registered worker: {worker_id} ({hostname})")
            return worker_id
    
    def update_worker_heartbeat(self, worker_id, data):
        """Update worker heartbeat"""
        with self.lock:
            if worker_id in self.workers:
                self.workers[worker_id]['last_seen'] = datetime.now().isoformat()
                self.workers[worker_id]['status'] = data.get('status', 'idle')
                
                # Update system info if provided
                if 'cpu_percent' in data:
                    self.workers[worker_id]['cpu_percent'] = data['cpu_percent']
                if 'memory_percent' in data:
                    self.workers[worker_id]['memory_percent'] = data['memory_percent']
                if 'current_speed' in data:
                    self.workers[worker_id]['current_speed'] = data['current_speed']
                if 'current_eta' in data:
                    self.workers[worker_id]['current_eta'] = data['current_eta']
    
    def assign_job(self, worker_id):
        """Assign next job to worker"""
        with self.lock:
            if worker_id not in self.workers:
                return None
            
            # Get next pending file (respecting priority and preferred worker)
            file_record = self.db.get_next_pending_file(worker_id)
            
            if not file_record:
                return None
            
            # Mark file as processing and assign to worker
            file_id = file_record['id']
            self.db.update_file_status(file_id, 'processing',
                                      started_at=datetime.now().isoformat(),
                                      assigned_worker_id=worker_id)
            
            # Track assignment
            self.worker_jobs[worker_id] = file_id
            self.workers[worker_id]['status'] = 'processing'
            self.workers[worker_id]['current_file'] = file_record['filename']
            
            logger.info(f"Assigned job {file_id} ({file_record['filename']}) to {worker_id}")
            
            return {
                'file_id': file_id,
                'path': file_record['path'],
                'filename': file_record['filename'],
                'size_bytes': file_record['size_bytes'],
                'source_codec': file_record.get('source_codec'),
                'source_resolution': file_record.get('source_resolution')
            }
    
    def update_job_progress(self, worker_id, file_id, progress_data):
        """Update job progress"""
        percent = progress_data.get('percent', 0)
        speed = progress_data.get('speed')
        eta = progress_data.get('eta')
        
        # Update database with all progress data
        update_fields = {
            'progress_percent': percent
        }
        if speed is not None:
            update_fields['processing_speed_fps'] = speed
        if eta is not None:
            update_fields['time_remaining_seconds'] = eta
            
        self.db.update_file_status(file_id, 'processing', **update_fields)
        
        # Update worker info
        with self.lock:
            if worker_id in self.workers:
                self.workers[worker_id]['current_progress'] = percent
                self.workers[worker_id]['current_speed'] = speed
                self.workers[worker_id]['current_eta'] = eta
    
    def complete_job(self, worker_id, file_id, result_data):
        """Mark job as completed"""
        output_size = result_data.get('output_size')
        original_size = result_data.get('original_size')
        savings_bytes = original_size - output_size
        savings_percent = (savings_bytes / original_size * 100) if original_size > 0 else 0
        
        # Update database
        self.db.mark_file_completed(file_id, output_size, savings_bytes, savings_percent)
        
        # Update worker stats
        with self.lock:
            if worker_id in self.workers:
                self.workers[worker_id]['status'] = 'idle'
                self.workers[worker_id]['jobs_completed'] += 1
                self.workers[worker_id]['total_bytes_processed'] += original_size
                
                if worker_id in self.worker_jobs:
                    del self.worker_jobs[worker_id]
        
        logger.info(f"Job {file_id} completed by {worker_id} ({savings_percent:.1f}% savings)")
    
    def fail_job(self, worker_id, file_id, error_message):
        """Mark job as failed"""
        self.db.mark_file_failed(file_id, error_message)
        
        # Update worker stats
        with self.lock:
            if worker_id in self.workers:
                self.workers[worker_id]['status'] = 'idle'
                self.workers[worker_id]['jobs_failed'] += 1
                
                if worker_id in self.worker_jobs:
                    del self.worker_jobs[worker_id]
        
        logger.warning(f"Job {file_id} failed on {worker_id}: {error_message}")
    
    def get_workers(self):
        """Get all workers"""
        with self.lock:
            return list(self.workers.values())
    
    def get_workers_dict(self):
        """Get all workers as dictionary keyed by worker ID"""
        with self.lock:
            return dict(self.workers)
    
    def get_worker_status(self):
        """Get worker status summary"""
        with self.lock:
            total = len(self.workers)
            online = sum(1 for w in self.workers.values() if w['status'] != 'offline')
            processing = sum(1 for w in self.workers.values() if w['status'] == 'processing')
            
            return {
                'total': total,
                'online': online,
                'processing': processing,
                'idle': online - processing
            }
    
    def get_current_jobs(self):
        """Get currently processing jobs"""
        with self.lock:
            jobs = []
            for worker_id, file_id in self.worker_jobs.items():
                worker = self.workers.get(worker_id, {})
                file_record = self.db.get_file_by_id(file_id)
                
                if file_record:
                    jobs.append({
                        'worker_id': worker_id,
                        'worker_hostname': worker.get('hostname', 'Unknown'),
                        'file_id': file_id,
                        'filename': file_record['filename'],
                        'progress_percent': file_record.get('progress_percent', 0),
                        'speed': worker.get('current_speed'),
                        'started_at': file_record.get('started_at')
                    })
            
            return jobs
