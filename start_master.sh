#!/bin/bash
# Start Master Server

cd "$(dirname "$0")"

echo "Starting AV1 Master Transcoding Server..."
python3 master_server.py
