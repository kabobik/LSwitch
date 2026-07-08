"""Tests for auto-conversion session state."""

from lswitch.core.auto_conversion_session import AutoConversionSessionState


def test_auto_conversion_session_defaults_are_empty():
    session = AutoConversionSessionState()

    assert session.last_marker is None
    assert session.sticky_events == []
    assert session.pending_space is False


def test_auto_conversion_session_clears_marker_and_sticky_events():
    session = AutoConversionSessionState(
        last_marker=object(),
        sticky_events=[object()],
        pending_space=True,
    )

    session.clear_marker()
    session.clear_sticky_events()

    assert session.last_marker is None
    assert session.sticky_events == []
    assert session.pending_space is True


def test_auto_conversion_session_normalizes_pending_space():
    session = AutoConversionSessionState()

    session.set_pending_space(1)

    assert session.pending_space is True


def test_auto_conversion_session_applies_space_state():
    marker = object()
    state = type(
        "State",
        (),
        {
            "last_auto_marker": marker,
            "pending_auto_space": 1,
        },
    )()
    session = AutoConversionSessionState()

    session.apply_space_state(state)

    assert session.last_marker is marker
    assert session.pending_space is True
