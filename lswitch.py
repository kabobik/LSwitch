#!/usr/bin/env python3
"""Lightweight shim for package-based LSwitch."""
from lswitch import main as _package_main


def main():
    return _package_main()


if __name__ == '__main__':
    main()
