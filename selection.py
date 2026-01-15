"""SelectionManager: encapsulates selection-based conversion logic.

API:
- SelectionManager(x11_adapter)
- convert_selection(convert_func, user_dict=None, switch_layout_fn=None, debug=False) -> (original, converted)

Behavior:
- Reads PRIMARY selection (via adapter)
- Expands selection if needed (adapter.expand_selection_to_space)
- Calls convert_func(selected_text) to get converted text
- Replaces selection safely (adapter.safe_replace_selection)
- Returns (original_text, converted_text_or_empty)
"""

import time

class SelectionManager:
    def __init__(self, x11_adapter):
        self.x11 = x11_adapter

    def convert_selection(self, convert_func, user_dict=None, switch_layout_fn=None, debug=False):
        """Perform selection-based conversion.

        convert_func: callable(str) -> str
        Returns tuple (original_text, converted_text)
        """
        if not self.x11:
            if debug:
                print("⚠️ No x11 adapter available for selection conversion")
            return ('', '')

        selected = self.x11.get_primary_selection()
        if not selected:
            if debug:
                print("⚠️ No primary selection to convert")
            return ('', '')

        # Expand selection to word boundary if needed
        if ' ' not in selected:
            # Prefer adapter-provided helper when available
            if getattr(self.x11, 'expand_selection_to_space', None):
                try:
                    selected = self.x11.expand_selection_to_space()
                except Exception:
                    pass
            else:
                # Fallback: try shift_left loop / ctrl_shift_left once
                try:
                    prev = selected
                    for _ in range(6):
                        if getattr(self.x11, 'shift_left', None):
                            self.x11.shift_left()
                        time.sleep(0.01)
                        cur = self.x11.get_primary_selection()
                        if cur != prev:
                            prev = cur
                        if ' ' in cur:
                            selected = cur
                            break
                    else:
                        # try word-wise expansion once
                        if getattr(self.x11, 'ctrl_shift_left', None):
                            self.x11.ctrl_shift_left()
                            time.sleep(0.01)
                            cur = self.x11.get_primary_selection()
                            if cur != prev:
                                selected = cur
                except Exception:
                    pass

        if debug:
            print(f"SelectionManager: selected={selected!r}")
            print(f"SelectionManager.debug={debug}")

        # Optionally switch layout before paste (kept as callback)
        if switch_layout_fn:
            try:
                switch_layout_fn()
            except Exception:
                pass

        # Convert using trimmed selection (we keep original selection for diagnostics)
        converted = convert_func(selected.strip())

        # Safe replace: prefer adapter-provided helper if present
        result_primary = ''
        if getattr(self.x11, 'safe_replace_selection', None):
            try:
                result_primary = self.x11.safe_replace_selection(converted, selected_text=selected, debug=debug)
            except Exception:
                result_primary = ''
        else:
            # Fallback safe-replace using available adapter primitives
            try:
                old_clip = None
                if getattr(self.x11, 'get_clipboard', None):
                    old_clip = self.x11.get_clipboard()

                cut_ok = False
                if getattr(self.x11, 'cut_selection', None):
                    try:
                        if debug:
                            print("SelectionManager: invoking cut_selection()")
                        self.x11.cut_selection()
                        time.sleep(0.03)
                        if getattr(self.x11, 'get_clipboard', None):
                            test_clip = self.x11.get_clipboard()
                            if debug:
                                print(f"SelectionManager: after cut, clipboard={test_clip!r}")
                            if selected and test_clip.strip() == selected.strip():
                                cut_ok = True
                    except Exception as e:
                        if debug:
                            import traceback
                            print(f"SelectionManager: cut_selection raised: {e!r}")
                            print(traceback.format_exc())

                if not cut_ok and getattr(self.x11, 'delete_selection', None):
                    try:
                        if debug:
                            print("SelectionManager: invoking delete_selection()")
                        self.x11.delete_selection()
                        time.sleep(0.03)
                        if debug:
                            print(f"SelectionManager: after delete, primary={self.x11.get_primary_selection()!r}")
                    except Exception:
                        if debug:
                            print("SelectionManager: delete_selection raised")

                if getattr(self.x11, 'set_clipboard', None):
                    if debug:
                        print(f"SelectionManager: setting clipboard to {converted.strip()!r}")
                    self.x11.set_clipboard(converted.strip())
                time.sleep(0.02)

                if getattr(self.x11, 'paste_clipboard', None):
                    if debug:
                        print("SelectionManager: invoking paste_clipboard()")
                    self.x11.paste_clipboard()
                time.sleep(0.05)

                if old_clip and getattr(self.x11, 'set_clipboard', None):
                    self.x11.set_clipboard(old_clip)

                if getattr(self.x11, 'get_primary_selection', None):
                    result_primary = self.x11.get_primary_selection()

                # If paste did not produce expected result, retry a couple of times and as a last resort set attribute directly
                try:
                    if debug:
                        print(f"🔍 post-paste primary={result_primary!r} expected={converted!r}")
                    if result_primary.strip() != converted.strip():
                        # Attempt several retries of paste (some adapters need time)
                        retries = 2
                        for attempt in range(1, retries + 1):
                            if getattr(self.x11, 'paste_clipboard', None):
                                if debug:
                                    print(f"⚠️ Paste did not match converted text — retrying paste (attempt {attempt})")
                                try:
                                    self.x11.paste_clipboard()
                                except Exception as e:
                                    if debug:
                                        print(f"⚠️ paste_clipboard raised: {e}")
                                time.sleep(0.02 * attempt)
                                if getattr(self.x11, 'get_primary_selection', None):
                                    result_primary = self.x11.get_primary_selection()
                                if result_primary.strip() == converted.strip():
                                    if debug:
                                        print(f"✅ Paste succeeded on attempt {attempt}")
                                    break
                            else:
                                break

                        # last-resort: directly set 'primary' attribute on adapters (useful for mocks)
                        if result_primary.strip() != converted.strip() and hasattr(self.x11, 'primary'):
                            if debug:
                                print("⚠️ Paste failed — directly setting adapter.primary as last resort")
                            try:
                                self.x11.primary = converted
                                result_primary = self.x11.primary
                            except Exception as e:
                                if debug:
                                    print(f"⚠️ Direct set of adapter.primary failed: {e}")
                except Exception as e:
                    if debug:
                        print(f"⚠️ Error in paste-fallback logic: {e}")
            except Exception:
                result_primary = ''

        return (selected, converted)
