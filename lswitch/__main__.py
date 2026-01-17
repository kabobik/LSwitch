#!/usr/bin/env python3
"""
LSwitch main entry point for running as a module: python3 -m lswitch
"""

import sys
from lswitch.cli import main

if __name__ == '__main__':
    sys.exit(main())
