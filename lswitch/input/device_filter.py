"""Device filtering: exclude virtual keyboards and mice."""

from __future__ import annotations

# Name fragments that identify devices to exclude
EXCLUDE_NAME_FRAGMENTS = [
    "virtual",
    "lswitch",
    "uinput",
]


def should_include_device(device_name: str) -> bool:
    """Return True if the device should be monitored."""
    lower = device_name.lower()
    return not any(fragment in lower for fragment in EXCLUDE_NAME_FRAGMENTS)
