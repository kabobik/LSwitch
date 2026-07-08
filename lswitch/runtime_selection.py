"""Runtime selection tracking helpers."""

from __future__ import annotations


def read_mouse_release_selection(*, selection, platform):
    """Read selection after mouse release when platform tracking allows it."""
    if selection is None:
        return None
    if not getattr(
        platform,
        "selection_mouse_release_tracking_enabled",
        True,
    ):
        return None

    from lswitch.platform.selection_adapter import get_passive_selection_reader

    reader = get_passive_selection_reader(selection)
    if reader is not None:
        return reader()
    return selection.get_selection()


def selection_baseline_tracking_enabled(*, platform) -> bool:
    """Return whether passive selection baseline reads are safe/useful."""
    if platform is None:
        return True

    polling = getattr(platform, "selection_polling_enabled", None)
    mouse_release = getattr(
        platform,
        "selection_mouse_release_tracking_enabled",
        None,
    )
    if polling is None and mouse_release is None:
        return True
    return bool(polling or mouse_release)


def update_selection_baseline(*, selection_tracker, selection, platform) -> None:
    """Update passive selection baseline when platform tracking allows it."""
    if selection is None or not selection_baseline_tracking_enabled(platform=platform):
        return

    try:
        from lswitch.platform.selection_adapter import get_passive_selection_reader

        reader = get_passive_selection_reader(selection)
        info = reader() if reader is not None else selection.get_selection()
        selection_tracker.update_baseline(
            info.text or "",
            info.owner_id,
        )
    except Exception:
        pass


def handle_poller_selection_changed(
    *,
    selection_tracker,
    text: str,
    owner_id: int,
    log,
) -> None:
    """Mark selection as fresh after the platform poller reports a change."""
    selection_tracker.on_poller_changed()
    log.debug(
        "Poller: selection changed, fresh=True — text=%r owner=0x%x",
        text[:50] if text else "",
        owner_id,
    )


def set_selection_valid_with_logging(*, selection_tracker, value: bool, log) -> None:
    """Set selection freshness and preserve legacy debug/trace logging."""
    old_value = selection_tracker.valid
    if value != old_value:
        log.debug(
            "fresh=%s → %s",
            old_value,
            value,
        )
    selection_tracker.set_valid(value)

    if log.isEnabledFor(5):  # TRACE = 5
        import traceback as _tb

        caller = _tb.extract_stack(limit=3)[-2]
        log.trace(  # type: ignore[attr-defined]
            "fresh=%s (set by %s:%d)",
            selection_tracker.valid,
            caller.name,
            caller.lineno,
        )


def update_passive_selection_baseline_on_click(
    *,
    selection_tracker,
    selection,
    platform,
    log,
) -> None:
    """Prime baseline on platforms with safe passive selection reads."""
    if platform is None:
        return
    if not getattr(
        platform,
        "selection_mouse_release_tracking_enabled",
        True,
    ):
        return

    from lswitch.platform.selection_adapter import get_passive_selection_reader

    reader = get_passive_selection_reader(selection)
    if reader is None:
        return
    try:
        info = reader()
        result = selection_tracker.on_click_passive_selection(
            info.text or "",
            info.owner_id,
        )
        if result == "initial":
            log.trace(  # type: ignore[attr-defined]
                "MouseClick: initial passive selection baseline — text=%r",
                info.text[:50] if info.text else "",
            )
            return
        if result == "fresh":
            log.debug(
                "MouseClick: fresh passive selection — text=%r owner=0x%x",
                info.text[:50] if info.text else "",
                info.owner_id,
            )
            return
        log.trace(  # type: ignore[attr-defined]
            "MouseClick: passive selection baseline — text=%r",
            info.text[:50] if info.text else "",
        )
    except Exception:
        pass
