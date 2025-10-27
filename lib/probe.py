"""
FFprobe wrapper for extracting media file metadata
"""

import json
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

class MediaProbe:
    """Extract metadata from media files using ffprobe"""
    
    @staticmethod
    def probe_file(file_path):
        """
        Extract comprehensive metadata from a media file.
        Returns dict with video and audio stream information.
        """
        try:
            cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                '-show_streams',
                str(file_path)
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode != 0:
                logger.error(f"ffprobe failed for {file_path}: {result.stderr}")
                return None
            
            data = json.loads(result.stdout)
            
            # Parse video and audio streams
            metadata = {
                'video': MediaProbe._parse_video_stream(data),
                'audio': MediaProbe._parse_audio_streams(data),
                'format': MediaProbe._parse_format(data)
            }
            
            return metadata
        
        except subprocess.TimeoutExpired:
            logger.error(f"ffprobe timeout for {file_path}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse ffprobe output: {e}")
            return None
        except Exception as e:
            logger.error(f"Error probing {file_path}: {e}", exc_info=True)
            return None
    
    @staticmethod
    def _parse_video_stream(data):
        """Extract video stream information"""
        video_streams = [s for s in data.get('streams', []) if s.get('codec_type') == 'video']
        
        if not video_streams:
            return None
        
        stream = video_streams[0]  # Take first video stream
        
        # Get codec
        codec = stream.get('codec_name', 'unknown')
        
        # Get resolution
        width = stream.get('width', 0)
        height = stream.get('height', 0)
        resolution = MediaProbe._classify_resolution(width, height)
        
        # Get bitrate (from stream or format)
        bitrate = int(stream.get('bit_rate', 0))
        if bitrate == 0 and 'format' in data:
            bitrate = int(data['format'].get('bit_rate', 0))
        
        # Get bit depth
        pix_fmt = stream.get('pix_fmt', '')
        bitdepth = 10 if '10' in pix_fmt else 8
        
        # Detect HDR (enhanced detection with dynamic HDR support)
        color_transfer = stream.get('color_transfer', '')
        color_space = stream.get('color_space', '')
        hdr_info = MediaProbe._detect_hdr(color_transfer, color_space, stream)
        
        return {
            'codec': codec,
            'bitrate': bitrate,
            'width': width,
            'height': height,
            'resolution': resolution,
            'bitdepth': bitdepth,
            'hdr': hdr_info['type'],  # 'SDR', 'HDR10', 'HDR10+', 'Dolby Vision'
            'hdr_dynamic': hdr_info['dynamic'],  # True for HDR10+/Dolby Vision
            'color_transfer': hdr_info['color_transfer'],
            'color_space': hdr_info['color_space'],
            'fps': MediaProbe._get_fps(stream),
            'pix_fmt': pix_fmt
        }
    
    @staticmethod
    def _parse_audio_streams(data):
        """Extract audio stream information"""
        audio_streams = [s for s in data.get('streams', []) if s.get('codec_type') == 'audio']
        
        if not audio_streams:
            return []
        
        result = []
        for stream in audio_streams:
            codec = stream.get('codec_name', 'unknown')
            channels = stream.get('channels', 2)
            bitrate = int(stream.get('bit_rate', 0))
            sample_rate = int(stream.get('sample_rate', 48000))
            
            result.append({
                'codec': codec,
                'channels': channels,
                'bitrate': bitrate,
                'sample_rate': sample_rate,
                'language': stream.get('tags', {}).get('language', 'und')
            })
        
        return result
    
    @staticmethod
    def _parse_format(data):
        """Extract format information"""
        fmt = data.get('format', {})
        
        return {
            'container': fmt.get('format_name', ''),
            'duration': float(fmt.get('duration', 0)),
            'size': int(fmt.get('size', 0)),
            'bitrate': int(fmt.get('bit_rate', 0))
        }
    
    @staticmethod
    def _classify_resolution(width, height):
        """
        Classify resolution into standard categories.
        Uses pixel count for ultra-wide content (like 1920x808).
        """
        # Calculate total pixels
        total_pixels = width * height
        
        # Standard resolution pixel counts (with 73% threshold for ultra-wide)
        # 4K: 3840x2160 = 8,294,400 pixels (threshold: 6,054,912)
        # 1440p: 2560x1440 = 3,686,400 pixels (threshold: 2,691,072)
        # 1080p: 1920x1080 = 2,073,600 pixels (threshold: 1,513,728)
        # 720p: 1280x720 = 921,600 pixels (threshold: 672,768)
        
        if total_pixels >= 6_054_912 or height >= 2160:
            return '4k'
        elif total_pixels >= 2_691_072 or height >= 1440:
            return '1440p'
        elif total_pixels >= 1_513_728 or height >= 1080:
            return '1080p'
        elif total_pixels >= 672_768 or height >= 720:
            return '720p'
        else:
            return '720p'  # Default for lower resolutions
    
    @staticmethod
    def _detect_hdr(color_transfer, color_space, stream):
        """
        Detect HDR type and dynamic metadata.
        Returns dict with HDR information.
        """
        hdr_transfers = ['smpte2084', 'arib-std-b67', 'smpte428']
        hdr_spaces = ['bt2020nc', 'bt2020c']
        
        hdr_type = 'SDR'
        has_dynamic_metadata = False
        
        # Check color transfer and space for basic HDR
        if color_transfer in hdr_transfers or color_space in hdr_spaces:
            hdr_type = 'HDR10'  # Base HDR (static)
        
        # Check for side data metadata
        side_data = stream.get('side_data_list', [])
        for data in side_data:
            data_type = data.get('side_data_type', '')
            
            # Static HDR10 mastering display metadata
            if 'Mastering display' in data_type:
                if hdr_type == 'SDR':
                    hdr_type = 'HDR10'
            
            # Content light level metadata
            if 'Content light level' in data_type:
                if hdr_type == 'SDR':
                    hdr_type = 'HDR10'
            
            # Dynamic HDR10+ metadata (SMPTE ST 2094-40)
            if 'HDR Dynamic Metadata SMPTE2094-40' in data_type or 'SMPTE2094-40' in data_type:
                hdr_type = 'HDR10+'
                has_dynamic_metadata = True
            
            # Dolby Vision configuration record
            if 'DOVI configuration record' in data_type or 'Dolby Vision' in data_type:
                hdr_type = 'Dolby Vision'
                has_dynamic_metadata = True
        
        return {
            'type': hdr_type,
            'dynamic': has_dynamic_metadata,
            'color_transfer': color_transfer,
            'color_space': color_space
        }
    
    @staticmethod
    def _get_fps(stream):
        """Extract framerate from stream"""
        r_frame_rate = stream.get('r_frame_rate', '0/1')
        try:
            num, den = r_frame_rate.split('/')
            return float(num) / float(den)
        except:
            return 0.0
    
    @staticmethod
    def get_bitrate_category(bitrate):
        """
        Convert bitrate to lookup category string.
        Examples: 1M, 2M, 4M, 6M, 8M, 10M, 15M, 20M, 30M, 40M+
        """
        bitrate_mbps = bitrate / 1_000_000
        
        if bitrate_mbps < 1.5:
            return '1M'
        elif bitrate_mbps < 3:
            return '2M'
        elif bitrate_mbps < 5:
            return '4M'
        elif bitrate_mbps < 7:
            return '6M'
        elif bitrate_mbps < 9:
            return '8M'
        elif bitrate_mbps < 12:
            return '10M'
        elif bitrate_mbps < 17:
            return '15M'
        elif bitrate_mbps < 25:
            return '20M'
        elif bitrate_mbps < 35:
            return '30M'
        else:
            return '40M+'
    
    @staticmethod
    def get_audio_bitrate_category(bitrate, codec):
        """
        Convert audio bitrate to lookup category string based on codec.
        Examples: 32k, 64k, 96k, 128k, 192k, 256k, 320k, 384k, 512k, 640k+
        """
        bitrate_kbps = bitrate / 1000
        
        # Different thresholds for different codecs
        if codec in ['aac', 'mp3']:
            if bitrate_kbps < 48:
                return '32k'
            elif bitrate_kbps < 80:
                return '64k'
            elif bitrate_kbps < 112:
                return '96k'
            elif bitrate_kbps < 160:
                return '128k'
            elif bitrate_kbps < 224:
                return '192k'
            elif bitrate_kbps < 288:
                return '256k'
            else:
                return '320k'
        
        elif codec in ['ac3', 'eac3']:
            if bitrate_kbps < 80:
                return '64k'
            elif bitrate_kbps < 112:
                return '96k'
            elif bitrate_kbps < 160:
                return '128k'
            elif bitrate_kbps < 224:
                return '192k'
            elif bitrate_kbps < 320:
                return '256k'
            elif bitrate_kbps < 448:
                return '384k'
            elif bitrate_kbps < 576:
                return '512k'
            else:
                return '640k+'
        
        elif codec in ['dts', 'truehd', 'flac', 'pcm']:
            if bitrate_kbps < 384:
                return '256k'
            elif bitrate_kbps < 640:
                return '512k'
            elif bitrate_kbps < 896:
                return '768k'
            elif bitrate_kbps < 1280:
                return '1024k'
            elif bitrate_kbps < 2000:
                return '1536k+'
            elif bitrate_kbps < 3000:
                return '2000k'
            elif bitrate_kbps < 5000:
                return '4000k'
            else:
                return '6000k+'
        
        # Default fallback
        if bitrate_kbps < 96:
            return '64k'
        elif bitrate_kbps < 160:
            return '128k'
        elif bitrate_kbps < 256:
            return '192k'
        else:
            return '384k'
    
    @staticmethod
    def get_channel_category(channels):
        """Convert channel count to category string"""
        if channels <= 1:
            return '1ch'
        elif channels <= 2:
            return '2ch'
        elif channels <= 6:
            return '6ch'
        else:
            return '8ch'
