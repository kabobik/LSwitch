"""Custom logging levels for LSwitch.

Levels (ascending):
    TRACE =  5  — every raw event, every ignored state transition
    DEBUG = 10  — state changes, auto-conv decisions, skips
    INFO  = 20  — conversions performed, startup/shutdown (default)

Usage:
    import lswitch.log  # must be imported once before any logger is used
    logger = logging.getLogger(__name__)
    logger.trace("very noisy message")
"""

import logging

TRACE: int = 5
logging.addLevelName(TRACE, "TRACE")


def _trace(self: logging.Logger, message: object, *args: object, **kwargs: object) -> None:
    if self.isEnabledFor(TRACE):
        self._log(TRACE, message, args, **kwargs)  # type: ignore[attr-defined]


# Patch Logger class once at import time
logging.Logger.trace = _trace  # type: ignore[attr-defined]
