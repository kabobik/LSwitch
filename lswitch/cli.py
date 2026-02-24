"""Command-line argument parser for LSwitch."""

import argparse

from lswitch import __version__


def parse_args():
    parser = argparse.ArgumentParser(
        prog="lswitch",
        description="LSwitch — keyboard layout switcher with auto-conversion",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run without GUI (daemon mode)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug output",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    from lswitch.app import LSwitchApp
    app = LSwitchApp(headless=args.headless, debug=args.debug)
    app.run()
