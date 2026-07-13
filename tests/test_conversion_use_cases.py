"""Tests for application-level conversion use cases."""

from __future__ import annotations

from unittest.mock import MagicMock

from lswitch.core.auto_marker import AutoConversionMarker
from lswitch.core.decision_trace import (
    DecisionOutcome,
    DecisionTraceRecorder,
    ExecutionOutcome,
    TraceTrigger,
)
from lswitch.core.conversion_use_cases import (
    AutoConversionCandidate,
    KEY_BACKSPACE,
    KEY_SPACE,
    ManualConversionPreparer,
    ManualConversionUseCase,
    MidWordAutoConversionUseCase,
    PostConversionStateUpdater,
    RecentAutoConversionUseCase,
    SpaceAutoConversionUseCase,
    UndoAutoConversionUseCase,
)
from lswitch.core.conversion_engine import ConversionEngine
from lswitch.core.events import KeyEventData
from lswitch.core.layout_service import LayoutService
from lswitch.core.layout_switch_controller import LayoutSwitchController
from lswitch.core.learning_service import PendingManualLearning
from lswitch.core.selection_tracker import SelectionFreshnessTracker
from lswitch.core.states import State, StateContext
from lswitch.core.typed_buffer import TypedBufferService
from lswitch.intelligence.mid_word_detector import MidWordDecision, MidWordDetector
from lswitch.intelligence.auto_detector import AutoDetector
from lswitch.intelligence.dictionary_service import DictionaryService
from lswitch.intelligence.ngram_analyzer import NgramAnalyzer
from lswitch.intelligence.prefix_dictionary import PrefixDictionary
from lswitch.intelligence.user_dictionary import UserDictionary
from lswitch.input.key_mapper import keycode_to_char
from lswitch.core.retype_service import RetypeService
from lswitch.platform.xkb_adapter import LayoutInfo
from tests.conftest import MockXKBAdapter


def test_undo_auto_conversion_replays_original_events_and_records_correction():
    events = [KeyEventData(code=34, value=1, device_name="test")]
    marker = AutoConversionMarker(
        kind="space",
        original_word="ghbdtn",
        original_lang="en",
        target_lang="ru",
        direction="en_to_ru",
        word_events=events,
        converted_len=6,
        had_space=True,
        created_at=123.0,
    )
    virtual_kb = MagicMock()
    xkb = MagicMock()
    en_layout = LayoutInfo(name="en", index=0, xkb_name="us")
    xkb.get_layouts.return_value = [
        en_layout,
        LayoutInfo(name="ru", index=1, xkb_name="ru"),
    ]
    user_dict = MagicMock()
    use_case = UndoAutoConversionUseCase(
        virtual_kb=virtual_kb,
        xkb=xkb,
        user_dict=user_dict,
        timing={"undo_before_replay_delay": 0},
        debug=True,
    )

    ok = use_case.execute(marker)

    assert ok is True
    user_dict.add_correction.assert_called_once_with("ghbdtn", "en", debug=True)
    virtual_kb.tap_key.assert_any_call(KEY_BACKSPACE, n_times=7)
    xkb.switch_layout.assert_called_once_with(target=en_layout)
    virtual_kb.replay_events.assert_called_once_with(events)
    virtual_kb.tap_key.assert_any_call(KEY_SPACE)


def test_undo_auto_conversion_without_space_does_not_readd_space():
    marker = AutoConversionMarker(
        kind="mid_word",
        original_word="ghb",
        original_lang="en",
        target_lang="ru",
        direction="en_to_ru",
        word_events=[],
        converted_len=3,
        had_space=False,
    )
    virtual_kb = MagicMock()
    xkb = MagicMock()
    xkb.get_layouts.return_value = []
    use_case = UndoAutoConversionUseCase(
        virtual_kb=virtual_kb,
        xkb=xkb,
        timing={"undo_before_replay_delay": 0},
    )

    ok = use_case.execute(marker)

    assert ok is True
    virtual_kb.tap_key.assert_called_once_with(KEY_BACKSPACE, n_times=3)
    virtual_kb.replay_events.assert_called_once_with([])


def test_undo_policy_restores_layout_active_before_undo():
    marker = AutoConversionMarker.for_space_conversion(
        original_word="ghbdtn",
        original_lang="en",
        direction="en_to_ru",
        word_events=[],
    )
    virtual_kb = MagicMock()
    xkb = MockXKBAdapter()
    xkb.switch_layout(target=xkb.get_layouts()[1])
    xkb.switch_calls.clear()
    controller = LayoutSwitchController(
        xkb=xkb,
        virtual_kb=virtual_kb,
        keep_target_after_conversion=False,
    )
    use_case = UndoAutoConversionUseCase(
        virtual_kb=virtual_kb,
        xkb=xkb,
        timing={"undo_before_replay_delay": 0},
        layout_switch_controller=controller,
    )

    assert use_case.execute(marker) is True
    assert xkb.get_current_layout().name == "ru"
    assert [target.name for target in xkb.switch_calls] == ["en", "ru"]


def test_mid_word_undo_persists_protection_for_detector(tmp_path):
    marker = AutoConversionMarker.for_mid_word_conversion(
        original_word="ghbd",
        original_lang="en",
        direction="en_to_ru",
        word_events=[],
    )
    user_dict = UserDictionary(path=str(tmp_path / "user_dict.toml"))
    virtual_kb = MagicMock()
    xkb = MagicMock()
    xkb.get_layouts.return_value = []
    undo = UndoAutoConversionUseCase(
        virtual_kb=virtual_kb,
        xkb=xkb,
        user_dict=user_dict,
        timing={"undo_before_replay_delay": 0},
    )

    assert undo.execute(marker) is True

    detector = MidWordDetector(
        PrefixDictionary(ru_words={"привет"}),
        min_prefix_len=4,
        user_dict=user_dict,
        user_dict_min_weight=2,
    )
    decision = detector.should_switch("ghbd", "en")

    assert user_dict.get_weight("ghbd", "en") == -2
    assert decision.should_switch is False
    assert decision.reason == "exact user dictionary keep decision"


def test_recent_auto_conversion_undo_handles_empty_buffer():
    marker = AutoConversionMarker(
        kind="space",
        original_word="ghb",
        original_lang="en",
        target_lang="ru",
        direction="en_to_ru",
        word_events=[],
        converted_len=3,
        had_space=True,
    )
    undo = MagicMock()
    use_case = RecentAutoConversionUseCase(undo_use_case=undo)

    result = use_case.execute(marker=marker, chars_in_buffer=0)

    assert result.handled is True
    undo.execute.assert_called_once_with(marker)


def test_recent_auto_conversion_undo_skips_when_user_typed_more_text():
    marker = AutoConversionMarker(
        kind="space",
        original_word="ghb",
        original_lang="en",
        target_lang="ru",
        direction="en_to_ru",
        word_events=[],
        converted_len=3,
        had_space=True,
    )
    undo = MagicMock()
    use_case = RecentAutoConversionUseCase(undo_use_case=undo)

    result = use_case.execute(marker=marker, chars_in_buffer=1)

    assert result.handled is False
    undo.execute.assert_not_called()


def test_manual_conversion_preparer_prepares_learning_and_buffer():
    context = StateContext()
    context.event_buffer = [
        KeyEventData(code=34, value=1, device_name="test"),
        KeyEventData(code=35, value=1, device_name="test"),
    ]
    context.chars_in_buffer = 2
    pending = PendingManualLearning("gh", "en", False)
    learning_service = MagicMock()
    learning_service.prepare_pending_manual_learning.return_value = pending
    xkb = MagicMock()
    xkb.get_current_layout.return_value = LayoutInfo("en", 0, "us")
    xkb.keycode_to_char.side_effect = lambda code, _layout: keycode_to_char(code)
    typed_buffer = TypedBufferService()

    preparation = ManualConversionPreparer(
        typed_buffer=typed_buffer,
        learning_service=learning_service,
        layout_service=LayoutService(xkb),
        selection=None,
        xkb=xkb,
        decode_events=typed_buffer.decode,
    ).prepare(
        context=context,
        selection_valid_for_convert=False,
        raw_selection_valid=False,
        raw_selection_repeat_valid=False,
        has_auto_marker=False,
        sticky_events=[],
        extract_last_word=lambda _layout: ("gh", list(context.event_buffer)),
    )

    assert preparation.selection_valid_for_convert is False
    assert preparation.saved_events == context.event_buffer
    assert preparation.saved_count == 2
    assert preparation.pending_manual_learning is pending
    learning_service.prepare_pending_manual_learning.assert_called_once()


def test_manual_conversion_preparer_trims_retype_buffer_to_last_word():
    context = StateContext()
    context.event_buffer = [
        KeyEventData(code=30, value=1, device_name="test"),
        KeyEventData(code=KEY_SPACE, value=1, device_name="test"),
        KeyEventData(code=34, value=1, device_name="test"),
        KeyEventData(code=35, value=1, device_name="test"),
        KeyEventData(code=48, value=1, device_name="test"),
        KeyEventData(code=KEY_SPACE, value=1, device_name="test"),
    ]
    context.chars_in_buffer = len(context.event_buffer)
    learning_service = MagicMock()
    xkb = MagicMock()
    xkb.get_current_layout.return_value = LayoutInfo("en", 0, "us")
    xkb.keycode_to_char.side_effect = lambda code, _layout: keycode_to_char(code)
    typed_buffer = TypedBufferService()

    preparation = ManualConversionPreparer(
        typed_buffer=typed_buffer,
        learning_service=learning_service,
        layout_service=LayoutService(xkb),
        selection=None,
        xkb=xkb,
        decode_events=typed_buffer.decode,
    ).prepare(
        context=context,
        selection_valid_for_convert=False,
        raw_selection_valid=False,
        raw_selection_repeat_valid=False,
        has_auto_marker=False,
        sticky_events=[],
        extract_last_word=lambda _layout: ("ghb", []),
    )

    assert [event.code for event in preparation.saved_events] == [
        34,
        35,
        48,
        KEY_SPACE,
    ]
    assert preparation.saved_count == 4
    assert context.event_buffer == preparation.saved_events
    assert context.chars_in_buffer == 4


def test_post_conversion_marks_repeat_for_successful_selection_conversion():
    tracker = SelectionFreshnessTracker(valid=True)
    tracker.set_valid(True)
    updater = PostConversionStateUpdater(tracker)

    sticky = updater.update(
        success=True,
        saved_count=0,
        saved_events=[],
        selection_valid_for_convert=True,
    )

    assert sticky == []
    assert tracker.repeat_valid is True
    assert tracker.repeat_generation == tracker.generation


def test_post_conversion_clears_repeat_on_failure():
    tracker = SelectionFreshnessTracker(repeat_valid=True, repeat_generation=1)
    updater = PostConversionStateUpdater(tracker)

    updater.update(
        success=False,
        saved_count=0,
        saved_events=[],
        selection_valid_for_convert=True,
    )

    assert tracker.repeat_valid is False
    assert tracker.repeat_generation == 0


def test_post_conversion_returns_sticky_events_for_successful_retype_only():
    tracker = SelectionFreshnessTracker()
    updater = PostConversionStateUpdater(tracker)
    events = [KeyEventData(code=34, value=1)]

    sticky = updater.update(
        success=True,
        saved_count=1,
        saved_events=events,
        selection_valid_for_convert=False,
    )

    assert sticky == events
    assert sticky is not events

    selection_sticky = updater.update(
        success=True,
        saved_count=0,
        saved_events=[],
        selection_valid_for_convert=True,
    )

    assert selection_sticky == []


def test_manual_conversion_use_case_records_pending_learning_and_sticky_events():
    conversion_engine = MagicMock()
    conversion_engine.convert.return_value = True
    learning_service = MagicMock()
    learning_service.user_dict = object()
    tracker = SelectionFreshnessTracker()
    use_case = ManualConversionUseCase(
        conversion_engine=conversion_engine,
        learning_service=learning_service,
        post_conversion_updater=PostConversionStateUpdater(tracker),
    )
    events = [KeyEventData(code=34, value=1)]
    pending = PendingManualLearning("ghbdtn", "en", False)

    result = use_case.execute(
        context=StateContext(),
        selection_valid_for_convert=False,
        saved_events=events,
        saved_count=1,
        pending_manual_learning=pending,
    )

    assert result.success is True
    assert result.sticky_events == events
    assert result.sticky_events is not events
    conversion_engine.convert.assert_called_once()
    learning_service.record_manual_conversion.assert_called_once_with(
        "ghbdtn",
        "en",
        False,
    )


def test_manual_conversion_use_case_records_selection_learning_from_last_conversion():
    conversion_engine = MagicMock()
    conversion_engine.convert.return_value = True
    conversion_engine.last_conversion = {
        "mode": "selection",
        "original": "ghbdtn",
        "converted": "привет",
        "target_lang": "ru",
    }
    learning_service = MagicMock()
    learning_service.user_dict = object()
    tracker = SelectionFreshnessTracker(valid=True)
    tracker.set_valid(True)
    use_case = ManualConversionUseCase(
        conversion_engine=conversion_engine,
        learning_service=learning_service,
        post_conversion_updater=PostConversionStateUpdater(tracker),
    )

    result = use_case.execute(
        context=StateContext(),
        selection_valid_for_convert=True,
        saved_events=[],
        saved_count=0,
        pending_manual_learning=None,
    )

    assert result.success is True
    assert result.sticky_events == []
    assert tracker.repeat_valid is True
    learning_service.record_selection_conversion.assert_called_once_with(
        conversion_engine.last_conversion
    )


def test_manual_conversion_use_case_failure_skips_learning_and_clears_repeat():
    conversion_engine = MagicMock()
    conversion_engine.convert.return_value = False
    learning_service = MagicMock()
    learning_service.user_dict = object()
    tracker = SelectionFreshnessTracker(repeat_valid=True, repeat_generation=1)
    use_case = ManualConversionUseCase(
        conversion_engine=conversion_engine,
        learning_service=learning_service,
        post_conversion_updater=PostConversionStateUpdater(tracker),
    )

    result = use_case.execute(
        context=StateContext(),
        selection_valid_for_convert=True,
        saved_events=[],
        saved_count=0,
        pending_manual_learning=PendingManualLearning("word", "en", False),
    )

    assert result.success is False
    assert result.sticky_events == []
    assert tracker.repeat_valid is False
    learning_service.record_manual_conversion.assert_not_called()
    learning_service.record_selection_conversion.assert_not_called()


class _Detector:
    def __init__(self, should: bool):
        self.should = should
        self.calls = []

    def should_convert(self, word: str, current_lang: str):
        self.calls.append((word, current_lang))
        return self.should, "test"


class _CandidateProvider:
    def __init__(self, candidate: AutoConversionCandidate):
        self.candidate = candidate
        self.calls = []

    def candidate_for_context(self, *, context, current_layout_info):
        self.calls.append((context, current_layout_info))
        return self.candidate


class _MidWordDetector:
    def __init__(self, decision: MidWordDecision):
        self.decision = decision
        self.calls = []

    def should_switch(self, prefix: str, current_lang: str):
        self.calls.append((prefix, current_lang))
        return self.decision


def _context_with_events(codes: list[int]) -> StateContext:
    context = StateContext()
    context.state = State.TYPING
    context.event_buffer = [
        KeyEventData(code=code, value=1, device_name="test")
        for code in codes
    ]
    context.chars_in_buffer = len(context.event_buffer)
    return context


def _space_auto_use_case(
    *,
    should_convert: bool = True,
    auto_detector=None,
    trace_recorder=None,
):
    xkb = MagicMock()
    en_layout = LayoutInfo(name="en", index=0, xkb_name="us")
    ru_layout = LayoutInfo(name="ru", index=1, xkb_name="ru")
    xkb.get_current_layout.return_value = en_layout
    xkb.get_layouts.return_value = [en_layout, ru_layout]
    xkb.keycode_to_char.side_effect = lambda code, _layout: keycode_to_char(code)
    retype_service = MagicMock()
    retype_service.retype_events.return_value = True
    use_case = SpaceAutoConversionUseCase(
        auto_detector=auto_detector or _Detector(should_convert),
        typed_buffer=TypedBufferService(),
        xkb=xkb,
        retype_service=retype_service,
        timing={
            "auto_before_replay_delay": 0,
            "auto_before_space_delay": 0,
        },
        trace_recorder=trace_recorder,
    )
    return use_case, xkb, retype_service


def test_space_auto_conversion_use_case_uses_injected_candidate_provider():
    xkb = MagicMock()
    en_layout = LayoutInfo(name="en", index=0, xkb_name="us")
    ru_layout = LayoutInfo(name="ru", index=1, xkb_name="ru")
    xkb.get_current_layout.return_value = en_layout
    xkb.get_layouts.return_value = [en_layout, ru_layout]
    typed_buffer = MagicMock()
    retype_service = MagicMock()
    retype_service.retype_events.return_value = True
    detector = _Detector(True)
    candidate_events = [
        KeyEventData(code=34, value=1, device_name="provider"),
        KeyEventData(code=35, value=1, device_name="provider"),
    ]
    provider = _CandidateProvider(
        AutoConversionCandidate(
            text="zz",
            events=candidate_events,
            current_lang="en",
        )
    )
    use_case = SpaceAutoConversionUseCase(
        auto_detector=detector,
        typed_buffer=typed_buffer,
        xkb=xkb,
        retype_service=retype_service,
        timing={"auto_before_replay_delay": 0, "auto_before_space_delay": 0},
        candidate_provider=provider,
    )
    context = _context_with_events([30, 31, 32])

    result = use_case.execute(
        context=context,
        threshold=0,
        last_auto_marker=None,
    )

    assert result.space_consumed is True
    assert result.marker is not None
    assert result.marker.original_word == "zz"
    assert result.marker.word_events == candidate_events
    assert detector.calls == [("zz", "en")]
    typed_buffer.last_word.assert_not_called()
    assert provider.calls == [(context, en_layout)]
    retype_service.retype_events.assert_called_once_with(
        candidate_events,
        delete_count=3,
        target_layout=ru_layout,
        before_replay_delay=0,
        backspace_n_times_keyword=True,
    )


def test_space_auto_conversion_use_case_skips_empty_candidate_from_provider():
    xkb = MagicMock()
    en_layout = LayoutInfo(name="en", index=0, xkb_name="us")
    xkb.get_current_layout.return_value = en_layout
    typed_buffer = MagicMock()
    retype_service = MagicMock()
    detector = _Detector(True)
    provider = _CandidateProvider(
        AutoConversionCandidate(text="", events=[], current_lang="en")
    )
    use_case = SpaceAutoConversionUseCase(
        auto_detector=detector,
        typed_buffer=typed_buffer,
        xkb=xkb,
        retype_service=retype_service,
        candidate_provider=provider,
    )

    result = use_case.execute(
        context=_context_with_events([34, 35]),
        threshold=0,
        last_auto_marker=None,
    )

    assert result.space_consumed is False
    assert detector.calls == []
    typed_buffer.last_word.assert_not_called()
    retype_service.retype_events.assert_not_called()


def test_space_auto_conversion_use_case_retypes_word_and_returns_marker():
    use_case, xkb, retype_service = _space_auto_use_case()
    context = _context_with_events([34, 35, 48])
    original_events = list(context.event_buffer)

    result = use_case.execute(
        context=context,
        threshold=0,
        last_auto_marker=None,
    )

    assert result.space_consumed is True
    assert result.pending_space is True
    assert result.marker is not None
    assert result.marker.original_word == "ghb"
    assert result.marker.original_lang == "en"
    assert result.marker.direction == "en_to_ru"
    assert result.marker_changed is True
    retype_service.retype_events.assert_called_once_with(
        original_events,
        delete_count=4,
        target_layout=xkb.get_layouts.return_value[1],
        before_replay_delay=0,
        backspace_n_times_keyword=True,
    )
    assert context.event_buffer == []
    assert context.chars_in_buffer == 0
    assert context.state == State.IDLE


def test_space_auto_conversion_policy_restores_source_layout():
    virtual_kb = MagicMock()
    xkb = MockXKBAdapter()
    controller = LayoutSwitchController(
        xkb=xkb,
        virtual_kb=virtual_kb,
        keep_target_after_conversion=False,
    )
    use_case = SpaceAutoConversionUseCase(
        auto_detector=MagicMock(),
        typed_buffer=TypedBufferService(),
        xkb=xkb,
        retype_service=RetypeService(
            virtual_kb,
            xkb,
            layout_switch_controller=controller,
        ),
        timing={"auto_before_replay_delay": 0, "auto_before_space_delay": 0},
    )

    result = use_case.perform_conversion(
        context=_context_with_events([34, 35]),
        word_len=2,
        word_events=[KeyEventData(code=34, value=1)],
        direction="en_to_ru",
    )

    assert result.space_consumed is True
    assert xkb.get_current_layout().name == "en"
    assert [target.name for target in xkb.switch_calls] == ["ru", "en"]


def test_space_auto_conversion_use_case_consumes_previous_marker_without_conversion():
    use_case, _xkb, retype_service = _space_auto_use_case(
        should_convert=False
    )
    context = _context_with_events([34, 35, 48])
    marker = AutoConversionMarker.for_space_conversion(
        original_word="old",
        original_lang="en",
        direction="en_to_ru",
        word_events=[],
    )

    result = use_case.execute(
        context=context,
        threshold=0,
        last_auto_marker=marker,
    )

    assert result.space_consumed is False
    assert result.marker is None
    assert result.marker_changed is True
    retype_service.retype_events.assert_not_called()
    assert context.event_buffer


def test_space_auto_conversion_use_case_skips_below_threshold():
    ngrams = MagicMock()
    ngrams.score.side_effect = lambda _word, lang: 0.2 if lang == "ru" else 0.0
    use_case, _xkb, retype_service = _space_auto_use_case(
        auto_detector=AutoDetector(DictionaryService(), ngrams),
    )
    context = _context_with_events([34, 35, 48])

    result = use_case.execute(
        context=context,
        threshold=10,
        last_auto_marker=AutoConversionMarker.for_space_conversion(
            original_word="old",
            original_lang="en",
            direction="en_to_ru",
            word_events=[],
        ),
    )

    assert result.space_consumed is False
    assert result.marker_changed is True
    assert result.marker is None
    retype_service.retype_events.assert_not_called()


def _mid_word_use_case(
    *,
    decision: MidWordDecision,
    candidate: AutoConversionCandidate | None = None,
    retype_ok: bool = True,
    trace_recorder=None,
):
    xkb = MagicMock()
    en_layout = LayoutInfo(name="en", index=0, xkb_name="us")
    ru_layout = LayoutInfo(name="ru", index=1, xkb_name="ru")
    xkb.get_current_layout.return_value = en_layout
    xkb.get_layouts.return_value = [en_layout, ru_layout]
    retype_service = MagicMock()
    retype_service.retype_events.return_value = retype_ok
    detector = _MidWordDetector(decision)
    provider = _CandidateProvider(
        candidate
        or AutoConversionCandidate(
            text="ghbd",
            events=[
                KeyEventData(code=34, value=1, device_name="provider"),
                KeyEventData(code=35, value=1, device_name="provider"),
                KeyEventData(code=48, value=1, device_name="provider"),
                KeyEventData(code=32, value=1, device_name="provider"),
            ],
            current_lang="en",
        )
    )
    use_case = MidWordAutoConversionUseCase(
        mid_word_detector=detector,
        typed_buffer=MagicMock(),
        xkb=xkb,
        retype_service=retype_service,
        timing={"mid_word_before_replay_delay": 0},
        candidate_provider=provider,
        trace_recorder=trace_recorder,
    )
    return use_case, detector, provider, retype_service, ru_layout


def test_mid_word_auto_conversion_use_case_retypes_prefix_and_returns_marker():
    decision = MidWordDecision(
        should_switch=True,
        reason="target prefix found and source prefix absent",
        current_lang="en",
        target_lang="ru",
        typed_prefix="ghbd",
        converted_prefix="прив",
        target_prefix_count=1,
    )
    use_case, detector, provider, retype_service, ru_layout = _mid_word_use_case(
        decision=decision
    )
    context = _context_with_events([34, 35, 48, 32])
    candidate = provider.candidate

    result = use_case.execute(context=context)

    assert result.switched is True
    assert result.marker is not None
    assert result.marker.kind == "mid_word"
    assert result.marker.original_word == "ghbd"
    assert result.marker.original_lang == "en"
    assert result.marker.target_lang == "ru"
    assert result.marker.had_space is False
    assert result.marker.converted_len == 4
    assert result.marker_changed is True
    assert detector.calls == [("ghbd", "en")]
    retype_service.retype_events.assert_called_once_with(
        candidate.events,
        delete_count=4,
        target_layout=ru_layout,
        before_replay_delay=0,
        backspace_n_times_keyword=True,
    )
    assert context.event_buffer == []
    assert context.chars_in_buffer == 0
    assert context.state == State.IDLE


def test_mid_word_auto_conversion_policy_restores_source_layout():
    decision = MidWordDecision(
        should_switch=True,
        reason="target prefix found",
        current_lang="en",
        target_lang="ru",
    )
    candidate = AutoConversionCandidate(
        text="ghbd",
        events=[KeyEventData(code=34, value=1)],
        current_lang="en",
    )
    virtual_kb = MagicMock()
    xkb = MockXKBAdapter()
    controller = LayoutSwitchController(
        xkb=xkb,
        virtual_kb=virtual_kb,
        keep_target_after_conversion=False,
    )
    use_case = MidWordAutoConversionUseCase(
        mid_word_detector=_MidWordDetector(decision),
        typed_buffer=MagicMock(),
        xkb=xkb,
        retype_service=RetypeService(
            virtual_kb,
            xkb,
            layout_switch_controller=controller,
        ),
        timing={"mid_word_before_replay_delay": 0},
        candidate_provider=_CandidateProvider(candidate),
    )

    result = use_case.execute(context=_context_with_events([34]))

    assert result.switched is True
    assert xkb.get_current_layout().name == "en"
    assert [target.name for target in xkb.switch_calls] == ["ru", "en"]


def test_mid_word_auto_conversion_use_case_skips_when_detector_rejects():
    decision = MidWordDecision(
        should_switch=False,
        reason="source prefix exists",
        current_lang="en",
        target_lang="ru",
    )
    use_case, detector, _provider, retype_service, _ru_layout = _mid_word_use_case(
        decision=decision
    )
    context = _context_with_events([34, 35, 48, 32])

    result = use_case.execute(context=context)

    assert result.switched is False
    assert result.reason == "source prefix exists"
    assert detector.calls == [("ghbd", "en")]
    retype_service.retype_events.assert_not_called()
    assert context.event_buffer


def test_mid_word_auto_conversion_use_case_keeps_context_when_retype_fails():
    decision = MidWordDecision(
        should_switch=True,
        reason="target prefix found and source prefix absent",
        current_lang="en",
        target_lang="ru",
    )
    use_case, _detector, _provider, retype_service, _ru_layout = _mid_word_use_case(
        decision=decision,
        retype_ok=False,
    )
    context = _context_with_events([34, 35, 48, 32])

    result = use_case.execute(context=context)

    assert result.switched is False
    assert result.reason == "retype failed"
    assert result.marker is None
    retype_service.retype_events.assert_called_once()
    assert context.event_buffer


def test_space_auto_trace_keeps_decision_separate_from_execution_success():
    recorder = DecisionTraceRecorder(enabled=True)
    xkb = MagicMock()
    en_layout = LayoutInfo(name="en", index=0, xkb_name="us")
    ru_layout = LayoutInfo(name="ru", index=1, xkb_name="ru")
    xkb.get_current_layout.return_value = en_layout
    xkb.get_layouts.return_value = [en_layout, ru_layout]
    events = [KeyEventData(code=code, value=1) for code in [34, 35, 48, 32, 20, 49]]
    provider = _CandidateProvider(
        AutoConversionCandidate(
            text="ghbdtn",
            events=events,
            current_lang="en",
        )
    )
    retype_service = MagicMock()
    retype_service.retype_events.return_value = True
    retype_service.last_trace_steps = ()
    use_case = SpaceAutoConversionUseCase(
        auto_detector=AutoDetector(DictionaryService(), NgramAnalyzer()),
        typed_buffer=MagicMock(),
        xkb=xkb,
        retype_service=retype_service,
        timing={"auto_before_replay_delay": 0, "auto_before_space_delay": 0},
        candidate_provider=provider,
        trace_recorder=recorder,
    )

    result = use_case.execute(
        context=_context_with_events([34, 35, 48, 32, 20, 49]),
        threshold=0,
        last_auto_marker=None,
        correlation_id=42,
    )

    assert result.execution_succeeded is True
    trace = recorder.snapshot()[0]
    assert trace.correlation_id == 42
    assert trace.trigger is TraceTrigger.SPACE_AUTO
    assert trace.decision is DecisionOutcome.CONVERT
    assert trace.execution is ExecutionOutcome.SUCCEEDED
    assert trace.converted == "привет"
    assert trace.conversion_mode == "retype"
    assert trace.attempts[0].steps[-1].rule_id == "auto.ngram.delta"
    assert trace.execution_steps[-1].rule_id == "execution.retype"


def test_space_auto_trace_preserves_convert_decision_when_retype_fails():
    recorder = DecisionTraceRecorder(enabled=True)
    use_case, _xkb, retype_service = _space_auto_use_case(
        trace_recorder=recorder
    )
    retype_service.retype_events.return_value = False
    retype_service.last_trace_steps = ()

    result = use_case.execute(
        context=_context_with_events([34, 35, 48]),
        threshold=0,
        last_auto_marker=None,
        correlation_id=5,
    )

    trace = recorder.snapshot()[0]
    assert result.execution_succeeded is False
    assert trace.decision is DecisionOutcome.CONVERT
    assert trace.execution is ExecutionOutcome.FAILED


def test_space_auto_threshold_is_recorded_inside_ngram_fallback():
    recorder = DecisionTraceRecorder(enabled=True)
    ngrams = MagicMock()
    ngrams.score.side_effect = lambda _word, lang: 0.2 if lang == "ru" else 0.0
    use_case, _xkb, retype_service = _space_auto_use_case(
        auto_detector=AutoDetector(DictionaryService(), ngrams),
        trace_recorder=recorder
    )

    use_case.execute(
        context=_context_with_events([34, 35, 48]),
        threshold=10,
        last_auto_marker=None,
        correlation_id=6,
    )

    trace = recorder.snapshot()[0]
    assert trace.decision is DecisionOutcome.SKIP
    assert trace.attempts[0].steps[-1].rule_id == "auto.ngram.min_length"
    ngrams.score.assert_not_called()
    retype_service.retype_events.assert_not_called()


def test_mid_word_trace_aggregates_prefix_attempts_for_one_session():
    recorder = DecisionTraceRecorder(enabled=True)
    xkb = MagicMock()
    en_layout = LayoutInfo(name="en", index=0, xkb_name="us")
    ru_layout = LayoutInfo(name="ru", index=1, xkb_name="ru")
    xkb.get_current_layout.return_value = en_layout
    xkb.get_layouts.return_value = [en_layout, ru_layout]
    provider = _CandidateProvider(
        AutoConversionCandidate(
            text="ghb",
            events=[KeyEventData(code=code, value=1) for code in [34, 35, 48]],
            current_lang="en",
        )
    )
    retype_service = MagicMock()
    retype_service.retype_events.return_value = True
    retype_service.last_trace_steps = ()
    use_case = MidWordAutoConversionUseCase(
        mid_word_detector=MidWordDetector(
            PrefixDictionary(ru_words={"привет"}),
            min_prefix_len=4,
        ),
        typed_buffer=MagicMock(),
        xkb=xkb,
        retype_service=retype_service,
        timing={"mid_word_before_replay_delay": 0},
        candidate_provider=provider,
        trace_recorder=recorder,
    )

    first = use_case.execute(
        context=_context_with_events([34, 35, 48]),
        correlation_id=9,
    )
    provider.candidate = AutoConversionCandidate(
        text="ghbd",
        events=[KeyEventData(code=code, value=1) for code in [34, 35, 48, 32]],
        current_lang="en",
    )
    second = use_case.execute(
        context=_context_with_events([34, 35, 48, 32]),
        correlation_id=9,
    )

    assert first.switched is False
    assert second.switched is True
    assert len(recorder.snapshot()) == 1
    trace = recorder.snapshot()[0]
    assert trace.trigger is TraceTrigger.MID_WORD
    assert [attempt.candidate for attempt in trace.attempts] == ["ghb", "ghbd"]
    assert trace.decision is DecisionOutcome.CONVERT
    assert trace.execution is ExecutionOutcome.SUCCEEDED


def test_related_mid_word_and_space_traces_share_correlation_id():
    recorder = DecisionTraceRecorder(enabled=True)
    mid_decision = MidWordDecision(
        should_switch=False,
        reason="prefix below threshold",
        current_lang="en",
    )
    mid_use_case, _detector, _provider, _retype, _layout = _mid_word_use_case(
        decision=mid_decision,
        trace_recorder=recorder,
    )
    mid_use_case.execute(
        context=_context_with_events([34, 35, 48, 32]),
        correlation_id=77,
    )

    space_use_case, _xkb, _retype = _space_auto_use_case(
        should_convert=False,
        trace_recorder=recorder,
    )
    space_use_case.execute(
        context=_context_with_events([34, 35, 48]),
        threshold=0,
        last_auto_marker=None,
        correlation_id=77,
    )

    traces = recorder.snapshot()
    assert len(traces) == 2
    assert {trace.trigger for trace in traces} == {
        TraceTrigger.MID_WORD,
        TraceTrigger.SPACE_AUTO,
    }
    assert {trace.correlation_id for trace in traces} == {77}


def test_manual_retype_trace_records_mode_and_execution_steps():
    recorder = DecisionTraceRecorder(enabled=True)
    xkb = MockXKBAdapter()
    virtual_kb = MagicMock()
    engine = ConversionEngine(
        xkb=xkb,
        selection=MagicMock(),
        virtual_kb=virtual_kb,
        dictionary=MagicMock(),
        system=MagicMock(),
        timing={"retype_before_replay_delay": 0},
    )
    learning_service = MagicMock()
    learning_service.user_dict = None
    updater = MagicMock()
    updater.update.return_value = []
    use_case = ManualConversionUseCase(
        conversion_engine=engine,
        learning_service=learning_service,
        post_conversion_updater=updater,
        trace_recorder=recorder,
    )
    context = _context_with_events([34, 35, 48, 32, 20, 49])

    result = use_case.execute(
        context=context,
        selection_valid_for_convert=False,
        saved_events=list(context.event_buffer),
        saved_count=6,
        pending_manual_learning=PendingManualLearning(
            "ghbdtn",
            "en",
            False,
        ),
        original_text="ghbdtn",
    )

    assert result.success is True
    trace = recorder.snapshot()[0]
    assert trace.trigger is TraceTrigger.MANUAL
    assert trace.decision is DecisionOutcome.CONVERT
    assert trace.execution is ExecutionOutcome.SUCCEEDED
    assert trace.conversion_mode == "retype"
    assert trace.original == "ghbdtn"
    assert trace.converted == "привет"
    assert trace.attempts[0].steps[-1].rule_id == "manual.mode.buffer_retype"
    assert any(
        step.rule_id == "execution.replay"
        for step in trace.execution_steps
    )


def test_manual_trace_records_engine_exception_without_swallowing_it():
    recorder = DecisionTraceRecorder(enabled=True)
    engine = MagicMock()
    engine.convert.side_effect = RuntimeError("manual failed")
    engine.last_mode_decision = None
    engine.last_execution_steps = ()
    learning_service = MagicMock()
    updater = MagicMock()
    use_case = ManualConversionUseCase(
        conversion_engine=engine,
        learning_service=learning_service,
        post_conversion_updater=updater,
        trace_recorder=recorder,
    )

    try:
        use_case.execute(
            context=StateContext(),
            selection_valid_for_convert=False,
            saved_events=[],
            saved_count=0,
            pending_manual_learning=None,
            original_text="word",
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError("manual exception was not propagated")

    trace = recorder.snapshot()[0]
    assert trace.execution is ExecutionOutcome.FAILED
    assert trace.decision is DecisionOutcome.CONVERT
    assert trace.execution_steps[-1].rule_id == "execution.error"


def test_undo_trace_records_successful_restore_path():
    recorder = DecisionTraceRecorder(enabled=True)
    marker = AutoConversionMarker.for_space_conversion(
        original_word="ghbdtn",
        original_lang="en",
        direction="en_to_ru",
        word_events=[KeyEventData(code=34, value=1)],
    )
    xkb = MockXKBAdapter()
    xkb.switch_layout(target=xkb.get_layouts()[1])
    virtual_kb = MagicMock()
    learning_service = MagicMock()
    use_case = UndoAutoConversionUseCase(
        virtual_kb=virtual_kb,
        xkb=xkb,
        learning_service=learning_service,
        timing={"undo_before_replay_delay": 0},
        trace_recorder=recorder,
    )

    assert use_case.execute(marker) is True

    trace = recorder.snapshot()[0]
    assert trace.trigger is TraceTrigger.UNDO
    assert trace.original == "привет"
    assert trace.converted == "ghbdtn"
    assert trace.execution is ExecutionOutcome.SUCCEEDED
    assert trace.execution_steps[-1].rule_id == "execution.success"


def test_undo_trace_records_execution_failure():
    recorder = DecisionTraceRecorder(enabled=True)
    marker = AutoConversionMarker.for_mid_word_conversion(
        original_word="ghbd",
        original_lang="en",
        direction="en_to_ru",
        word_events=[],
    )
    virtual_kb = MagicMock()
    virtual_kb.tap_key.side_effect = RuntimeError("delete failed")
    use_case = UndoAutoConversionUseCase(
        virtual_kb=virtual_kb,
        xkb=MockXKBAdapter(),
        learning_service=MagicMock(),
        timing={"undo_before_replay_delay": 0},
        trace_recorder=recorder,
    )

    assert use_case.execute(marker) is False

    trace = recorder.snapshot()[0]
    assert trace.decision is DecisionOutcome.CONVERT
    assert trace.execution is ExecutionOutcome.FAILED
    assert trace.execution_steps[-1].rule_id == "execution.error"
