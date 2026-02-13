# LSwitch Audit Report (2026-02-13)

## Scope
- GUI <-> daemon interaction
- Input handling: left click selection, backspace, word-navigation arrows
- Conversion behavior during these events

## Key Findings

### High
1. GUI control path uses undefined `system` and missing `subprocess` import, so several GUI->daemon operations fail.
   - Evidence: `subprocess` not imported in [lswitch_control.py](../lswitch_control.py#L8-L18) but used in [lswitch_control.py](../lswitch_control.py#L354-L362) and [lswitch_control.py](../lswitch_control.py#L417-L422).
   - Evidence: `system` referenced without definition in [lswitch_control.py](../lswitch_control.py#L485-L496), [lswitch_control.py](../lswitch_control.py#L532-L536), [lswitch_control.py](../lswitch_control.py#L760-L766), [lswitch_control.py](../lswitch_control.py#L794-L804).
   - Impact: GUI may show wrong service state, fail to publish layouts, and cannot signal the daemon.
   - Fix: add `import subprocess`, replace `system.*` calls with `get_system().*` (or consistently use `_system_mod.SYSTEM`) to keep DI hook intact.

### Medium
2. GUI config toggles may not propagate to the daemon on non-system installs because the daemon watches a different file.
   - Evidence: daemon defaults to `config_path = 'config.json'` if `/etc/lswitch/config.json` is absent [lswitch/core.py](../lswitch/core.py#L269-L274), but reload loop only watches `_config_path` [lswitch/core.py](../lswitch/core.py#L1553-L1562).
   - Impact: GUI writes `~/.config/lswitch/config.json`, daemon keeps running with old settings.
   - Fix: watch both system and user config paths, or default to the user config when `/etc` is missing, or always use `ConfigManager` in daemon.

3. Selection freshness detection uses string equality only, so reselecting the same text is treated as "not fresh" and the selection path is skipped.
   - Evidence: `has_selection()` only checks `current_selection != last_known_selection` [lswitch/core.py](../lswitch/core.py#L892-L903).
   - Impact: selecting the same word twice with the mouse can cause double Shift to convert the last buffered word (or do nothing) instead of the selection.
   - Fix: track selection owner/timestamp, or clear/update `last_known_selection` on mouse release, or treat any non-empty selection as fresh when last input was mouse action.

4. Backspace-hold flag persists across new typing and can force selection-mode conversions long after the hold ended.
   - Evidence: `backspace_hold_detected` set on repeats [lswitch/input.py](../lswitch/input.py#L266-L274), but normal key handling does not clear it [lswitch/input.py](../lswitch/input.py#L278-L305).
   - Impact: after a long backspace, a later double Shift prefers selection even when a word is buffered.
   - Fix: reset the flag on first non-backspace key release, or clear when the hold timestamp is older than a short threshold.

### Low
5. `subprocess.DEVNULL` is used without importing `subprocess` in input handling, so selection expansion via `xdotool` can no-op.
   - Evidence: missing import in [lswitch/input.py](../lswitch/input.py#L10-L14), use in [lswitch/input.py](../lswitch/input.py#L80-L83).
   - Impact: double Shift with empty buffer/backspace-hold may not select the word on systems without the adapter.
   - Fix: import `subprocess` or drop `stderr=subprocess.DEVNULL`.

6. Layouts runtime file is written non-atomically while daemon reads it; partial writes can be parsed as invalid JSON and ignored.
   - Evidence: direct write in [lswitch_control.py](../lswitch_control.py#L438-L448) and read loop in [lswitch/monitor.py](../lswitch/monitor.py#L77-L96).
   - Impact: occasional missed layout updates or transient stale layouts.
   - Fix: write to a temp file and `os.replace()` atomically.

## Sensitivity Tuning (Ngrams)
- Auto-convert uses an ngram score delta via `ngrams.should_convert()` with `threshold=ls.config.get('auto_switch_threshold', 10)` in [lswitch/conversion.py](../lswitch/conversion.py#L203-L234) and the decision logic in [lswitch/ngrams.py](../lswitch/ngrams.py#L145-L228).
- `auto_switch_threshold` is documented but not merged by config defaults, so it may stick to the default unless injected elsewhere; see [docs/INSTALL.md](../docs/INSTALL.md#L140-L153) and defaults in [lswitch/config.py](../lswitch/config.py#L16-L97).
- Learned-word auto-convert uses a separate `auto_convert_threshold` stored in user dict settings [lswitch/user_dictionary.py](../lswitch/user_dictionary.py#L67-L76) and enforced in [lswitch/user_dictionary.py](../lswitch/user_dictionary.py#L187-L219).

## Input Handling Focus: Left Click, Backspace, Word Arrows
- Left click selection: selection freshness logic in [lswitch/core.py](../lswitch/core.py#L892-L903) treats a same-text reselect as stale. This can misroute conversion to buffered word path instead of selection.
- Backspace hold: flag lingers beyond the backspace session [lswitch/input.py](../lswitch/input.py#L266-L305), causing the converter to prefer selection-mode even when new typing occurred.
- Word arrows: no direct bug found in the conversion path, but arrow navigation relies on selection freshness to decide conversion target; if selection is stale, conversion can target buffer instead of selection. Consider adding mouse/arrow activity timestamps for target selection.

## Recommended Tests
1. GUI toggles `auto_switch` on a system without `/etc/lswitch/config.json` and verify daemon picks up changes within 1-2 seconds.
2. Select the same word twice with the mouse and press double Shift; ensure the selection is converted both times.
3. Hold Backspace to trigger `backspace_hold_detected`, then type a new word and double Shift; verify retype-mode conversion (not selection mode).
4. Run GUI with missing adapter; double Shift should still attempt selection (no NameError, no silent no-op).
5. Publish layout changes rapidly; verify daemon consistently updates `self.layouts` without JSON parse errors.
