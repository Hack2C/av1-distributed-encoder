"""
Flask REST API for web interface
"""

import logging
from flask import jsonify, send_from_directory

logger = logging.getLogger(__name__)

def register_routes(app, database, scanner, engine):
    """Register all API routes"""
    
    @app.route('/')
    def index():
        """Serve the main web interface"""
        return send_from_directory('web', 'index.html')
    
    @app.route('/api/status')
    def api_status():
        """Get current service status"""
        try:
            engine_status = engine.get_status()
            stats = database.get_statistics()
            
            return jsonify({
                'success': True,
                'status': {
                    'running': engine_status['is_running'],
                    'paused': engine_status['is_paused'],
                    'current_file': engine_status['current_file']
                },
                'statistics': stats
            })
        except Exception as e:
            logger.error(f"Error getting status: {e}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @app.route('/api/files')
    def api_files():
        """Get list of all files"""
        try:
            files = database.get_all_files()
            return jsonify({
                'success': True,
                'files': files
            })
        except Exception as e:
            logger.error(f"Error getting files: {e}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @app.route('/api/files/<status>')
    def api_files_by_status(status):
        """Get files filtered by status"""
        try:
            files = database.get_all_files(status=status)
            return jsonify({
                'success': True,
                'files': files
            })
        except Exception as e:
            logger.error(f"Error getting files by status: {e}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @app.route('/api/pause', methods=['POST'])
    def api_pause():
        """Pause transcoding"""
        try:
            engine.pause()
            return jsonify({'success': True, 'message': 'Transcoding paused'})
        except Exception as e:
            logger.error(f"Error pausing: {e}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @app.route('/api/resume', methods=['POST'])
    def api_resume():
        """Resume transcoding"""
        try:
            engine.resume()
            return jsonify({'success': True, 'message': 'Transcoding resumed'})
        except Exception as e:
            logger.error(f"Error resuming: {e}", exc_info=True)
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
    
    @app.route('/api/abort', methods=['POST'])
    def api_abort():
        """Abort the currently processing file"""
        try:
            success = engine.abort_current_file()
            if success:
                return jsonify({'success': True, 'message': 'Current file aborted'})
            else:
                return jsonify({'success': False, 'error': 'No file currently processing'}), 400
        except Exception as e:
            logger.error(f"Error aborting: {e}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500
    
    # File management endpoints
    @app.route('/api/files/reset-failed', methods=['POST'])
    def api_reset_failed():
        """Reset all failed files to pending"""
        try:
            count = database.reset_failed_files()
            logger.info(f"Reset {count} failed files to pending")
            return jsonify({'success': True, 'count': count})
        except Exception as e:
            logger.error(f"Error resetting failed files: {e}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @app.route('/api/files/delete-completed', methods=['POST'])
    def api_delete_completed():
        """Delete all completed files from database"""
        try:
            count = database.delete_completed_files()
            logger.info(f"Deleted {count} completed files from database")
            return jsonify({'success': True, 'count': count})
        except Exception as e:
            logger.error(f"Error deleting completed files: {e}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @app.route('/api/files/<int:file_id>/reset', methods=['POST'])
    def api_reset_file(file_id):
        """Reset a specific file to pending"""
        try:
            database.reset_file(file_id)
            logger.info(f"Reset file {file_id} to pending")
            return jsonify({'success': True})
        except Exception as e:
            logger.error(f"Error resetting file {file_id}: {e}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @app.route('/api/files/<int:file_id>/skip', methods=['POST'])
    def api_skip_file(file_id):
        """Skip a file (mark as completed without processing)"""
        try:
            database.skip_file(file_id)
            logger.info(f"Skipped file {file_id}")
            return jsonify({'success': True})
        except Exception as e:
            logger.error(f"Error skipping file {file_id}: {e}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @app.route('/api/files/<int:file_id>/retry', methods=['POST'])
    def api_retry_file(file_id):
        """Retry a file stuck in processing"""
        try:
            database.retry_file(file_id)
            logger.info(f"Retrying file {file_id}")
            return jsonify({'success': True})
        except Exception as e:
            logger.error(f"Error retrying file {file_id}: {e}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @app.route('/api/files/<int:file_id>/delete', methods=['POST'])
    def api_delete_file(file_id):
        """Delete a file from database"""
        try:
            database.delete_file(file_id)
            logger.info(f"Deleted file {file_id} from database")
            return jsonify({'success': True})
        except Exception as e:
            logger.error(f"Error deleting file {file_id}: {e}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500
    
    logger.info("API routes registered")
