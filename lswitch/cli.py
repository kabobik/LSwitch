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
        "--replace",
        action="store_true",
        help="Stop existing instance before starting (safe restart)",
    )
    parser.add_argument(
        "--diagnose-wayland",
        action="store_true",
        help="Run a read-only Wayland/KDE backend diagnostic and exit",
    )
    parser.add_argument(
        "--diagnose-wayland-switch-test",
        action="store_true",
        help="With --diagnose-wayland, briefly switch layout and restore it",
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
    if args.diagnose_wayland or args.diagnose_wayland_switch_test:
        from lswitch.platform.wayland_diagnostics import run_wayland_diagnostics

        report = run_wayland_diagnostics(
            switch_test=args.diagnose_wayland_switch_test,
        )
        print(report.to_text())
        raise SystemExit(0 if report.ok else 1)

    from lswitch.app import LSwitchApp
    app = LSwitchApp(headless=args.headless, debug=debug, replace=args.replace)
    app.run()
