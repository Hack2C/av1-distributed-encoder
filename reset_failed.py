#!/usr/bin/env python3
"""
Reset failed/error files back to pending status
"""

import sqlite3
import sys

def reset_failed_files(db_path='transcoding.db'):
    """Reset all failed/error files to pending status"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get count of failed files
        cursor.execute("SELECT COUNT(*) FROM files WHERE status = 'failed' OR status = 'error'")
        count = cursor.fetchone()[0]
        
        if count == 0:
            print("No failed files found.")
            return
        
        print(f"Found {count} failed file(s)")
        
        # Reset failed files to pending
        cursor.execute("""
            UPDATE files 
            SET status = 'pending',
                progress_percent = 0,
                error_message = NULL,
                started_at = NULL,
                completed_at = NULL
            WHERE status = 'failed' OR status = 'error'
        """)
        
        conn.commit()
        print(f"✅ Reset {count} file(s) to pending status")
        
        # Show the files
        cursor.execute("SELECT filename, directory FROM files WHERE status = 'pending'")
        files = cursor.fetchall()
        print(f"\nPending files ({len(files)}):")
        for filename, directory in files:
            print(f"  - {filename}")
            print(f"    {directory}")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    reset_failed_files()
