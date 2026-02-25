"""Command-line argument parser for LSwitch."""

import argparse
import logging

import lswitch.log  # registers TRACE level and logger.trace()
from lswitch import __version__


def _setup_logging(debug: bool, trace: bool = False) -> None:
    if trace:
        level = lswitch.log.TRACE
    elif debug:
        level = logging.DEBUG
    else:
        level = logging.INFO
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
        help="Enable debug output (state changes, auto-conv decisions)",
    )
    parser.add_argument(
        "--trace",
        action="store_true",
        help="Enable trace output (all raw events, ignored transitions; implies --debug)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    debug = args.debug or args.trace  # --trace implies --debug
    _setup_logging(debug=debug, trace=args.trace)
    from lswitch.app import LSwitchApp
    app = LSwitchApp(headless=args.headless, debug=debug)
    app.run()
