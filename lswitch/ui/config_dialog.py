"""Modeless five-page settings dialog backed by a mergeable draft."""

from __future__ import annotations

import os

from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from lswitch.core.events import EventType
from lswitch.i18n import t
from lswitch.runtime_config import RuntimeConfigController
from lswitch.ui.settings_model import (
    PAGE_ADVANCED,
    PAGE_AUTO,
    PAGE_DICTIONARIES,
    PAGE_GENERAL,
    PAGE_SELECTION,
    SETTINGS_BINDINGS,
    SETTINGS_BINDING_BY_PATH,
    SETTINGS_PAGES,
    SettingsDraftModel,
    platform_visibility,
)


_PAGE_LABEL_KEYS = {
    PAGE_GENERAL: "settings_page_general",
    PAGE_AUTO: "settings_page_auto",
    PAGE_DICTIONARIES: "settings_page_dictionaries",
    PAGE_SELECTION: "settings_page_selection",
    PAGE_ADVANCED: "settings_page_advanced",
}
_STRATEGY_LABEL_KEYS = {
    "auto": "settings_strategy_auto",
    "clipboard_copy": "settings_strategy_clipboard",
    "primary_selection": "settings_strategy_primary",
    "disabled": "settings_strategy_disabled",
}


class ConfigDialog(QDialog):
    """Edit a local draft and commit it through RuntimeConfigController."""

    def __init__(
        self,
        config=None,
        event_bus=None,
        parent=None,
        config_controller=None,
        app=None,
    ):
        super().__init__(parent)
        self.config = config
        self.event_bus = event_bus
        self.app = app
        self.config_controller = config_controller
        if self.config_controller is None and self.config is not None:
            self.config_controller = RuntimeConfigController(
                config=self.config,
                event_bus=self.event_bus,
            )

        committed = self.config.get_all() if self.config is not None else None
        self.model = SettingsDraftModel(committed)
        self._widgets: dict[str, object] = {}
        self._control_groups: dict[str, list[object]] = {}
        self._row_groups: dict[str, list[object]] = {}
        self._setting_help_icons: dict[str, QLabel] = {}
        self._rendered_values: dict[str, object] = {}
        self._page_widgets: dict[str, object] = {}
        self._dictionary_status_labels: dict[str, QLabel] = {}
        self._platform_warning_label = None
        self._loading = False
        self._applying = False
        self._last_error: str | None = None
        self._subscribed = False
        self._session_type = self._current_session_type()

        self.setWindowTitle(t("settings_title"))
        if hasattr(self, "setMinimumSize"):
            self.setMinimumSize(720, 560)
        else:
            self.setMinimumWidth(720)

        self._build_ui()
        self._apply_platform_visibility()
        self._auto_switch_cb = self._widgets["auto_switch"]
        self._threshold_spin = self._widgets["auto_switch_threshold"]
        self._user_dict_cb = self._widgets["user_dict_enabled"]
        self._dct_spin = self._widgets["double_click_timeout"]
        self._populate_widgets()
        self._subscribe()

    # -- UI construction -------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        self._conflict_label = QLabel(t("settings_external_change"))
        if hasattr(self._conflict_label, "setWordWrap"):
            self._conflict_label.setWordWrap(True)
        self._conflict_label.hide()
        root.addWidget(self._conflict_label)

        body = QHBoxLayout()
        self._navigation = QListWidget()
        self._navigation.addItems(
            [t(_PAGE_LABEL_KEYS[page]) for page in SETTINGS_PAGES]
        )
        if hasattr(self._navigation, "setFixedWidth"):
            self._navigation.setFixedWidth(190)
        body.addWidget(self._navigation)

        self._stack = QStackedWidget()
        for page in SETTINGS_PAGES:
            self._stack.addWidget(self._build_page(page))
        body.addWidget(self._stack)
        root.addLayout(body)

        self._navigation.currentRowChanged.connect(self._stack.setCurrentIndex)
        self._navigation.setCurrentRow(0)

        self._status_label = QLabel("")
        if hasattr(self._status_label, "setWordWrap"):
            self._status_label.setWordWrap(True)
        root.addWidget(self._status_label)

        buttons = QHBoxLayout()
        self._reset_page_btn = QPushButton(t("settings_reset_page"))
        self._reset_all_btn = QPushButton(t("settings_reset_all"))
        self._cancel_btn = QPushButton(t("settings_cancel"))
        self._apply_btn = QPushButton(t("settings_apply"))
        self._ok_btn = QPushButton(t("settings_ok"))
        buttons.addWidget(self._reset_page_btn)
        buttons.addWidget(self._reset_all_btn)
        buttons.addStretch()
        buttons.addWidget(self._cancel_btn)
        buttons.addWidget(self._apply_btn)
        buttons.addWidget(self._ok_btn)
        root.addLayout(buttons)

        self._reset_page_btn.clicked.connect(self._reset_current_page)
        self._reset_all_btn.clicked.connect(self._reset_defaults)
        self._cancel_btn.clicked.connect(self.reject)
        self._apply_btn.clicked.connect(self.apply)
        self._ok_btn.clicked.connect(self.accept)

    def _build_page(self, page: str):
        content = QWidget()
        form = QFormLayout(content)
        for binding in SETTINGS_BINDINGS:
            if binding.page != page:
                continue
            label = QLabel(t(binding.label_key))
            help_icon = self._create_help_icon(binding)
            label_container = QWidget()
            label_layout = QHBoxLayout(label_container)
            if hasattr(label_layout, "setContentsMargins"):
                label_layout.setContentsMargins(0, 0, 0, 0)
            if hasattr(label_layout, "setSpacing"):
                label_layout.setSpacing(4)
            label_layout.addWidget(label)
            label_layout.addWidget(help_icon)
            label_layout.addStretch()
            control, group = self._create_control(binding)
            self._widgets[binding.path] = control
            self._control_groups[binding.path] = [label, *group]
            self._row_groups[binding.path] = [
                label_container,
                label,
                help_icon,
                *group,
            ]
            self._setting_help_icons[binding.path] = help_icon
            form.addRow(
                label_container,
                group[0] if len(group) == 1 else group[-1],
            )
            if binding.path in {
                "system_dict_en_path",
                "system_dict_ru_path",
            }:
                lang = (
                    "en"
                    if binding.path == "system_dict_en_path"
                    else "ru"
                )
                status_label = QLabel("")
                if hasattr(status_label, "setWordWrap"):
                    status_label.setWordWrap(True)
                self._dictionary_status_labels[lang] = status_label
                form.addRow(
                    QLabel(t(f"settings_system_dict_{lang}_status")),
                    status_label,
                )

        if page == PAGE_GENERAL:
            shortcut_note = QLabel(t("settings_shortcut_help"))
            if hasattr(shortcut_note, "setWordWrap"):
                shortcut_note.setWordWrap(True)
            form.addRow(QLabel(""), shortcut_note)
            form.addRow(
                QLabel(t("settings_platform")),
                QLabel(self._platform_description()),
            )
            if self._session_type == "unknown":
                self._platform_warning_label = QLabel(
                    t("settings_platform_unknown_warning")
                )
                if hasattr(self._platform_warning_label, "setWordWrap"):
                    self._platform_warning_label.setWordWrap(True)
                form.addRow(QLabel(""), self._platform_warning_label)
        elif page == PAGE_SELECTION:
            self._strategy_help_label = QLabel("")
            self._strategy_help = QLabel("")
            if hasattr(self._strategy_help, "setWordWrap"):
                self._strategy_help.setWordWrap(True)
            form.addRow(self._strategy_help_label, self._strategy_help)
        elif page == PAGE_ADVANCED:
            path = self.config.config_path if self.config is not None else ""
            path_widget = QLineEdit(path)
            path_widget.setReadOnly(True)
            form.addRow(QLabel(t("settings_config_path")), path_widget)
            if self._trace_override_active():
                trace_note = QLabel(t("settings_trace_override"))
                if hasattr(trace_note, "setWordWrap"):
                    trace_note.setWordWrap(True)
                form.addRow(QLabel(""), trace_note)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        self._page_widgets[page] = content
        return scroll

    def _create_help_icon(self, binding) -> QLabel:
        description = t(binding.help_key)
        icon = QLabel("ⓘ")
        icon.setToolTip(description)
        if hasattr(icon, "setToolTipDuration"):
            icon.setToolTipDuration(30_000)
        if hasattr(icon, "setStyleSheet"):
            icon.setStyleSheet("font-size: 16px;")
        if hasattr(icon, "setAccessibleName"):
            icon.setAccessibleName(
                t("settings_help_accessible", setting=t(binding.label_key))
            )
        if hasattr(icon, "setAccessibleDescription"):
            icon.setAccessibleDescription(description)
        return icon

    def _create_control(self, binding):
        if binding.widget == "bool":
            widget = QCheckBox()
            widget.toggled.connect(
                lambda _value, path=binding.path: self._on_widget_changed(path)
            )
            return widget, [widget]

        if binding.widget == "int":
            widget = QSpinBox()
            widget.setRange(int(binding.minimum), int(binding.maximum))
            widget.setSingleStep(1)
            widget.valueChanged.connect(
                lambda _value, path=binding.path: self._on_widget_changed(path)
            )
            return widget, [widget]

        if binding.widget == "float":
            widget = QDoubleSpinBox()
            widget.setRange(float(binding.minimum), float(binding.maximum))
            widget.setDecimals(max(9, int(binding.decimals or 6)))
            widget.setSingleStep(0.001)
            if hasattr(widget, "setSuffix"):
                widget.setSuffix(f" {t('settings_seconds')}")
            widget.valueChanged.connect(
                lambda _value, path=binding.path: self._on_widget_changed(path)
            )
            return widget, [widget]

        if binding.widget == "choice":
            widget = QComboBox()
            for option in binding.options:
                widget.addItem(t(_STRATEGY_LABEL_KEYS[option]), option)
            widget.currentIndexChanged.connect(
                lambda _index, path=binding.path: self._on_widget_changed(path)
            )
            return widget, [widget]

        if binding.widget == "shortcut":
            widget = QKeySequenceEdit()
            widget.keySequenceChanged.connect(
                lambda _sequence, path=binding.path: self._on_widget_changed(path)
            )
            return widget, [widget]

        if binding.widget == "path":
            line_edit = QLineEdit()
            if hasattr(line_edit, "setPlaceholderText"):
                line_edit.setPlaceholderText(
                    t("settings_dictionary_path_auto_placeholder")
                )
            browse = QPushButton(t("settings_browse"))
            container = QWidget()
            layout = QHBoxLayout(container)
            if hasattr(layout, "setContentsMargins"):
                layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(line_edit)
            layout.addWidget(browse)
            line_edit.textChanged.connect(
                lambda _text, path=binding.path: self._on_widget_changed(path)
            )
            browse.clicked.connect(
                lambda _checked=False, path=binding.path: self._browse_dictionary(path)
            )
            return line_edit, [line_edit, browse, container]

        raise ValueError(f"Unsupported settings widget: {binding.widget}")

    # -- draft/widget synchronization -----------------------------------

    def _populate_widgets(self) -> None:
        self._loading = True
        try:
            for binding in SETTINGS_BINDINGS:
                widget = self._widgets[binding.path]
                value = self.model.get(binding.path)
                self._write_widget(binding, widget, value)
                self._rendered_values[binding.path] = self._read_widget(
                    binding,
                    widget,
                )
        finally:
            self._loading = False
        self._apply_dependencies()
        self._update_dictionary_status()
        self._update_dirty_state()

    def _write_widget(self, binding, widget, value) -> None:
        if binding.widget == "bool":
            widget.setChecked(bool(value))
        elif binding.widget in {"int", "float"}:
            widget.setValue(value)
        elif binding.widget == "choice":
            index = widget.findData(value)
            widget.setCurrentIndex(max(0, index))
        elif binding.widget == "shortcut":
            widget.setKeySequence(QKeySequence(str(value)))
        elif binding.widget == "path":
            widget.setText(str(value or ""))

    def _read_widget(self, binding, widget):
        if binding.widget == "bool":
            return bool(widget.isChecked())
        if binding.widget == "int":
            return int(widget.value())
        if binding.widget == "float":
            return float(widget.value())
        if binding.widget == "choice":
            return widget.currentData()
        if binding.widget == "shortcut":
            sequence = widget.keySequence()
            try:
                return sequence.toString(QKeySequence.SequenceFormat.PortableText)
            except (AttributeError, TypeError):
                return sequence.toString()
        if binding.widget == "path":
            return widget.text()
        raise ValueError(f"Unsupported settings widget: {binding.widget}")

    def _on_widget_changed(self, path: str) -> None:
        if self._loading:
            return
        binding = SETTINGS_BINDING_BY_PATH[path]
        self.model.set(path, self._read_widget(binding, self._widgets[path]))
        self._apply_dependencies()
        self._update_dictionary_status()
        self._update_dirty_state()

    def _sync_changed_widgets(self) -> None:
        """Support programmatic edits while avoiding float roundtrip churn."""
        for binding in SETTINGS_BINDINGS:
            current = self._read_widget(binding, self._widgets[binding.path])
            if current != self._rendered_values.get(binding.path):
                self.model.set(binding.path, current)

    def _apply_dependencies(self) -> None:
        enabled = self.model.enabled_paths()
        for path, group in self._control_groups.items():
            is_enabled = enabled[path]
            for item in group:
                if hasattr(item, "setEnabled"):
                    item.setEnabled(is_enabled)
                if hasattr(item, "setToolTip"):
                    item.setToolTip(
                        "" if is_enabled else t("settings_dependency_disabled")
                    )
        strategy = self.model.get("wayland_selection_strategy", "auto")
        if hasattr(self, "_strategy_help"):
            self._strategy_help.setText(
                t(f"settings_strategy_help_{strategy}")
            )

    def _apply_platform_visibility(self) -> None:
        visible_paths = platform_visibility(self._session_type)
        for path, group in self._row_groups.items():
            visible = visible_paths[path]
            for item in group:
                if hasattr(item, "setVisible"):
                    item.setVisible(visible)
                elif visible and hasattr(item, "show"):
                    item.show()
                elif not visible and hasattr(item, "hide"):
                    item.hide()
        wayland_visible = visible_paths["wayland_selection_strategy"]
        for item in (
            getattr(self, "_strategy_help_label", None),
            getattr(self, "_strategy_help", None),
        ):
            if item is not None and hasattr(item, "setVisible"):
                item.setVisible(wayland_visible)

    def _update_dirty_state(self) -> None:
        if hasattr(self._apply_btn, "setEnabled"):
            self._apply_btn.setEnabled(self.model.is_dirty)
        if self.model.external_change_pending:
            self._conflict_label.show()
        else:
            self._conflict_label.hide()

    def _update_dictionary_status(self) -> None:
        statuses = {
            getattr(status, "lang", ""): status
            for status in (
                getattr(self.app, "system_dictionary_statuses", ()) or ()
            )
        }
        active_in_draft = bool(
            self.model.get("auto_switch_mid_word", False)
            and self.model.get("system_dict_enabled", False)
        )
        for lang, label in self._dictionary_status_labels.items():
            status = statuses.get(lang)
            if status is None:
                key = (
                    "settings_dictionary_status_unavailable"
                    if active_in_draft
                    else "settings_dictionary_status_disabled"
                )
                label.setText(t(key))
                continue
            if not getattr(status, "enabled", False):
                label.setText(t("settings_dictionary_status_disabled"))
                continue
            path = getattr(status, "path", None)
            if path is None:
                label.setText(t("settings_dictionary_status_not_found"))
                continue
            count = f"{int(getattr(status, 'word_count', 0)):,}".replace(
                ",",
                " ",
            )
            source = (
                "explicit"
                if getattr(status, "explicit", False)
                else "auto"
            )
            label.setText(
                t(
                    f"settings_dictionary_status_loaded_{source}",
                    path=str(path),
                    count=count,
                )
            )

    # -- commands --------------------------------------------------------

    def apply(self) -> bool:
        return self._commit(close_on_success=False)

    def _apply_values(self) -> bool:
        """Compatibility wrapper used by older callers/tests."""
        return self.apply()

    def _commit(self, *, close_on_success: bool) -> bool:
        self._sync_changed_widgets()
        if self.config is None or self.config_controller is None:
            if close_on_success:
                super().accept()
            return True

        candidate = self.model.build_candidate(self.config.get_all())
        self._set_busy(True)
        self._applying = True
        try:
            result = self.config_controller.apply(candidate, source="gui")
        finally:
            self._applying = False
            self._set_busy(False)

        if not result.ok:
            self._last_error = result.error or t("settings_unknown_error")
            self._status_label.setText(self._last_error)
            QMessageBox.critical(
                self,
                t("settings_error_title"),
                self._last_error,
            )
            self._update_dirty_state()
            return False

        self._last_error = None
        self._status_label.setText(t("settings_applied"))
        self.model.mark_committed(self.config.get_all())
        self._populate_widgets()
        if close_on_success:
            super().accept()
        return True

    def _set_busy(self, busy: bool) -> None:
        for button in (self._apply_btn, self._ok_btn, self._reset_page_btn, self._reset_all_btn):
            if hasattr(button, "setEnabled"):
                button.setEnabled(not busy)
        if busy:
            self._status_label.setText(t("settings_applying"))

    def _reset_current_page(self) -> None:
        index = self._navigation.currentRow()
        page = SETTINGS_PAGES[index if 0 <= index < len(SETTINGS_PAGES) else 0]
        self.model.reset_page(page)
        self._populate_widgets()

    def _reset_defaults(self) -> None:
        self.model.reset_all()
        self._populate_widgets()

    def _browse_dictionary(self, path: str) -> None:
        current = str(self.model.get(path, "") or "")
        filename, _selected_filter = QFileDialog.getOpenFileName(
            self,
            t("settings_choose_dictionary"),
            os.path.dirname(current) if current else "",
            t("settings_dictionary_filter"),
        )
        if filename:
            self._widgets[path].setText(filename)
            self._on_widget_changed(path)

    # -- external synchronization ---------------------------------------

    def _subscribe(self) -> None:
        if self.event_bus is not None and not self._subscribed:
            self.event_bus.subscribe(EventType.CONFIG_CHANGED, self._on_config_changed)
            self._subscribed = True

    def cleanup(self) -> None:
        if self.event_bus is not None and self._subscribed:
            self.event_bus.unsubscribe(EventType.CONFIG_CHANGED, self._on_config_changed)
            self._subscribed = False

    def _on_config_changed(self, event) -> None:
        data = getattr(event, "data", None) or {}
        if self._applying and data.get("source") == "gui":
            return
        if self.config is None:
            return
        self.model.handle_external_change(self.config.get_all())
        self._populate_widgets()

    def refresh_from_config(self) -> None:
        if self.config is not None:
            self.model.handle_external_change(self.config.get_all())
            self._populate_widgets()

    def _load_values(self) -> None:
        """Compatibility wrapper that reloads the current committed snapshot."""
        if self.config is not None:
            self.model.load(self.config.get_all())
            self._populate_widgets()

    # -- dialog overrides ------------------------------------------------

    def accept(self) -> None:
        self._commit(close_on_success=True)

    def reject(self) -> None:
        if self.config is not None:
            self.model.load(self.config.get_all())
            self._populate_widgets()
        super().reject()

    def show(self) -> None:
        if not self.model.is_dirty:
            self.refresh_from_config()
        super().show()

    # -- informational helpers ------------------------------------------

    def _platform_description(self) -> str:
        platform = getattr(self.app, "_platform", None)
        compositor = getattr(platform, "compositor", "")
        if self._session_type != "unknown":
            return f"{self._session_type} / {compositor or 'unknown'}"
        return "unknown"

    def _current_session_type(self) -> str:
        platform = getattr(self.app, "_platform", None)
        session = getattr(platform, "session_type", "")
        if isinstance(session, str):
            normalized = session.strip().lower()
            if normalized in {"x11", "wayland"}:
                return normalized

        from lswitch.platform.platform_factory import detect_session_type

        detected = detect_session_type()
        return detected if detected in {"x11", "wayland"} else "unknown"

    def _trace_override_active(self) -> bool:
        logging_controller = getattr(self.app, "logging_controller", None)
        return bool(getattr(logging_controller, "trace_override", False))
