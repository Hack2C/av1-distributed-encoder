# AV1 Media Transcoding System

Automated media library transcoding to AV1 (SVT-AV1) with Opus audio for maximum disk space savings while preserving visual quality.

## Features

- ✅ Automatic transcoding to AV1 (SVT-AV1 preset 0) + Opus audio
- ✅ Quality-aware CRF selection based on source bitrate/resolution/codec
- ✅ One file at a time processing (low priority)
- ✅ Simple web interface for monitoring
- ✅ Error-aware: handles NAS disconnection and app shutdowns
- ✅ Disk space estimation and tracking
- ✅ Safe file replacement with backup
- ✅ Testing mode to verify before deleting originals

## Requirements

### System Dependencies
```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y ffmpeg python3 python3-pip

# Install SVT-AV1 encoder
sudo apt-get install -y libsvtav1enc-dev libsvtav1-1

# Or build from source if not available
git clone https://gitlab.com/AOMediaCodec/SVT-AV1.git
cd SVT-AV1 && ./build.sh && sudo make install
```

### Python Dependencies
```bash
pip3 install -r requirements.txt
```

## Installation

1. Clone or copy this project to your system
2. Install dependencies (see above)
3. Edit `config.json` to match your setup:
   - Update `source_directories` to your media folders
   - Set `temp_directory` to a location with enough space
   - Set `testing_mode: true` for initial runs

## Configuration

Edit `config.json`:

```json
{
  "source_directories": ["path/to/Movies", "path/to/TV"],
  "temp_directory": "/tmp/av1_transcoding",
  "testing_mode": true,  // Keep .bak files
  "web_server": {
    "port": 8080
  }
}
```

## Usage

### Start the transcoding service:
```bash
python3 transcode.py
```

### Access the web interface:
Open browser to: `http://localhost:8080`

### Monitor progress:
The web interface shows:
- Current file being processed
- Overall progress
- Disk space savings
- Queue status

## How It Works

1. Scans media directories for video files
2. For each file:
   - Creates `.av1.inprogress` marker
   - Copies to temp location
   - Analyzes source (codec, bitrate, resolution, HDR)
   - Looks up optimal CRF and audio bitrate from JSON files
   - Transcodes with SVT-AV1 + Opus
   - Verifies output
   - Replaces original safely
   - Deletes backup (if not testing mode)

## Quality Lookup Tables

- `quality_lookup.json`: Maps source video characteristics to optimal AV1 CRF values
- `audio_codec_lookup.json`: Maps source audio to optimal Opus bitrate

Values optimized for perceptually lossless quality with maximum compression.

## Safety Features

- **Testing Mode**: Keeps `.bak` files for manual verification
- **Atomic Operations**: Uses temp files to avoid corruption
- **Verification**: Checks transcoded files before replacing
- **Low Priority**: Uses `nice` and `ionice` to minimize impact
- **Resume Support**: Continues from last checkpoint after interruption

## License

MIT
