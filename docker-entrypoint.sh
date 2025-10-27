#!/bin/bash
# SMB/CIFS Mount Script for Docker Container
# This script mounts network shares before starting the application

set -e

echo "=== AV1 Transcoding - SMB Mount Script ==="

# Check if SMB shares are configured
if [ -n "$SMB_SHARES" ]; then
    echo "Mounting multiple SMB shares..."
    IFS=',' read -ra SHARES <<< "$SMB_SHARES"
    for share_config in "${SHARES[@]}"; do
        # Parse: [user:pass@]host/share/mountpoint
        if [[ $share_config =~ ^([^@]+@)?([^/]+)/([^/]+)/(.+)$ ]]; then
            creds="${BASH_REMATCH[1]%@}"
            host="${BASH_REMATCH[2]}"
            share="${BASH_REMATCH[3]}"
            mountpoint="${BASH_REMATCH[4]}"
            
            # Parse credentials if provided
            if [ -n "$creds" ]; then
                username="${creds%:*}"
                password="${creds#*:}"
            else
                username="${SMB_USERNAME:-guest}"
                password="${SMB_PASSWORD:-}"
            fi
            
            echo "Mounting //$host/$share to $mountpoint"
            mkdir -p "$mountpoint"
            
            mount_opts="username=$username,vers=${SMB_VERSION:-3.0},iocharset=utf8,file_mode=0777,dir_mode=0777"
            if [ -n "$password" ]; then
                mount_opts="$mount_opts,password=$password"
            fi
            if [ -n "$SMB_DOMAIN" ]; then
                mount_opts="$mount_opts,domain=$SMB_DOMAIN"
            fi
            
            mount -t cifs "//$host/$share" "$mountpoint" -o "$mount_opts" || {
                echo "ERROR: Failed to mount //$host/$share"
                exit 1
            }
            echo "✓ Mounted //$host/$share"
        else
            echo "ERROR: Invalid share format: $share_config"
            echo "Expected: [user:pass@]host/share/mountpoint"
            exit 1
        fi
    done

elif [ -n "$SMB_HOST" ] && [ -n "$SMB_SHARE" ]; then
    # Single SMB share configuration
    echo "Mounting SMB share: //$SMB_HOST/$SMB_SHARE"
    
    MOUNT_POINT="/media/${SMB_SHARE}"
    mkdir -p "$MOUNT_POINT"
    
    MOUNT_OPTS="username=${SMB_USERNAME:-guest},vers=${SMB_VERSION:-3.0},iocharset=utf8,file_mode=0777,dir_mode=0777"
    
    if [ -n "$SMB_PASSWORD" ]; then
        MOUNT_OPTS="$MOUNT_OPTS,password=$SMB_PASSWORD"
    fi
    
    if [ -n "$SMB_DOMAIN" ]; then
        MOUNT_OPTS="$MOUNT_OPTS,domain=$SMB_DOMAIN"
    fi
    
    mount -t cifs "//$SMB_HOST/$SMB_SHARE" "$MOUNT_POINT" -o "$MOUNT_OPTS" || {
        echo "ERROR: Failed to mount SMB share"
        exit 1
    }
    
    echo "✓ Mounted //$SMB_HOST/$SMB_SHARE to $MOUNT_POINT"
else
    echo "No SMB shares configured, skipping mount"
fi

echo "=== Initializing configuration ==="
python3 /app/init_config.py

echo "=== Starting application ==="
exec "$@"
