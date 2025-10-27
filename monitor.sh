#!/bin/bash
# Simple monitoring script for transcoding progress

echo "🎬 AV1 Transcoding System - Status Monitor"
echo "=========================================="
echo ""

# Check containers
echo "📦 Container Status:"
docker compose -f docker-compose.filedist-test.yml ps --format "table {{.Name}}\t{{.Status}}"
echo ""

# Check database status
echo "📊 Job Queue Status:"
docker exec av1-master python3 -c "
import sqlite3
conn = sqlite3.connect('/data/transcoding.db')
cursor = conn.cursor()
cursor.execute('SELECT status, COUNT(*) FROM files GROUP BY status')
for row in cursor.fetchall():
    print(f'  {row[0]:12} : {row[1]:3}')
cursor.execute('SELECT COUNT(*) FROM files')
total = cursor.fetchone()[0]
cursor.execute('SELECT COUNT(*) FROM files WHERE status=\"completed\"')
completed = cursor.fetchone()[0]
if total > 0:
    percent = (completed * 100) / total
    print(f'  Progress    : {completed}/{total} ({percent:.1f}%)')
"
echo ""

# Check for backup files
echo "💾 Backup Files (TESTING_MODE):"
BAK_COUNT=$(find TestLib -name "*.bak" 2>/dev/null | wc -l)
echo "  .bak files  : $BAK_COUNT"
echo ""

# Check web UI
echo "🌐 Web Interface:"
echo "  http://localhost:8090"
echo ""

echo "Use: docker logs av1-worker1 --tail 20    # View worker logs"
echo "Use: docker logs av1-master --tail 20     # View master logs"
echo "Use: watch -n 5 ./monitor.sh              # Auto-refresh every 5 sec"
