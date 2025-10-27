@echo off
REM AV1 Worker Client Launcher for Windows
REM
REM Before running:
REM 1. Install Docker Desktop for Windows
REM 2. Edit docker-compose.worker.yml:
REM    - Set your media directory paths (D:/Movies, etc.)
REM    - Set MASTER_IP to your Linux server's IP address
REM 3. Start Docker Desktop
REM 4. Run this script

echo ========================================
echo AV1 Transcoding Worker - Starting...
echo ========================================
echo.
echo Make sure you have edited docker-compose.worker.yml
echo to set the correct master server IP and media paths!
echo.
pause

docker-compose -f docker-compose.worker.yml up --build
