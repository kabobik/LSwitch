#!/usr/bin/env python3
"""
LSwitch CLI entry point with enhanced logging
"""

from __future__ import annotations
import sys
import argparse
import signal
import os
import logging
import logging.handlers
import traceback
from pathlib import Path
from datetime import datetime

from __version__ import __version__

# Global logger instance
logger = None


def setup_logging(debug: bool = False, log_file: str | None = None) -> logging.Logger:
    """Setup logging to both console and file
    
    Args:
        debug: Enable debug level logging
        log_file: Path to log file (default: ~/.lswitch.log)
    """
    global logger
    
    if logger is not None:
        return logger
    
    # Create logger
    logger = logging.getLogger('lswitch')
    logger.setLevel(logging.DEBUG if debug else logging.INFO)
    
    # Default log file location
    if log_file is None:
        log_file = os.path.expanduser('~/.lswitch.log')
    
    # Ensure log directory exists
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Format for logs
    fmt = logging.Formatter(
        '[%(asctime)s] %(levelname)-8s %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # File handler (rotate log file when it gets too large)
    try:
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10*1024*1024,  # 10 MB
            backupCount=5  # Keep 5 old log files
        )
        file_handler.setLevel(logging.DEBUG)  # Always log everything to file
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)
    except Exception as e:
        print(f"Warning: Could not setup file logging: {e}", file=sys.stderr)
    
    # Console handler (only errors in production, all in debug)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.DEBUG if debug else logging.WARNING)
    console_handler.setFormatter(fmt)
    logger.addHandler(console_handler)
    
    return logger


def main() -> int:
    """Main entry point for LSwitch"""
    # Setup early argument parsing just for version and help
    parser = argparse.ArgumentParser(
        prog='lswitch',
        description='Layout Switcher - быстрое переключение раскладки по двойному Shift',
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug mode with verbose logging'
    )
    parser.add_argument(
        '--config',
        type=str,
        default=None,
        help='Path to config file'
    )
    parser.add_argument(
        '--logfile',
        type=str,
        default=None,
        help='Path to log file (default: ~/.lswitch.log)'
    )
    parser.add_argument(
        '--version',
        action='version',
        version='%(prog)s ' + __version__
    )
    
    args = parser.parse_args()
    
    # Setup logging first
    log = setup_logging(debug=args.debug, log_file=args.logfile)
    
    log.info(f"{'='*60}")
    log.info(f"LSwitch started (version {__version__})")
    log.info(f"Debug mode: {args.debug}")
    log.info(f"PID: {os.getpid()}")
    log.info(f"{'='*60}")
    
    # Import after args parsing to avoid import-time side effects
    from lswitch.core import LSwitch
    from lswitch.config import load_config
    
    # Load configuration
    try:
        log.debug(f"Loading config from: {args.config or 'default'}")
        config = load_config(args.config, args.debug)
        log.info("✓ Config loaded successfully")
    except Exception as e:
        log.error(f"Failed to load config: {e}")
        log.debug(traceback.format_exc())
        return 1
    
    # Override debug flag if specified (ensure it's set)
    if args.debug:
        config['debug'] = True
    
    # Global flag to track why we're exiting
    exit_reason = None
    ls = None
    
    # Create and run LSwitch
    try:
        log.info(f"Creating LSwitch instance...")
        ls = LSwitch(args.config)
        
        # Override debug after construction
        if args.debug:
            ls.config['debug'] = True
        
        log.info("✓ LSwitch instance created")
        
        # Handle signals gracefully
        def signal_handler(signum: int, frame) -> None:
            nonlocal exit_reason
            signal_name = signal.Signals(signum).name
            exit_reason = f"Signal {signal_name} (code {signum})"
            log.warning(f"\n⚠️  Received signal: {exit_reason}")
            log.info(f"Gracefully shutting down due to {signal_name}...")
            sys.exit(0)
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGHUP, signal_handler)
        
        log.info("✓ Signal handlers registered")
        log.info("🚀 Starting main event loop...")
        
        # Run the main loop
        ls.run()
        
        exit_reason = "Normal completion"
        log.info(f"👋 LSwitch exited normally")
        return 0
        
    except KeyboardInterrupt:
        exit_reason = "Keyboard interrupt (Ctrl+C)"
        log.info(f"👋 LSwitch terminated by user (Ctrl+C)")
        return 0
        
    except BrokenPipeError:
        exit_reason = "Broken pipe error"
        log.error(f"❌ Broken pipe error - pipeline was closed")
        log.debug(traceback.format_exc())
        return 1
        
    except PermissionError as e:
        exit_reason = f"Permission denied: {e}"
        log.error(f"❌ Permission error: {e}")
        log.error("This may be due to missing permission to access input devices.")
        log.error("Try running with: sudo usermod -a -G input $USER")
        log.debug(traceback.format_exc())
        return 1
        
    except OSError as e:
        exit_reason = f"OS error: {e}"
        log.error(f"❌ OS error: {e}")
        log.debug(traceback.format_exc())
        return 1
        
    except Exception as e:
        exit_reason = f"Unhandled exception: {type(e).__name__}: {e}"
        log.error(f"❌ Unhandled error: {e}")
        log.error(f"Error type: {type(e).__name__}")
        log.debug(traceback.format_exc())
        return 1
        
    finally:
        # Log exit information
        if exit_reason:
            log.info(f"Exit reason: {exit_reason}")
        log.info(f"{'='*60}")
        log.info(f"LSwitch shutdown")
        log.info(f"{'='*60}")


if __name__ == '__main__':
    sys.exit(main())
