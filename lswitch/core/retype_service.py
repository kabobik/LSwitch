"""Shared typed-event retype primitive."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from lswitch.core.decision_trace import (
    DecisionTraceStep,
    StepState,
    TraceFact,
)

if TYPE_CHECKING:
    from lswitch.input.virtual_keyboard import VirtualKeyboard
    from lswitch.platform.xkb_adapter import IXKBAdapter, LayoutInfo

logger = logging.getLogger(__name__)

KEY_BACKSPACE = 14


class RetypeService:
    """Delete typed characters, switch layout, and replay physical events."""

    def __init__(
        self,
        virtual_kb: "VirtualKeyboard",
        xkb: "IXKBAdapter",
        *,
        debug: bool = False,
        layout_switch_controller=None,
    ):
        self.virtual_kb = virtual_kb
        self.xkb = xkb
        self.debug = debug
        self.layout_switch_controller = layout_switch_controller
        self.last_trace_steps: tuple[DecisionTraceStep, ...] = ()

    def retype_events(
        self,
        events: list,
        *,
        delete_count: int,
        target_layout: "LayoutInfo | None" = None,
        switch_to_next: bool = False,
        before_replay_delay: float = 0.05,
        backspace_n_times_keyword: bool = False,
    ) -> bool:
        steps: list[DecisionTraceStep] = []
        self.last_trace_steps = ()
        if delete_count <= 0:
            logger.debug("RetypeService: skip — delete_count=%d", delete_count)
            self.last_trace_steps = (
                self._step(
                    "execution.delete",
                    StepState.SKIPPED,
                    decisive=True,
                    delete_count=delete_count,
                ),
            )
            return False

        saved_events = list(events)
        operation = (
            self.layout_switch_controller.begin_operation()
            if self.layout_switch_controller is not None
            else None
        )
        if self.debug:
            logger.debug(
                "RetypeService: start — delete=%d, events=%d, codes=%s",
                delete_count,
                len(saved_events),
                [getattr(event, "code", "?") for event in saved_events],
            )

        logger.debug("RetypeService: sending %d backspaces", delete_count)
        try:
            if backspace_n_times_keyword:
                self.virtual_kb.tap_key(KEY_BACKSPACE, n_times=delete_count)
            else:
                self.virtual_kb.tap_key(KEY_BACKSPACE, delete_count)
            steps.append(
                self._step(
                    "execution.delete",
                    StepState.SUCCEEDED,
                    delete_count=delete_count,
                )
            )
        except Exception as exc:
            steps.append(
                self._step(
                    "execution.delete",
                    StepState.FAILED,
                    decisive=True,
                    delete_count=delete_count,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
            )
            self.last_trace_steps = tuple(steps)
            raise

        try:
            if target_layout is not None:
                new_layout = (
                    operation.switch_to(target_layout)
                    if operation is not None
                    else self.xkb.switch_layout(target=target_layout)
                )
            elif switch_to_next:
                new_layout = (
                    operation.switch_to()
                    if operation is not None
                    else self.xkb.switch_layout()
                )
            else:
                new_layout = None
            if new_layout is not None:
                logger.debug(
                    "RetypeService: switched layout → %s",
                    getattr(new_layout, "name", new_layout),
                )
            steps.append(
                self._step(
                    "execution.layout_switch",
                    StepState.SUCCEEDED,
                    target_layout=getattr(target_layout, "name", None),
                    actual_layout=getattr(new_layout, "name", None),
                    switch_to_next=switch_to_next,
                )
            )
        except Exception as exc:
            logger.error("RetypeService: switch_layout failed: %s", exc)
            if operation is not None:
                operation.finish(success=False)
            steps.append(
                self._step(
                    "execution.layout_switch",
                    StepState.FAILED,
                    decisive=True,
                    target_layout=getattr(target_layout, "name", None),
                    switch_to_next=switch_to_next,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
            )
            self.last_trace_steps = tuple(steps)
            return False

        time.sleep(before_replay_delay)

        if self.debug:
            logger.debug(
                "RetypeService: replaying %d events (codes=%s)",
                len(saved_events),
                [getattr(event, "code", "?") for event in saved_events],
            )
        try:
            self.virtual_kb.replay_events(saved_events)
            steps.append(
                self._step(
                    "execution.replay",
                    StepState.SUCCEEDED,
                    event_count=len(saved_events),
                )
            )
        except Exception as exc:
            logger.error("RetypeService: replay failed: %s", exc)
            if operation is not None:
                operation.finish(success=False)
            steps.append(
                self._step(
                    "execution.replay",
                    StepState.FAILED,
                    decisive=True,
                    event_count=len(saved_events),
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
            )
            self.last_trace_steps = tuple(steps)
            return False

        if operation is not None:
            operation.finish(success=True)
            steps.append(
                self._step(
                    "execution.layout_policy",
                    StepState.SUCCEEDED,
                    keep_target=operation.keep_target_after_conversion,
                )
            )

        logger.debug(
            "RetypeService: done — deleted=%d, replayed=%d",
            delete_count,
            len(saved_events),
        )
        steps.append(
            self._step(
                "execution.success",
                StepState.SUCCEEDED,
                decisive=True,
            )
        )
        self.last_trace_steps = tuple(steps)
        return True

    @staticmethod
    def _step(
        rule_id: str,
        state: StepState,
        *,
        decisive: bool = False,
        **facts,
    ) -> DecisionTraceStep:
        return DecisionTraceStep(
            rule_id=rule_id,
            state=state,
            decisive=decisive,
            facts=tuple(
                TraceFact(
                    key=key,
                    value=(
                        value
                        if isinstance(
                            value,
                            (str, int, float, bool, type(None)),
                        )
                        else str(value)
                    ),
                )
                for key, value in facts.items()
            ),
        )
