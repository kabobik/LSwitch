"""Command-line argument parser for LSwitch."""

import argparse
import logging

from lswitch import __version__


def _setup_logging(debug: bool) -> None:
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


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
    _setup_logging(args.debug)
    from lswitch.app import LSwitchApp
    app = LSwitchApp(headless=args.headless, debug=args.debug)
    app.run()
