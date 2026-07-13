"""ConversionEngine — chooses conversion mode and executes it."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from lswitch.core.decision_trace import (
    DecisionTraceStep,
    StepState,
    TraceFact,
)

if TYPE_CHECKING:
    from lswitch.core.states import StateContext
    from lswitch.platform.xkb_adapter import IXKBAdapter
    from lswitch.platform.selection_adapter import ISelectionAdapter
    from lswitch.platform.system_adapter import ISystemAdapter
    from lswitch.input.virtual_keyboard import VirtualKeyboard
    from lswitch.intelligence.dictionary_service import DictionaryService
    from lswitch.intelligence.user_dictionary import UserDictionary

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ConversionModeDecision:
    """Ordered explanation for manual conversion mode selection."""

    mode: str
    reason_id: str
    steps: tuple[DecisionTraceStep, ...]


class ConversionEngine:
    """Orchestrates text conversion: retype or selection mode."""

    def __init__(
        self,
        xkb: "IXKBAdapter",
        selection: "ISelectionAdapter",
        virtual_kb: "VirtualKeyboard",
        dictionary: "DictionaryService",
        system: "ISystemAdapter",
        user_dict: "UserDictionary | None" = None,
        debug: bool = False,
        timing: dict | None = None,
        layout_switch_controller=None,
    ):
        self.xkb = xkb
        self.selection = selection
        self.virtual_kb = virtual_kb
        self.dictionary = dictionary
        self.system = system
        self.user_dict = user_dict
        self.debug = debug
        self.timing = timing or {}
        self.layout_switch_controller = layout_switch_controller
        self.last_conversion: dict | None = None
        self.last_mode_decision: ConversionModeDecision | None = None
        self.last_execution_steps: tuple[DecisionTraceStep, ...] = ()

    def choose_mode_decision(
        self,
        context: "StateContext",
        selection_valid: bool = False,
    ) -> ConversionModeDecision:
        """Return the selected mode together with reached priority rules."""
        steps: list[DecisionTraceStep] = []
        if context.backspace_hold_active:
            logger.debug(
                "choose_mode: backspace_hold_active=True → selection"
            )
            steps.append(
                self._mode_step(
                    "manual.mode.backspace_selection",
                    StepState.MATCHED,
                    decisive=True,
                    backspace_hold_active=True,
                )
            )
            return ConversionModeDecision(
                "selection",
                "manual.mode.backspace_selection",
                tuple(steps),
            )
        steps.append(
            self._mode_step(
                "manual.mode.backspace_selection",
                StepState.NOT_MATCHED,
                backspace_hold_active=False,
            )
        )
        if context.chars_in_buffer > 0:
            logger.debug(
                "choose_mode: chars_in_buffer=%d > 0 → retype",
                context.chars_in_buffer,
            )
            steps.append(
                self._mode_step(
                    "manual.mode.buffer_retype",
                    StepState.MATCHED,
                    decisive=True,
                    chars_in_buffer=context.chars_in_buffer,
                )
            )
            return ConversionModeDecision(
                "retype",
                "manual.mode.buffer_retype",
                tuple(steps),
            )
        steps.append(
            self._mode_step(
                "manual.mode.buffer_retype",
                StepState.NOT_MATCHED,
                chars_in_buffer=context.chars_in_buffer,
            )
        )
        if selection_valid:
            logger.debug(
                "choose_mode: selection_valid=True, chars=0 → selection"
            )
            steps.append(
                self._mode_step(
                    "manual.mode.fresh_selection",
                    StepState.MATCHED,
                    decisive=True,
                    selection_valid=True,
                )
            )
            return ConversionModeDecision(
                "selection",
                "manual.mode.fresh_selection",
                tuple(steps),
            )
        steps.append(
            self._mode_step(
                "manual.mode.fresh_selection",
                StepState.NOT_MATCHED,
                selection_valid=False,
            )
        )
        logger.debug(
            "choose_mode: fallback → selection_expand (chars=0, sel_valid=False, bs_hold=False)"
        )
        steps.append(
            self._mode_step(
                "manual.mode.expand_fallback",
                StepState.MATCHED,
                decisive=True,
            )
        )
        return ConversionModeDecision(
            "selection_expand",
            "manual.mode.expand_fallback",
            tuple(steps),
        )

    def choose_mode(self, context: "StateContext", selection_valid: bool = False) -> str:
        """Compatibility wrapper returning only the selected mode."""
        return self.choose_mode_decision(
            context,
            selection_valid=selection_valid,
        ).mode

    def convert(self, context: "StateContext", selection_valid: bool = False) -> bool:
        """Perform conversion. Returns True on success."""
        from lswitch.core.modes import RetypeMode, SelectionMode

        mode_decision = self.choose_mode_decision(
            context,
            selection_valid=selection_valid,
        )
        self.last_mode_decision = mode_decision
        mode = mode_decision.mode
        logger.debug("Converting in mode: %s", mode)
        self.last_conversion = None
        self.last_execution_steps = ()
        if mode == "retype":
            retype = RetypeMode(
                self.virtual_kb,
                self.xkb,
                self.system,
                self.debug,
                timing=self.timing,
                layout_switch_controller=self.layout_switch_controller,
            )
            success = retype.execute(context)
            self.last_execution_steps = tuple(
                getattr(retype, "last_trace_steps", ()) or ()
            )
            if not self.last_execution_steps:
                self.last_execution_steps = (
                    self._mode_step(
                        "execution.retype",
                        (
                            StepState.SUCCEEDED
                            if success
                            else StepState.FAILED
                        ),
                        decisive=not success,
                    ),
                )
            return success
        elif mode == "selection_expand":
            sel_mode = SelectionMode(
                self.selection,
                self.xkb,
                self.system,
                self.debug,
                expand=True,
                timing=self.timing,
                layout_switch_controller=self.layout_switch_controller,
            )
            success = sel_mode.execute(context)
            self.last_execution_steps = self._selection_execution_steps(
                mode,
                sel_mode,
                success,
            )
            if success:
                self._remember_selection_conversion(mode, sel_mode)
            return success
        else:
            sel_mode = SelectionMode(
                self.selection,
                self.xkb,
                self.system,
                self.debug,
                timing=self.timing,
                layout_switch_controller=self.layout_switch_controller,
            )
            success = sel_mode.execute(context)
            self.last_execution_steps = self._selection_execution_steps(
                mode,
                sel_mode,
                success,
            )
            if success:
                self._remember_selection_conversion(mode, sel_mode)
            return success

    def _remember_selection_conversion(self, mode: str, sel_mode) -> None:
        self.last_conversion = {
            "mode": mode,
            "original": getattr(sel_mode, "last_original", ""),
            "converted": getattr(sel_mode, "last_converted", ""),
            "target_lang": getattr(sel_mode, "last_target_lang", None),
        }

    @classmethod
    def _selection_execution_steps(
        cls,
        mode: str,
        selection_mode,
        success: bool,
    ) -> tuple[DecisionTraceStep, ...]:
        return (
            cls._mode_step(
                "execution.selection",
                StepState.SUCCEEDED if success else StepState.FAILED,
                decisive=not success,
                mode=mode,
                original=getattr(selection_mode, "last_original", ""),
                converted=getattr(selection_mode, "last_converted", ""),
                target_lang=getattr(selection_mode, "last_target_lang", None),
            ),
            *(
                (
                    cls._mode_step(
                        "execution.success",
                        StepState.SUCCEEDED,
                        decisive=True,
                    ),
                )
                if success
                else ()
            ),
        )

    @staticmethod
    def _mode_step(
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
