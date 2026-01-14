"""X11 adapter wrapping xclip/xdotool calls.

Provides small, test-friendly wrappers so we can mock X11 interactions in tests.
"""
import subprocess
import time


def get_primary_selection(timeout=0.3) -> str:
    try:
        return subprocess.run(['xclip', '-o', '-selection', 'primary'], capture_output=True, timeout=timeout, text=True).stdout
    except Exception:
        return ''


def get_clipboard(timeout=0.3) -> str:
    try:
        return subprocess.run(['xclip', '-o', '-selection', 'clipboard'], capture_output=True, timeout=timeout, text=True).stdout
    except Exception:
        return ''


def set_clipboard(text: str, timeout=0.5):
    try:
        subprocess.run(['xclip', '-selection', 'clipboard'], input=text, text=True, timeout=timeout)
    except Exception:
        pass


def paste_clipboard():
    try:
        subprocess.run(['xdotool', 'key', 'ctrl+v'], timeout=1.0, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def cut_selection():
    try:
        subprocess.run(['xdotool', 'key', 'ctrl+x'], timeout=0.5, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def delete_selection():
    try:
        subprocess.run(['xdotool', 'key', 'Delete'], timeout=0.2, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def shift_left():
    try:
        subprocess.run(['xdotool', 'key', 'shift+Left'], timeout=0.1, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def get_active_window_name():
    """Return active window name using xdotool, or empty string on failure."""
    try:
        res = subprocess.run(['xdotool', 'getwindowfocus', 'getwindowname'], capture_output=True, timeout=0.5, text=True)
        return res.stdout.strip()
    except Exception:
        return ''


def get_active_window_class():
    """Return active window WM_CLASS via xprop, or empty string on failure."""
    try:
        # get window id
        wid = subprocess.run(['xdotool', 'getwindowfocus'], capture_output=True, timeout=0.3, text=True).stdout.strip()
        if not wid:
            return ''
        # query WM_CLASS
        res = subprocess.run(['xprop', '-id', wid, 'WM_CLASS'], capture_output=True, timeout=0.5, text=True).stdout
        # WM_CLASS(STRING) = "code", "Code"
        if 'WM_CLASS' in res and '"' in res:
            parts = [p.strip().strip('"') for p in res.split('=')[-1].split(',')]
            # return first non-empty part
            for p in parts:
                if p:
                    return p
        return ''
    except Exception:
        return ''

def ctrl_shift_left():
    try:
        subprocess.run(['xdotool', 'key', 'ctrl+shift+Left'], timeout=0.1, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def send_key(key: str):
    try:
        subprocess.run(['xdotool', 'key', key], timeout=0.5, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def expand_selection_to_space(max_steps: int = 100, stable_timeout: float = 0.5) -> str:
    """Expand selection leftwards until a space is included or max_steps reached.

    Returns the current PRIMARY selection (possibly unchanged).
    """
    sel = get_primary_selection()
    try:
        prev = sel
        no_growth = 0
        for _ in range(max_steps):
            shift_left()
            time.sleep(0.01)
            new_sel = get_primary_selection()
            if new_sel == prev:
                no_growth += 1
            else:
                prev = new_sel
                no_growth = 0
            if ' ' in new_sel:
                sel = new_sel
                break
            if no_growth >= 3:
                # try word-wise once
                ctrl_shift_left()
                time.sleep(0.01)
                new_sel = get_primary_selection()
                if new_sel != prev:
                    sel = new_sel
                    break
                else:
                    # can't expand more
                    break
        # Stabilize
        stable_prev = None
        stable_count = 0
        start_t = time.time()
        while time.time() - start_t < stable_timeout and stable_count < 3:
            cur = get_primary_selection()
            if cur == stable_prev:
                stable_count += 1
            else:
                stable_prev = cur
                stable_count = 1
            time.sleep(0.02)
        if stable_prev:
            sel = stable_prev
    except Exception:
        pass
    return sel


def safe_replace_selection(converted: str, selected_text: str = None, debug: bool = False) -> str:
    """Safely replace current PRIMARY selection with converted text.

    Strategy:
    - Try Cut (ctrl+x) and verify clipboard contains original selection
    - If cut didn't work, send Delete and check PRIMARY emptied
    - Put converted text into clipboard and paste
    - Restore previous clipboard

    Returns the resulting PRIMARY selection after paste (may be empty on failure).
    """
    old_clip = get_clipboard()
    cut_succeeded = False
    try:
        cut_selection()
        time.sleep(0.03)
        test_clip = get_clipboard()
        if debug:
            print(f"🔍 after cut: clip_len={len(test_clip)} selected_len={len(selected_text or '')}")
        if selected_text and test_clip.strip() == selected_text.strip():
            cut_succeeded = True
            if debug:
                print("✓ Cut succeeded (ctrl+x)")
    except Exception:
        if debug:
            print("⚠️ Cut failed (ctrl+x)")
    if not cut_succeeded:
        try:
            delete_selection()
            time.sleep(0.03)
            after = get_primary_selection()
            if debug:
                print(f"🔍 after delete: primary_len={len(after)}")
            if after.strip() != (selected_text or '').strip():
                if debug:
                    print("✓ Delete seems to have removed selection")
        except Exception:
            if debug:
                print("⚠️ Delete failed")
    # Paste converted
    set_clipboard(converted.strip())
    time.sleep(0.02)
    paste_clipboard()
    time.sleep(0.05)
    # Restore clipboard
    if old_clip:
        set_clipboard(old_clip)
    # Return current primary
    return get_primary_selection()
