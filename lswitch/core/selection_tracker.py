"""Selection freshness state tracking."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SelectionFreshnessTracker:
    """Owns the state used to decide whether selection conversion is fresh."""

    valid: bool = False
    generation: int = 0
    repeat_valid: bool = False
    repeat_generation: int = 0
    prev_text: str = ""
    prev_owner_id: int = 0
    baseline_initialized: bool = False

    def set_valid(self, value: bool) -> None:
        if value != self.valid and value:
            self.generation += 1
        self.valid = value

    def clear_repeat(self) -> None:
        self.repeat_valid = False
        self.repeat_generation = 0

    def reset_fresh_and_repeat(self) -> None:
        self.set_valid(False)
        self.clear_repeat()

    def effective_valid(self) -> bool:
        return self.valid or (
            self.repeat_valid and self.repeat_generation == self.generation
        )

    def mark_repeat_for_current_generation(self) -> None:
        self.repeat_valid = True
        self.repeat_generation = self.generation

    def update_baseline(self, text: str, owner_id: int) -> None:
        self.prev_text = text or ""
        self.prev_owner_id = owner_id
        self.baseline_initialized = True

    def on_poller_changed(self) -> None:
        self.set_valid(True)

    def on_release_selection(self, text: str, owner_id: int) -> str:
        old_text = self.prev_text
        old_owner = self.prev_owner_id
        had_baseline = self.baseline_initialized

        self.update_baseline(text or "", owner_id)

        if not text:
            self.reset_fresh_and_repeat()
            return "empty"

        if not had_baseline:
            return "initial"

        if text != old_text or (owner_id != old_owner and owner_id != 0):
            self.set_valid(True)
            return "fresh"

        return "unchanged"

    def on_click_passive_selection(self, text: str, owner_id: int) -> str:
        old_text = self.prev_text
        old_owner = self.prev_owner_id
        had_baseline = self.baseline_initialized

        self.update_baseline(text or "", owner_id)

        if not had_baseline:
            return "initial"

        if text and (text != old_text or (owner_id != old_owner and owner_id != 0)):
            self.set_valid(True)
            return "fresh"

        return "unchanged"
