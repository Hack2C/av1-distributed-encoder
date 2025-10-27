#!/bin/bash
# Start Worker Client

cd "$(dirname "$0")"

if [ -z "$1" ]; then
    echo "Usage: ./start_worker.sh <master_url>"
    echo "Example: ./start_worker.sh http://192.168.1.100:8090"
    exit 1
fi

MASTER_URL=$1

echo "Starting AV1 Worker Client..."
echo "Master Server: $MASTER_URL"
python3 worker_client.py "$MASTER_URL"
