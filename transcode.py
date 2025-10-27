#!/usr/bin/env python3
"""
AV1 Media Transcoding System - Main Entry Point
Orchestrates the transcoding service, web interface, and background processing.
"""

import os
import sys
import signal
import logging
from pathlib import Path
from threading import Thread, Event

from flask import Flask
from flask_socketio import SocketIO
from flask_cors import CORS

from lib.config import Config
from lib.database import Database
from lib.scanner import MediaScanner
from lib.transcoder import TranscodingEngine
from lib.web_api import register_routes

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('transcoding.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Global shutdown event
shutdown_event = Event()

class TranscodingService:
    """Main service orchestrator"""
    
    def __init__(self, config_path='config.json'):
        self.config = Config(config_path)
        self.db = Database()
        self.scanner = MediaScanner(self.config, self.db)
        self.engine = TranscodingEngine(self.config, self.db, shutdown_event)
        
        # Flask app setup
        self.app = Flask(__name__, 
                        static_folder='web',
                        static_url_path='')
        CORS(self.app)
        self.socketio = SocketIO(self.app, cors_allowed_origins="*")
        
        # Register API routes
        register_routes(self.app, self.db, self.scanner, self.engine)
        
        # Connect engine to socketio for progress updates
        self.engine.set_socketio(self.socketio)
        
        logger.info("Transcoding service initialized")
    
    def start(self):
        """Start the transcoding service"""
        logger.info("Starting AV1 Transcoding Service...")
        
        # Initial scan of media libraries
        logger.info("Performing initial media library scan...")
        self.scanner.scan_all()
        
        # Start transcoding engine in background thread
        engine_thread = Thread(target=self.engine.run, daemon=True)
        engine_thread.start()
        logger.info("Transcoding engine started")
        
        # Start web server
        host = self.config.get('web_server.host', '0.0.0.0')
        port = self.config.get('web_server.port', 8080)
        
        logger.info(f"Starting web interface at http://{host}:{port}")
        logger.info(f"Testing mode: {self.config.get('testing_mode', True)}")
        
        try:
            self.socketio.run(self.app, host=host, port=port, debug=False)
        except KeyboardInterrupt:
            logger.info("Received shutdown signal")
            self.shutdown()
    
    def shutdown(self):
        """Gracefully shutdown the service"""
        logger.info("Shutting down transcoding service...")
        shutdown_event.set()
        self.engine.stop()
        logger.info("Service stopped")

def signal_handler(signum, frame):
    """Handle termination signals"""
    logger.info(f"Received signal {signum}")
    shutdown_event.set()
    sys.exit(0)

def main():
    """Main entry point"""
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Check for config file
    config_path = 'config.json'
    if not os.path.exists(config_path):
        logger.error(f"Config file not found: {config_path}")
        logger.error("Please create config.json based on config.example.json")
        sys.exit(1)
    
    # Start service
    service = TranscodingService(config_path)
    service.start()

if __name__ == '__main__':
    main()
