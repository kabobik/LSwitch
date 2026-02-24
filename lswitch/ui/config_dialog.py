"""ConfigDialog — settings window."""

from __future__ import annotations

import time

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QCheckBox, QSpinBox, QDoubleSpinBox,
    QPushButton, QDialogButtonBox, QLabel,
)
from PyQt5.QtCore import Qt

from lswitch.config import DEFAULT_CONFIG
from lswitch.core.events import Event, EventType


class ConfigDialog(QDialog):
    """Settings dialog opened from the tray menu.

    Displays all user-configurable options and saves via ConfigManager.
    """

    def __init__(self, config=None, event_bus=None, parent=None):
        super().__init__(parent)
        self.config = config
        self.event_bus = event_bus

        self.setWindowTitle("LSwitch Settings")
        self.setMinimumWidth(360)

        self._build_ui()
        self._load_values()

    # -- UI construction ---------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        form = QFormLayout()

        # auto_switch
        self._auto_switch_cb = QCheckBox()
        form.addRow("Auto switch:", self._auto_switch_cb)

        # auto_switch_threshold
        self._threshold_spin = QSpinBox()
        self._threshold_spin.setRange(0, 100)
        self._threshold_spin.setSingleStep(1)
        form.addRow("Auto switch threshold:", self._threshold_spin)

        # user_dict_enabled
        self._user_dict_cb = QCheckBox()
        form.addRow("User dictionary:", self._user_dict_cb)

        # double_click_timeout
        self._dct_spin = QDoubleSpinBox()
        self._dct_spin.setRange(0.05, 10.0)
        self._dct_spin.setSingleStep(0.05)
        self._dct_spin.setDecimals(2)
        form.addRow("Double click timeout:", self._dct_spin)

        layout.addLayout(form)

        # Buttons
        btn_layout = QHBoxLayout()

        reset_btn = QPushButton("Reset defaults")
        reset_btn.clicked.connect(self._reset_defaults)
        btn_layout.addWidget(reset_btn)

        btn_layout.addStretch()

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        btn_layout.addWidget(button_box)

        layout.addLayout(btn_layout)

    # -- value management --------------------------------------------------

    def _load_values(self) -> None:
        """Load current config values into widgets."""
        cfg = self.config
        if cfg is None:
            return
        self._auto_switch_cb.setChecked(cfg.get("auto_switch", False))
        self._threshold_spin.setValue(int(cfg.get("auto_switch_threshold", 10)))
        self._user_dict_cb.setChecked(cfg.get("user_dict_enabled", False))
        self._dct_spin.setValue(float(cfg.get("double_click_timeout", 0.3)))

    def _apply_values(self) -> None:
        """Write widget values back to ConfigManager and save."""
        if self.config is None:
            return
        self.config.set("auto_switch", self._auto_switch_cb.isChecked())
        self.config.set("auto_switch_threshold", self._threshold_spin.value())
        self.config.set("user_dict_enabled", self._user_dict_cb.isChecked())
        self.config.set("double_click_timeout", self._dct_spin.value())
        self.config.save()

    def _reset_defaults(self) -> None:
        """Reset widgets to DEFAULT_CONFIG values."""
        self._auto_switch_cb.setChecked(DEFAULT_CONFIG["auto_switch"])
        self._threshold_spin.setValue(DEFAULT_CONFIG["auto_switch_threshold"])
        self._user_dict_cb.setChecked(DEFAULT_CONFIG["user_dict_enabled"])
        self._dct_spin.setValue(DEFAULT_CONFIG["double_click_timeout"])

    # -- QDialog overrides -------------------------------------------------

    def accept(self) -> None:
        """Save config and publish CONFIG_CHANGED event."""
        self._apply_values()
        if self.event_bus is not None:
            self.event_bus.publish(
                Event(type=EventType.CONFIG_CHANGED, data=None, timestamp=time.time())
            )
        super().accept()

    def reject(self) -> None:
        """Close without saving."""
        super().reject()

    # -- convenience -------------------------------------------------------

    def show(self) -> None:
        """Show the dialog (non-modal)."""
        super().show()
