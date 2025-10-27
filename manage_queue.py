#!/usr/bin/env python3
"""
Manage file queue status - reset, skip, or view files
"""

import sqlite3
import sys
from pathlib import Path

def show_failed_files(db_path='transcoding.db'):
    """Show all failed files"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, filename, directory, error_message, updated_at 
        FROM files 
        WHERE status = 'failed' OR status = 'error'
        ORDER BY updated_at DESC
    """)
    
    files = cursor.fetchall()
    conn.close()
    
    if not files:
        print("✅ No failed files found")
        return []
    
    print(f"\n❌ Failed files ({len(files)}):")
    print("=" * 80)
    for file_id, filename, directory, error, updated in files:
        print(f"ID: {file_id}")
        print(f"  File: {filename}")
        print(f"  Dir:  {directory}")
        print(f"  Error: {error or 'No error message'}")
        print(f"  Date: {updated}")
        print()
    
    return files

def reset_to_pending(file_ids=None, db_path='transcoding.db'):
    """Reset files to pending status"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    if file_ids:
        # Reset specific files
        placeholders = ','.join('?' * len(file_ids))
        cursor.execute(f"""
            UPDATE files 
            SET status = 'pending',
                progress_percent = 0,
                error_message = NULL,
                started_at = NULL,
                completed_at = NULL,
                retry_count = 0
            WHERE id IN ({placeholders})
        """, file_ids)
        count = cursor.rowcount
    else:
        # Reset all failed files
        cursor.execute("""
            UPDATE files 
            SET status = 'pending',
                progress_percent = 0,
                error_message = NULL,
                started_at = NULL,
                completed_at = NULL,
                retry_count = 0
            WHERE status = 'failed' OR status = 'error'
        """)
        count = cursor.rowcount
    
    conn.commit()
    conn.close()
    
    print(f"✅ Reset {count} file(s) to pending status")

def skip_files(file_ids, db_path='transcoding.db'):
    """Mark files as skipped (completed without processing)"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    placeholders = ','.join('?' * len(file_ids))
    cursor.execute(f"""
        UPDATE files 
        SET status = 'completed',
            progress_percent = 100,
            error_message = 'Manually skipped'
        WHERE id IN ({placeholders})
    """, file_ids)
    
    count = cursor.rowcount
    conn.commit()
    conn.close()
    
    print(f"⏭️  Skipped {count} file(s)")

def show_all_status(db_path='transcoding.db'):
    """Show file counts by status"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT status, COUNT(*) 
        FROM files 
        GROUP BY status
        ORDER BY status
    """)
    
    stats = cursor.fetchall()
    conn.close()
    
    print("\n📊 File Status Summary:")
    print("=" * 40)
    for status, count in stats:
        print(f"  {status:12s}: {count:3d} files")
    print()

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Manage transcoding queue')
    parser.add_argument('action', choices=['list', 'reset', 'skip', 'status'],
                       help='Action to perform')
    parser.add_argument('--ids', type=int, nargs='+',
                       help='File IDs to operate on')
    parser.add_argument('--all', action='store_true',
                       help='Apply to all failed files')
    
    args = parser.parse_args()
    
    if args.action == 'list':
        show_failed_files()
    
    elif args.action == 'reset':
        if args.all:
            failed = show_failed_files()
            if failed:
                confirm = input(f"\nReset {len(failed)} failed files to pending? (y/N): ")
                if confirm.lower() == 'y':
                    reset_to_pending()
                else:
                    print("Cancelled")
        elif args.ids:
            reset_to_pending(args.ids)
        else:
            print("Use --all to reset all failed files, or --ids to reset specific files")
    
    elif args.action == 'skip':
        if not args.ids:
            print("Error: --ids required for skip action")
            sys.exit(1)
        skip_files(args.ids)
    
    elif args.action == 'status':
        show_all_status()
