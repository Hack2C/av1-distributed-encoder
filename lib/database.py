"""
SQLite database management for tracking transcoding state
"""

import sqlite3
import logging
import json
from datetime import datetime
from pathlib import Path
from contextlib import contextmanager

logger = logging.getLogger(__name__)

class Database:
    """SQLite database for tracking file queue and statistics"""
    
    def __init__(self, db_path='transcoding.db'):
        self.db_path = db_path
        self._init_database()
    
    def _init_database(self):
        """Initialize database schema"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Files table - tracks all media files
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT UNIQUE NOT NULL,
                    directory TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    size_bytes INTEGER,
                    status TEXT DEFAULT 'pending',
                    
                    -- Source metadata
                    source_codec TEXT,
                    source_bitrate INTEGER,
                    source_resolution TEXT,
                    source_bitdepth INTEGER,
                    source_hdr TEXT,
                    source_audio_codec TEXT,
                    source_audio_channels INTEGER,
                    source_audio_bitrate INTEGER,
                    
                    -- Target settings
                    target_crf INTEGER,
                    target_opus_bitrate INTEGER,
                    
                    -- Progress tracking
                    progress_percent REAL DEFAULT 0,
                    assigned_worker_id TEXT,
                    started_at TEXT,
                    completed_at TEXT,
                    estimated_time_seconds INTEGER,
                    time_remaining_seconds INTEGER,
                    processing_speed_fps REAL,
                    
                    -- Results
                    output_size_bytes INTEGER,
                    savings_bytes INTEGER,
                    savings_percent REAL,
                    
                    -- Error handling
                    error_message TEXT,
                    retry_count INTEGER DEFAULT 0,
                    
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Statistics table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS statistics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    total_files INTEGER DEFAULT 0,
                    completed_files INTEGER DEFAULT 0,
                    failed_files INTEGER DEFAULT 0,
                    pending_files INTEGER DEFAULT 0,
                    processing_files INTEGER DEFAULT 0,
                    
                    total_original_size INTEGER DEFAULT 0,
                    total_transcoded_size INTEGER DEFAULT 0,
                    total_savings_bytes INTEGER DEFAULT 0,
                    total_savings_percent REAL DEFAULT 0,
                    
                    estimated_total_savings INTEGER DEFAULT 0,
                    estimated_final_size INTEGER DEFAULT 0,
                    
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Insert initial statistics row if not exists
            cursor.execute('SELECT COUNT(*) FROM statistics')
            if cursor.fetchone()[0] == 0:
                cursor.execute('INSERT INTO statistics DEFAULT VALUES')
            
            # Create indexes
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_status ON files(status)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_directory ON files(directory)')
            
            # Migrate existing database - add new columns if they don't exist
            self._migrate_database(cursor)
            
            conn.commit()
            logger.info("Database initialized")
    
    def _migrate_database(self, cursor):
        """Add new columns to existing databases"""
        try:
            # Check if new columns exist
            cursor.execute("PRAGMA table_info(files)")
            columns = [row[1] for row in cursor.fetchall()]
            
            if 'assigned_worker_id' not in columns:
                cursor.execute("ALTER TABLE files ADD COLUMN assigned_worker_id TEXT")
                logger.info("Added assigned_worker_id column")
            
            if 'estimated_time_seconds' not in columns:
                cursor.execute("ALTER TABLE files ADD COLUMN estimated_time_seconds INTEGER")
                logger.info("Added estimated_time_seconds column")
            
            if 'time_remaining_seconds' not in columns:
                cursor.execute("ALTER TABLE files ADD COLUMN time_remaining_seconds INTEGER")
                logger.info("Added time_remaining_seconds column")
            
            if 'processing_speed_fps' not in columns:
                cursor.execute("ALTER TABLE files ADD COLUMN processing_speed_fps REAL")
                logger.info("Added processing_speed_fps column")
                
        except Exception as e:
            logger.warning(f"Migration warning: {e}")

    
    @contextmanager
    def _get_connection(self):
        """Context manager for database connections"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def add_file(self, file_info):
        """Add a new file to the queue"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR IGNORE INTO files (path, directory, filename, size_bytes)
                VALUES (?, ?, ?, ?)
            ''', (file_info['path'], file_info['directory'], 
                  file_info['filename'], file_info['size_bytes']))
            conn.commit()
            return cursor.lastrowid
    
    def get_next_pending_file(self):
        """Get the next file to process"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM files 
                WHERE status = 'pending'
                ORDER BY created_at ASC
                LIMIT 1
            ''')
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def update_file_status(self, file_id, status, **kwargs):
        """Update file status and optional metadata"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            set_clause = ['status = ?', 'updated_at = CURRENT_TIMESTAMP']
            values = [status]
            
            for key, value in kwargs.items():
                set_clause.append(f'{key} = ?')
                values.append(value)
            
            values.append(file_id)
            
            query = f'UPDATE files SET {", ".join(set_clause)} WHERE id = ?'
            cursor.execute(query, values)
            conn.commit()
    
    def get_statistics(self):
        """Get current statistics"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Update statistics from files table
            cursor.execute('''
                UPDATE statistics SET
                    total_files = (SELECT COUNT(*) FROM files),
                    completed_files = (SELECT COUNT(*) FROM files WHERE status = 'completed'),
                    failed_files = (SELECT COUNT(*) FROM files WHERE status = 'failed'),
                    pending_files = (SELECT COUNT(*) FROM files WHERE status = 'pending'),
                    processing_files = (SELECT COUNT(*) FROM files WHERE status = 'processing'),
                    
                    total_original_size = COALESCE((SELECT SUM(size_bytes) FROM files), 0),
                    total_transcoded_size = COALESCE((SELECT SUM(output_size_bytes) FROM files WHERE status = 'completed'), 0),
                    total_savings_bytes = COALESCE((SELECT SUM(savings_bytes) FROM files WHERE status = 'completed'), 0),
                    
                    updated_at = CURRENT_TIMESTAMP
            ''')
            
            # Calculate average savings percentage
            cursor.execute('''
                SELECT AVG(savings_percent) FROM files WHERE status = 'completed'
            ''')
            avg_savings = cursor.fetchone()[0] or 0
            
            cursor.execute('''
                UPDATE statistics SET 
                    total_savings_percent = ?,
                    estimated_total_savings = CAST(total_original_size * ? / 100.0 AS INTEGER),
                    estimated_final_size = CAST(total_original_size * (100.0 - ?) / 100.0 AS INTEGER)
            ''', (avg_savings, avg_savings, avg_savings))
            
            conn.commit()
            
            # Return statistics
            cursor.execute('SELECT * FROM statistics LIMIT 1')
            row = cursor.fetchone()
            return dict(row) if row else {}
    
    def get_all_files(self, status=None):
        """Get all files, optionally filtered by status"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            if status:
                cursor.execute('SELECT * FROM files WHERE status = ? ORDER BY created_at DESC', (status,))
            else:
                cursor.execute('SELECT * FROM files ORDER BY created_at DESC')
            
            return [dict(row) for row in cursor.fetchall()]
    
    def get_file_by_id(self, file_id):
        """Get file by ID"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM files WHERE id = ?', (file_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def mark_file_processing(self, file_id):
        """Mark file as currently processing"""
        self.update_file_status(file_id, 'processing', 
                               started_at=datetime.now().isoformat())
    
    def mark_file_completed(self, file_id, output_size, savings_bytes, savings_percent):
        """Mark file as completed"""
        self.update_file_status(file_id, 'completed',
                               completed_at=datetime.now().isoformat(),
                               output_size_bytes=output_size,
                               savings_bytes=savings_bytes,
                               savings_percent=savings_percent,
                               progress_percent=100.0)
    
    def mark_file_failed(self, file_id, error_message):
        """Mark file as failed"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE files 
                SET status = 'failed', 
                    error_message = ?,
                    retry_count = retry_count + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (error_message, file_id))
            conn.commit()
    
    def reset_failed_files(self):
        """Reset all failed files to pending status"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE files 
                SET status = 'pending',
                    progress_percent = 0,
                    error_message = NULL,
                    started_at = NULL,
                    completed_at = NULL,
                    retry_count = 0,
                    updated_at = CURRENT_TIMESTAMP
                WHERE status = 'failed'
            ''')
            count = cursor.rowcount
            conn.commit()
            return count
    
    def reset_file(self, file_id):
        """Reset a specific file to pending status"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE files 
                SET status = 'pending',
                    progress_percent = 0,
                    error_message = NULL,
                    started_at = NULL,
                    completed_at = NULL,
                    output_size_bytes = NULL,
                    savings_bytes = NULL,
                    savings_percent = NULL,
                    retry_count = 0,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (file_id,))
            conn.commit()
    
    def skip_file(self, file_id):
        """Skip a file by marking it as completed without processing"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE files 
                SET status = 'completed',
                    progress_percent = 100,
                    error_message = 'Manually skipped',
                    completed_at = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (datetime.now().isoformat(), file_id))
            conn.commit()
    
    def delete_file(self, file_id):
        """Delete a file from the database"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM files WHERE id = ?', (file_id,))
            conn.commit()
    
    def delete_completed_files(self):
        """Delete all completed files from database"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM files WHERE status = 'completed'")
            count = cursor.rowcount
            conn.commit()
            return count
    
    def retry_file(self, file_id):
        """Retry a file stuck in processing by resetting it to pending"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE files 
                SET status = 'pending',
                    progress_percent = 0,
                    started_at = NULL,
                    retry_count = retry_count + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (file_id,))
            conn.commit()
