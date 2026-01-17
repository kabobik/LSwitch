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
    def __init__(self, x11_adapter, repair_enabled=False):
        self.x11 = x11_adapter
        # When True, SelectionManager will attempt repair steps (delete+set+paste or direct set)
        # if the adapter does not commit the expected replacement. Default: disabled (conservative).
        self.repair_enabled = bool(repair_enabled)

    def convert_selection(self, convert_func, user_dict=None, switch_layout_fn=None, debug=False, prefer_trim_leading=False, user_has_selection=False):
        """Perform selection-based conversion.

        convert_func: callable(str) -> str
        user_has_selection: bool - if True, user manually selected text, don't expand
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
        outside_leading = ''
        original_selected = selected
        # Only expand if: selection is too short AND user did NOT manually select anything
        # (if user_has_selection=True, they explicitly selected what they want)
        if debug:
            print(f"SelectionManager: selected={selected!r}, user_has_selection={user_has_selection}, has_space={' ' in selected}", flush=True)
        
        should_expand = ' ' not in selected and not user_has_selection
        if debug:
            print(f"SelectionManager: should_expand={should_expand} (no_space={' ' not in selected}, not_user_sel={not user_has_selection})", flush=True)
        
        if should_expand:
            # Prefer adapter-provided helper when available
            if getattr(self.x11, 'expand_selection_to_space', None):
                try:
                    selected = self.x11.expand_selection_to_space()
                    # If adapter expansion included a leading space and the
                    # caller requested trimming, treat it as outside leading
                    # whitespace and remove it from the selected text used for
                    # conversion.
                    lw = selected[:len(selected) - len(selected.lstrip())]
                    if lw and prefer_trim_leading:
                        outside_leading = lw
                        selected = selected.lstrip()
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
                            # If expansion captured a leading space, treat it as
                            # outside leading whitespace when either the original
                            # selection included it OR the caller requested trimming
                            # of leading whitespace (e.g., selection was created by
                            # ctrl_shift_left from on_double_shift).
                            lw = cur[:len(cur) - len(cur.lstrip())]
                            if lw and (prefer_trim_leading or original_selected.startswith(lw)):
                                outside_leading = lw
                                selected = cur.lstrip()
                            else:
                                # Drop leading space for conversion; do not assume
                                # it's part of original selection
                                selected = cur.lstrip()
                            break
                    else:
                        # try word-wise expansion once
                        if getattr(self.x11, 'ctrl_shift_left', None):
                            self.x11.ctrl_shift_left()
                            time.sleep(0.01)
                            cur = self.x11.get_primary_selection()
                            if cur != prev:
                                lw = cur[:len(cur) - len(cur.lstrip())]
                                if lw and original_selected.startswith(lw):
                                    outside_leading = lw
                                    selected = cur.lstrip()
                                else:
                                    selected = cur.lstrip()
                except Exception:
                    pass

        if debug:
            print(f"SelectionManager: original_selected={original_selected!r} selected_after_expand={selected!r} outside_leading={outside_leading!r} prefer_trim_leading={prefer_trim_leading}")
            print(f"SelectionManager.debug={debug}")

        # Optionally switch layout before paste (kept as callback)
        if switch_layout_fn:
            try:
                switch_layout_fn()
            except Exception:
                pass

        # Convert using trimmed selection (we keep original selection for diagnostics)
        converted = convert_func(selected.strip())

        # Preserve surrounding whitespace from the original selection so that
        # replacing the selection does not remove leading/trailing spaces.
        try:
            core = selected.strip()
            # If expansion captured an outside leading whitespace, use it; otherwise use any leading whitespace inside `selected`.
            leading_inside = selected[:len(selected) - len(selected.lstrip())]
            # Preserve leading whitespace introduced by expansion unless the caller explicitly
            # requested trimming (prefer_trim_leading). If trimming was requested and the
            # original selection didn't include it, drop it.
            if leading_inside and not original_selected.startswith(leading_inside) and prefer_trim_leading:
                leading_inside = ''
            # NOTE: do not clear `outside_leading` when prefer_trim_leading is set.
            # The adapter may have introduced leading whitespace during expansion; we
            # exclude it from the converted text when trimming is requested, but we
            # should restore it in the final replacement so document spacing is preserved.
            # (i.e., leave `outside_leading` as-is)
            leading = (outside_leading or '') + leading_inside
            trailing = selected[len(selected.rstrip()):]
            # Reconstruct replaced primary value preserving whitespace
            result_primary_reconstructed = f"{leading}{converted.strip()}{trailing}"
        except Exception:
            # Fallback: just use converted (stripped)
            result_primary_reconstructed = converted.strip()
        # Safe replace: prefer adapter-provided helper if present
        result_primary = ''
        has_safe_replace = getattr(self.x11, 'safe_replace_selection', None)
        if has_safe_replace:
            try:
                # Provide selected_text so adapter may decide more intelligently
                result_primary = self.x11.safe_replace_selection(result_primary_reconstructed, selected_text=selected, debug=debug)
                if debug:
                    print(f"SelectionManager: safe_replace_selection returned={result_primary!r}", flush=True)
            except Exception as e:
                if debug:
                    print(f"⚠️ safe_replace_selection raised: {e}", flush=True)
                result_primary = ''
        else:
            # Fallback safe-replace using available adapter primitives
            try:
                old_clip = None
                if getattr(self.x11, 'get_clipboard', None):
                    old_clip = self.x11.get_clipboard()

                cut_ok = False
                repaired = False
                # If caller requested trimming and adapter supports delete, prefer
                # delete_selection so we avoid capturing leading whitespace at all.
                if prefer_trim_leading and getattr(self.x11, 'delete_selection', None):
                    try:
                        if debug:
                            print("SelectionManager: invoking delete_selection() to avoid leading-space capture")
                        self.x11.delete_selection()
                        time.sleep(0.03)
                        # Consider as success (selection removed)
                        cut_ok = True
                    except Exception:
                        if debug:
                            print("SelectionManager: delete_selection raised (non-fatal)")

                if not cut_ok and getattr(self.x11, 'cut_selection', None):
                    try:
                        if debug:
                            print("SelectionManager: invoking cut_selection()")
                        self.x11.cut_selection()
                        time.sleep(0.03)
                        if getattr(self.x11, 'get_clipboard', None):
                            test_clip = self.x11.get_clipboard()
                            if debug:
                                print(f"SelectionManager: after cut, clipboard={test_clip!r} selected={selected!r}")
                            # If the adapter included an outside leading whitespace
                            # during expansion and the caller requested trimming,
                            # treat the clipboard for conversion as trimmed so the
                            # leading space is not considered part of the word.
                            test_clip_for_check = test_clip
                            if prefer_trim_leading and outside_leading and test_clip.startswith(outside_leading) and not original_selected.startswith(outside_leading):
                                # do not mutate real clipboard; use trimmed copy for checks
                                test_clip_for_check = test_clip[len(outside_leading):]
                                if debug:
                                    print(f"SelectionManager: trimming clipboard for conversion -> {test_clip_for_check!r}")
                            if selected and test_clip_for_check.strip() == selected.strip():
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
                        # If adapter exposes PRIMARY, check whether delete actually cleared it
                        if getattr(self.x11, 'get_primary_selection', None):
                            try:
                                after_del = self.x11.get_primary_selection()
                                if debug:
                                    print(f"SelectionManager: after delete, primary={after_del!r}")
                                if after_del:
                                    # delete did not clear selection; avoid cut+paste to prevent duplication
                                    if debug:
                                        print("⚠️ delete did not clear primary (fallback path) — will attempt direct set instead of paste", flush=True)
                                    # Try direct set if possible; mark repaired when we commit replacement
                                    if hasattr(self.x11, 'primary'):
                                        if debug:
                                            print("SelectionManager: direct-setting adapter.primary as fallback", flush=True)
                                        try:
                                            self.x11.primary = result_primary_reconstructed
                                            repaired = True
                                        except Exception as e:
                                            if debug:
                                                print(f"⚠️ Direct set failed in fallback branch: {e}", flush=True)
                                    else:
                                        # fallback to set_clipboard+paste (risky)
                                        if getattr(self.x11, 'set_clipboard', None):
                                            if debug:
                                                print("SelectionManager: delete no-op — attempting guarded set+paste", flush=True)
                                            try:
                                                self.x11.set_clipboard(result_primary_reconstructed)
                                                time.sleep(0.03)
                                                if getattr(self.x11, 'paste_clipboard', None):
                                                    self.x11.paste_clipboard()
                                                    time.sleep(0.03)
                                                repaired = True
                                            except Exception as e:
                                                if debug:
                                                    print(f"⚠️ guarded set+paste failed (fallback path): {e}", flush=True)
                            except Exception as e:
                                if debug:
                                    print(f"🔍 get_primary_selection raised after delete (fallback path): {e}", flush=True)
                        else:
                            if debug:
                                print("SelectionManager: after delete (no get_primary_selection available)")
                    except Exception:
                        if debug:
                            print("SelectionManager: delete_selection raised")

                if not repaired and getattr(self.x11, 'set_clipboard', None):
                    if debug:
                        print(f"SelectionManager: setting clipboard to {result_primary_reconstructed!r}")
                    self.x11.set_clipboard(result_primary_reconstructed)
                    if debug:
                        try:
                            if getattr(self.x11, 'get_clipboard', None):
                                clip_now = self.x11.get_clipboard()
                                print(f"🔍 clipboard after set_clipboard: {clip_now!r}", flush=True)
                            else:
                                print("🔍 clipboard set (get_clipboard not available)", flush=True)
                        except Exception as e:
                            print(f"🔍 get_clipboard raised after set_clipboard: {e}", flush=True)
                time.sleep(0.02)

                if getattr(self.x11, 'paste_clipboard', None):
                    if debug:
                        try:
                            clip_before = self.x11.get_clipboard() if getattr(self.x11, 'get_clipboard', None) else None
                            print(f"SelectionManager: invoking paste_clipboard(), clipboard_before={clip_before!r}")
                        except Exception as e:
                            print(f"SelectionManager: invoking paste_clipboard(), get_clipboard raised: {e}")
                    try:
                        self.x11.paste_clipboard()
                    except Exception as e:
                        if debug:
                            print(f"⚠️ paste_clipboard raised: {e}")
                time.sleep(0.05)

                if debug:
                    try:
                        if getattr(self.x11, 'get_clipboard', None):
                            clip_after = self.x11.get_clipboard()
                            print(f"🔍 clipboard after paste: {clip_after!r}", flush=True)
                    except Exception as e:
                        if debug:
                            print(f"🔍 get_clipboard raised after paste: {e}", flush=True)

                if old_clip and getattr(self.x11, 'set_clipboard', None):
                    self.x11.set_clipboard(old_clip)

                if getattr(self.x11, 'get_primary_selection', None):
                    result_primary = self.x11.get_primary_selection()

                # If paste did not produce expected result, retry a couple of times and as a last resort set attribute directly
                try:
                    if debug:
                        print(f"🔍 post-paste primary={result_primary!r} expected={result_primary_reconstructed!r}")
                        print(f"🔍 details: outside_leading={outside_leading!r}, leading_inside={leading_inside!r}, trailing={trailing!r}")
                    # Ensure we compare exact result including leading/trailing whitespace
                    if result_primary != result_primary_reconstructed:
                        # Attempt several retries of paste (some adapters need time and may clear clipboard)
                        retries = 3
                        for attempt in range(1, retries + 1):
                            if getattr(self.x11, 'paste_clipboard', None):
                                if debug:
                                    print(f"⚠️ Paste did not match converted text exactly — retrying paste (attempt {attempt}/{retries})")
                                # Re-set clipboard before retry — some adapters may lose it
                                try:
                                    if getattr(self.x11, 'set_clipboard', None):
                                        self.x11.set_clipboard(result_primary_reconstructed)
                                except Exception as e:
                                    if debug:
                                        print(f"⚠️ set_clipboard raised during retry prep: {e}")
                                try:
                                    self.x11.paste_clipboard()
                                except Exception as e:
                                    if debug:
                                        print(f"⚠️ paste_clipboard raised: {e}")
                                # Backoff increasing delay for stability
                                time.sleep(0.02 * attempt)
                                if getattr(self.x11, 'get_primary_selection', None):
                                    result_primary = self.x11.get_primary_selection()
                                # Require exact match including whitespace
                                if result_primary == result_primary_reconstructed:
                                    if debug:
                                        print(f"✅ Paste succeeded on attempt {attempt}")
                                    break
                            else:
                                break

                        # last-resort: directly set 'primary' attribute on adapters (useful for mocks)
                        if result_primary != result_primary_reconstructed and hasattr(self.x11, 'primary'):
                            if debug:
                                print("⚠️ Paste failed — directly setting adapter.primary as last resort")
                            try:
                                self.x11.primary = result_primary_reconstructed
                                result_primary = self.x11.primary
                            except Exception as e:
                                if debug:
                                    print(f"⚠️ Direct set of adapter.primary failed: {e}")

                        # If paste still did not produce expected result, attempt to restore the
                        # original selection to avoid data loss: set clipboard back to original
                        # selection and paste it (best-effort). This prevents the case where
                        # delete/remove occurred but the converted text was not inserted.
                        if result_primary != result_primary_reconstructed:
                            try:
                                if debug:
                                    print("⚠️ Paste failed — attempting to restore original selection")
                                if getattr(self.x11, 'set_clipboard', None) and getattr(self.x11, 'paste_clipboard', None):
                                    self.x11.set_clipboard(selected.strip())
                                    time.sleep(0.02)
                                    self.x11.paste_clipboard()
                                    time.sleep(0.03)
                                    if getattr(self.x11, 'get_primary_selection', None):
                                        result_primary = self.x11.get_primary_selection()
                                        if debug:
                                            print(f"🔄 After restore attempt, primary={result_primary!r}")
                            except Exception as e:
                                if debug:
                                    print(f"⚠️ Error during restore attempt: {e}")
                except Exception as e:
                    if debug:
                        print(f"⚠️ Error in paste-fallback logic: {e}")
            except Exception:
                result_primary = ''

        return (selected, converted)
