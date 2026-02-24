#!/usr/bin/env python3
"""Helper to find processes holding /dev/uinput (virtual keyboards) and optionally kill them.

Usage:
  python3 scripts/release_virtual_kb.py --kill

Requires either lsof or fuser to be installed. May need sudo to inspect some PIDs or to kill them.
"""

import subprocess
import shutil
import sys
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--kill', action='store_true', help='Kill discovered PIDs (requires permissions)')
args = parser.parse_args()

def run(cmd):
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return out.stdout.strip()
    except Exception as e:
        return ''

def find_with_lsof():
    if not shutil.which('lsof'):
        return []
    out = run(['lsof', '/dev/uinput'])
    pids = set()
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2:
            try:
                pids.add(int(parts[1]))
            except Exception:
                pass
    return sorted(pids)

def find_with_fuser():
    if not shutil.which('fuser'):
        return []
    out = run(['fuser', '/dev/uinput'])
    pids = []
    for token in out.split():
        if token.isdigit():
            pids.append(int(token))
    return pids

pids = find_with_lsof() or find_with_fuser()
if not pids:
    print('No processes found holding /dev/uinput (no virtual keyboard processes detected)')
    sys.exit(0)

print('Found PIDs holding /dev/uinput:')
for pid in pids:
    print('  ', pid)

if args.kill:
    print('Killing PIDs...')
    for pid in pids:
        try:
            subprocess.run(['kill', str(pid)])
            print('  killed', pid)
        except Exception as e:
            print('  failed to kill', pid, e)
else:
    print('\nRun with --kill to attempt to terminate them (may require sudo).')
