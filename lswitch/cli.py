#!/usr/bin/env python3
"""
LSwitch CLI entry point
"""

import sys
import argparse
import signal
from lswitch.core import LSwitch
from lswitch.config import load_config


def main():
    """Main entry point for LSwitch"""
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
        '--version',
        action='version',
        version='%(prog)s 1.0'
    )
    
    args = parser.parse_args()
    
    # Load configuration
    try:
        if args.config:
            config = load_config(args.config)
        else:
            # Use default (None means load from standard paths)
            config = load_config(None)
    except Exception as e:
        print(f"❌ Error loading config: {e}", file=sys.stderr)
        return 1
    
    # Override debug flag if specified
    if args.debug:
        config['debug'] = True
    
    # Create and run LSwitch
    try:
        ls = LSwitch(config)
        
        # Handle signals gracefully
        def signal_handler(signum, frame):
            print("\n👋 LSwitch закрыт")
            if hasattr(ls, 'stop'):
                ls.stop()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Run the main loop
        ls.run()
        
    except KeyboardInterrupt:
        print("\n👋 LSwitch закрыт")
        return 0
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        if args.debug:
            import traceback
            traceback.print_exc()
        return 1
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
