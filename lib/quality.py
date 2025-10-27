"""
Quality settings lookup based on source media characteristics
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class QualityLookup:
    """Lookup optimal encoding settings based on source characteristics"""
    
    def __init__(self):
        self.video_lookup = self._load_json('quality_lookup.json')
        self.audio_lookup = self._load_json('audio_codec_lookup.json')
    
    def _load_json(self, filename):
        """Load JSON lookup table"""
        try:
            with open(filename, 'r') as f:
                data = json.load(f)
                logger.info(f"Loaded {filename}")
                return data
        except FileNotFoundError:
            logger.error(f"Lookup file not found: {filename}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in {filename}: {e}")
            raise
    
    def get_video_crf(self, codec, bitdepth, hdr, resolution, bitrate_category):
        """
        Get optimal CRF value for AV1 encoding.
        
        Args:
            codec: Source codec (h264, h265, hevc, vp9, av1, etc.)
            bitdepth: 8 or 10 bit
            hdr: 'HDR' or 'SDR'
            resolution: '720p', '1080p', '1440p', '4k'
            bitrate_category: Bitrate category like '1M', '4M', '10M', etc.
        
        Returns:
            CRF value (int)
        """
        # Normalize codec name
        codec = codec.lower()
        if codec in ['x264', 'h.264']:
            codec = 'h264'
        elif codec in ['x265', 'h.265']:
            codec = 'h265'
        
        # Get bit depth category
        bitdepth_key = '10bit' if bitdepth >= 10 else '8bit'
        
        try:
            # Try to get from specific codec
            if codec in self.video_lookup:
                codec_data = self.video_lookup[codec]
                
                if bitdepth_key in codec_data:
                    depth_data = codec_data[bitdepth_key]
                    
                    if hdr in depth_data:
                        hdr_data = depth_data[hdr]
                        
                        if resolution in hdr_data:
                            res_data = hdr_data[resolution]
                            
                            if bitrate_category in res_data:
                                crf = res_data[bitrate_category]
                                logger.debug(f"CRF lookup: {codec}/{bitdepth_key}/{hdr}/{resolution}/{bitrate_category} = {crf}")
                                return crf
                            else:
                                # Find closest bitrate category
                                return self._find_closest_bitrate(res_data, bitrate_category)
            
            # Fallback to default
            logger.warning(f"Using default CRF for {codec}/{bitdepth_key}/{hdr}/{resolution}")
            default = self.video_lookup.get('default', {})
            return default.get(bitdepth_key, {}).get(hdr, {}).get(resolution, 25)
        
        except Exception as e:
            logger.error(f"Error in CRF lookup: {e}", exc_info=True)
            return 25  # Safe default
    
    def _find_closest_bitrate(self, res_data, target_category):
        """Find the closest bitrate category in the data"""
        # Extract numeric value from category
        target_value = self._bitrate_to_number(target_category)
        
        closest_key = None
        closest_diff = float('inf')
        
        for key in res_data.keys():
            key_value = self._bitrate_to_number(key)
            diff = abs(key_value - target_value)
            
            if diff < closest_diff:
                closest_diff = diff
                closest_key = key
        
        if closest_key:
            logger.debug(f"Using closest bitrate {closest_key} for {target_category}")
            return res_data[closest_key]
        
        return 25  # Default fallback
    
    def _bitrate_to_number(self, category):
        """Convert bitrate category to numeric value for comparison"""
        # Remove 'M' and '+', convert to float
        value = category.replace('M', '').replace('+', '')
        try:
            return float(value)
        except:
            return 0
    
    def get_opus_bitrate(self, source_codec, channels, source_bitrate_category):
        """
        Get optimal Opus bitrate based on source audio.
        
        Args:
            source_codec: Source audio codec (aac, ac3, dts, etc.)
            channels: Number of channels (1, 2, 6, 8)
            source_bitrate_category: Bitrate category like '64k', '192k', etc.
        
        Returns:
            Opus bitrate in kbps (int)
        """
        # Normalize codec
        codec = source_codec.lower()
        if codec in ['e-ac3', 'eac-3']:
            codec = 'eac3'
        
        # Get channel category
        if channels <= 1:
            channel_key = '1ch'
        elif channels <= 2:
            channel_key = '2ch'
        elif channels <= 6:
            channel_key = '6ch'
        else:
            channel_key = '8ch'
        
        try:
            # Try codec-specific lookup
            if codec in self.audio_lookup:
                codec_data = self.audio_lookup[codec]
                
                if channel_key in codec_data:
                    channel_data = codec_data[channel_key]
                    
                    if source_bitrate_category in channel_data:
                        bitrate = channel_data[source_bitrate_category]
                        logger.debug(f"Opus bitrate lookup: {codec}/{channel_key}/{source_bitrate_category} = {bitrate}k")
                        return bitrate
                    else:
                        # Find closest
                        return self._find_closest_audio_bitrate(channel_data, source_bitrate_category)
            
            # Fallback to default
            logger.warning(f"Using default Opus bitrate for {codec}/{channel_key}")
            default = self.audio_lookup.get('default', {})
            return default.get(channel_key, {}).get(source_bitrate_category, 96)
        
        except Exception as e:
            logger.error(f"Error in Opus bitrate lookup: {e}", exc_info=True)
            # Safe defaults based on channels
            if channels <= 1:
                return 48
            elif channels <= 2:
                return 96
            elif channels <= 6:
                return 160
            else:
                return 192
    
    def _find_closest_audio_bitrate(self, channel_data, target_category):
        """Find closest audio bitrate category"""
        target_value = self._audio_bitrate_to_number(target_category)
        
        closest_key = None
        closest_diff = float('inf')
        
        for key in channel_data.keys():
            key_value = self._audio_bitrate_to_number(key)
            diff = abs(key_value - target_value)
            
            if diff < closest_diff:
                closest_diff = diff
                closest_key = key
        
        if closest_key:
            logger.debug(f"Using closest audio bitrate {closest_key} for {target_category}")
            return channel_data[closest_key]
        
        return 96  # Default
    
    def _audio_bitrate_to_number(self, category):
        """Convert audio bitrate category to numeric value"""
        # Remove 'k' and '+', convert to int
        value = category.replace('k', '').replace('+', '')
        try:
            return int(value)
        except:
            return 0
