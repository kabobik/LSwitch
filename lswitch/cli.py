#!/usr/bin/env python3
"""
LSwitch CLI entry point
"""

from __future__ import annotations
import sys
import argparse
import signal
import os

from __version__ import __version__


def main() -> int:
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
        version='%(prog)s ' + __version__
    )
    
    args = parser.parse_args()
    
    # Import after args parsing to avoid import-time side effects
    from lswitch.core import LSwitch
    from lswitch.config import load_config
    
    # Load configuration
    try:
        config = load_config(args.config, args.debug)
    except Exception as e:
        print(f"❌ Error loading config: {e}", file=sys.stderr)
        return 1
    
    # Override debug flag if specified (ensure it's set)
    if args.debug:
        config['debug'] = True
    
    # Create and run LSwitch
    try:
        # Pass config_path to LSwitch so it can load config itself,
        # OR pass the loaded config if __init__ supports it
        # For now, pass args.config (path) so LSwitch reloads if needed
        ls = LSwitch(args.config)
        
        # Override debug after construction
        if args.debug:
            ls.config['debug'] = True
        
        # Handle signals gracefully
        def signal_handler(signum: int, frame) -> None:
            # Сохраняем пользовательский словарь перед выходом
            if ls and hasattr(ls, 'user_dict') and ls.user_dict:
                ls.user_dict.flush()
            print("\n👋 LSwitch закрыт")
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
