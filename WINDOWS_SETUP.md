# Windows Worker Setup Guide

This guide helps you set up AV1 encoding workers on Windows Desktop using Docker Desktop.

## Prerequisites

1. **Docker Desktop for Windows** - Install from https://www.docker.com/products/docker-desktop/
2. **Network access** to the master server (replace `YOUR_MASTER_IP` with actual IP address)

## Quick Start

### 1. Download the configuration file

Download `docker-compose.windows-worker.yml` from this repository.

### 2. Edit the configuration

Open `docker-compose.windows-worker.yml` and replace `MASTER_IP_HERE` with your master server's IP address:

```yaml
command: python3 worker_client.py http://YOUR_MASTER_IP:8090
```

And also in the environment section:
```yaml
- MASTER_URL=http://YOUR_MASTER_IP:8090
```

### 3. Start the worker

Open PowerShell or Command Prompt in the folder containing the file:

```powershell
# Start 1 worker
docker-compose -f docker-compose.windows-worker.yml up -d

# Start 4 workers (scales based on your CPU)
docker-compose -f docker-compose.windows-worker.yml up -d --scale worker=4
```

### 3. Check worker status

```powershell
# View logs
docker-compose -f docker-compose.windows-worker.yml logs -f

```powershell
# Check if workers are connected
# Open browser to: http://YOUR_MASTER_IP:8090
```

### 4. Stop workers
```

### 4. Stop workers

```powershell
docker-compose -f docker-compose.windows-worker.yml down
```

## Configuration

The worker connects to the master using **file distribution mode** - files are transferred via HTTP, no shared storage needed.

**Important:** Make sure to replace `MASTER_IP_HERE` with your actual master server IP address in the docker-compose file before starting.

### Encoding Quality

- **SVT_AV1_PRESET=0** - Slowest encoding, highest quality (default)
- Preset 0 provides the best compression but is very slow
- You can change this in the docker-compose file if needed

### Resource Limits

Default configuration:
- Memory: 8GB limit, 4GB reserved
- CPUs: No limit (uses all available cores)

To adjust, edit the `docker-compose.windows-worker.yml` file:

```yaml
deploy:
  resources:
    limits:
      memory: 16G  # Increase if you have more RAM
    reservations:
      cpus: '8'    # Number of CPU cores to dedicate
```

### Storage Locations

Workers create two folders in the same directory:
- `./worker-data` - Configuration files
- `./worker-temp` - Temporary transcoding files

These can be deleted when workers are stopped.

## Troubleshooting

### Can't connect to master

If the worker can't reach the master, try using host network mode:

Edit `docker-compose.windows-worker.yml` and uncomment:
```yaml
network_mode: "host"
```

### Out of memory errors

Reduce memory limits or reduce the number of workers:
```powershell
docker-compose -f docker-compose.windows-worker.yml up -d --scale worker=2
```

### Check worker logs

```powershell
docker-compose -f docker-compose.windows-worker.yml logs worker
```

## Master Server

The master server dashboard is available at:
**http://YOUR_MASTER_IP:8090** (replace with your master server's IP)

You can monitor:
- Worker status
- Encoding progress
- Queue statistics

## Scaling Workers

Run multiple workers on powerful machines:

```powershell
# 8 workers for a high-end PC
docker-compose -f docker-compose.windows-worker.yml up -d --scale worker=8

# Scale down to 2 workers
docker-compose -f docker-compose.windows-worker.yml up -d --scale worker=2
```

Each worker will:
- Request a file from the master
- Encode it locally
- Upload the result back
- Request the next file

## Performance Notes

- Preset 0 is **very slow** but produces the best quality
- Expected speed: ~0.1-0.3 fps per worker on modern CPUs
- A 24-minute episode may take 2-8 hours per file
- Multiple workers encode different files in parallel
