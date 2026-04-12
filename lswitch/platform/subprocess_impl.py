"""SubprocessSystemAdapter — real implementation of ISystemAdapter."""

from __future__ import annotations

import subprocess

from lswitch.platform.system_adapter import CommandResult, ISystemAdapter


class SubprocessSystemAdapter(ISystemAdapter):
    """Executes real subprocess calls."""

    def __init__(self, debug: bool = False) -> None:
        self.debug = debug

    def run_command(self, args: list[str], timeout: float = 1.0) -> CommandResult:
        try:
            r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
            return CommandResult(stdout=r.stdout, stderr=r.stderr, returncode=r.returncode)
        except subprocess.TimeoutExpired:
            return CommandResult(stdout="", stderr="timeout", returncode=-1)
        except Exception as e:
            return CommandResult(stdout="", stderr=str(e), returncode=-1)

    def xdotool_key(self, sequence: str, timeout: float = 0.3) -> None:
        self.run_command(["xdotool", "key", sequence], timeout=timeout)

    def get_clipboard(self, selection: str = "primary") -> str:
        result = self.run_command(
            ["xclip", "-o", "-selection", selection], timeout=0.3
        )
        return result.stdout

    def set_clipboard(self, text: str, selection: str = "clipboard") -> None:
        try:
            subprocess.run(
                ["xclip", "-i", "-selection", selection],
                input=text, text=True, timeout=1.0,
            )
        except Exception:
            pass
