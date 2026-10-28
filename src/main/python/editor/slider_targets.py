# SPDX-License-Identifier: GPL-2.0-or-later
import logging

from PyQt5.QtCore import QRegularExpression, QTimer
from PyQt5.QtGui import QColor, QRegularExpressionValidator
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget, QVBoxLayout, QColorDialog, QLineEdit, \
    QSpinBox, QSizePolicy, QDialog

from editor.basic_editor import BasicEditor
from protocol.slider_targets import SliderTarget, ST_MAX_CONTROL
from util import tr
from vial_device import VialKeyboard
from widgets.clickable_label import ClickableLabel

NOTE_TEXT = "Assign the \"Next slider target\" key in the Keymap tab (it's in the User tab)."

REFRESH_INTERVAL_MS = 1000
DEFAULT_CONTROL = 62
CURRENT_MARK = "▶"


def _swatch_style(colour):
    return "QLabel { background-color: %s; border: 1px solid palette(button-text); }" % QColor(*colour).name()


class TargetRow:
    """ The widgets of one target row. """

    def __init__(self, editor, idx, target, name_max, count):
        self.widget = QWidget()
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)

        self.marker = QLabel()
        self.marker.setMinimumWidth(16)
        row.addWidget(self.marker)

        self.name = QLineEdit()
        self.name.setValidator(QRegularExpressionValidator(QRegularExpression("[ -~]*"), self.name))
        self.name.editingFinished.connect(lambda: editor.on_name_edited(idx))
        row.addWidget(self.name, 1)

        row.addWidget(QLabel(tr("SliderTargets", "Control:")))
        self.control = QSpinBox()
        self.control.setRange(0, ST_MAX_CONTROL)
        self.control.valueChanged.connect(lambda value: editor.on_control_changed(idx, value))
        row.addWidget(self.control)

        self.swatch = ClickableLabel(" ")
        self.swatch.setToolTip(tr("SliderTargets", "Colour"))
        self.swatch.setMinimumWidth(32)
        self.swatch.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        self.swatch.clicked.connect(lambda: editor.on_colour_clicked(idx))
        row.addWidget(self.swatch)

        self.up = QPushButton(tr("SliderTargets", "Up"))
        self.up.setEnabled(idx > 0)
        self.up.clicked.connect(lambda: editor.move(idx, -1))
        row.addWidget(self.up)
        self.down = QPushButton(tr("SliderTargets", "Down"))
        self.down.setEnabled(idx < count - 1)
        self.down.clicked.connect(lambda: editor.move(idx, 1))
        row.addWidget(self.down)
        self.remove = QPushButton(tr("SliderTargets", "Remove"))
        self.remove.setEnabled(count > 1)
        self.remove.clicked.connect(lambda: editor.remove(idx))
        row.addWidget(self.remove)

        self.widget.setLayout(row)
        self.show_target(target, name_max)

    def show_target(self, target, name_max):
        """ Show target's values without sending them back to the keyboard. """
        self.name.setMaxLength(name_max)
        if self.name.text() != target.name:
            self.name.setText(target.name)
        self.control.blockSignals(True)
        self.control.setValue(target.control)
        self.control.blockSignals(False)
        self.colour = tuple(target.colour)
        self.swatch.setStyleSheet(_swatch_style(self.colour))

    def set_current(self, current):
        self.marker.setText(CURRENT_MARK if current else "")
        font = self.name.font()
        font.setBold(current)
        self.name.setFont(font)


class SliderTargetsEditor(BasicEditor):
    """ Edit the list of MIDI controls the numpad's slider cycles through. """

    def __init__(self):
        super().__init__()
        self.keyboard = None
        self.rows = []
        self.shown = []           # targets the rows were built from
        self.dlg_color = None
        self.dlg_row = None
        self.write_error = False  # error label shows a failed write

        self.timer = QTimer()
        self.timer.setInterval(REFRESH_INTERVAL_MS)
        self.timer.timeout.connect(self.on_timer)

        self.error_label = QLabel()
        self.error_label.setStyleSheet("QLabel { color: #d32f2f; }")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        self.addWidget(self.error_label)

        self.rows_layout = QVBoxLayout()
        self.addLayout(self.rows_layout)

        buttons = QHBoxLayout()
        self.btn_add = QPushButton(tr("SliderTargets", "Add target"))
        self.btn_add.clicked.connect(self.add)
        buttons.addWidget(self.btn_add)
        buttons.addStretch()
        self.addLayout(buttons)

        self.note = QLabel(tr("SliderTargets", NOTE_TEXT))
        self.note.setWordWrap(True)
        self.addWidget(self.note)
        self.addStretch()

    # ---- BasicEditor ----

    def valid(self):
        return isinstance(self.device, VialKeyboard) and bool(self.device.keyboard.slider_supported)

    def rebuild(self, device):
        super().rebuild(device)
        self.write_error = False
        self.error_label.hide()
        if not self.valid():
            self.keyboard = None
            self.timer.stop()
            self._clear_rows()
            return
        self.keyboard = device.keyboard
        self._build_rows()

    def activate(self):
        if self.valid():
            self.timer.start()

    def deactivate(self):
        self.timer.stop()

    # ---- rows ----

    def _clear_rows(self):
        for row in self.rows:
            # a focused name field would emit editingFinished on hide, against the new list
            row.name.blockSignals(True)
            row.control.blockSignals(True)
            self.rows_layout.removeWidget(row.widget)
            row.widget.hide()
            row.widget.deleteLater()
        self.rows = []
        self.shown = []

    def _build_rows(self):
        self._clear_rows()
        targets = list(self.keyboard.slider_targets)
        for idx, t in enumerate(targets):
            row = TargetRow(self, idx, t, self.keyboard.slider_name_max, len(targets))
            self.rows_layout.addWidget(row.widget)
            self.rows.append(row)
        self.shown = targets
        self.btn_add.setEnabled(len(targets) < self.keyboard.slider_max)
        self._mark_current()

    def _sync(self):
        """ Make the rows show the keyboard's targets, rebuilding only when the count changed. """
        targets = list(self.keyboard.slider_targets)
        if len(targets) != len(self.rows):
            self._build_rows()
            return
        for row, t in zip(self.rows, targets):
            row.show_target(t, self.keyboard.slider_name_max)
        self.shown = targets
        self.btn_add.setEnabled(len(targets) < self.keyboard.slider_max)
        self._mark_current()

    def _mark_current(self):
        for idx, row in enumerate(self.rows):
            row.set_current(idx == self.keyboard.slider_current)

    # ---- keyboard I/O ----

    def _call(self, fn, *args, write=False):
        """ Run a keyboard call; on failure show the error inline instead of crashing.
        A failed write stays shown until the next successful write; refreshes never clear it. """
        try:
            fn(*args)
        except Exception as e:
            logging.warning("slider targets: %s", e)
            self.error_label.setText(tr("SliderTargets", "Could not talk to the keyboard: {}").format(e))
            self.error_label.show()
            self.write_error = self.write_error or write
            return False
        if write or not self.write_error:
            self.error_label.hide()
            self.write_error = False
        return True

    def _write(self, targets):
        """ Send the whole list; the rows then show what the keyboard holds. """
        self._call(self.keyboard.set_slider_targets, targets, write=True)
        self._sync()

    def _reload(self):
        kb = self.keyboard
        saved = (kb.slider_supported, kb.slider_max, kb.slider_name_max, list(kb.slider_targets), kb.slider_current)
        try:
            kb.reload_slider_targets()
            if not kb.slider_supported:
                raise RuntimeError("slider targets not available")
        except Exception:
            # keep the last known state so the tab stays usable
            (kb.slider_supported, kb.slider_max, kb.slider_name_max, kb.slider_targets,
             kb.slider_current) = saved
            raise

    def on_timer(self):
        if self.keyboard is None or not self._call(self._reload):
            return
        if list(self.keyboard.slider_targets) != self.shown:
            self._sync()
        else:
            self._mark_current()

    # ---- edits ----

    def _targets(self):
        return list(self.keyboard.slider_targets)

    def on_name_edited(self, idx):
        targets = self._targets()
        name = self.rows[idx].name.text()
        if idx >= len(targets) or targets[idx].name == name:
            return
        targets[idx] = targets[idx]._replace(name=name)
        self._write(targets)

    def on_control_changed(self, idx, value):
        targets = self._targets()
        if idx >= len(targets) or targets[idx].control == value:
            return
        targets[idx] = targets[idx]._replace(control=value)
        self._write(targets)

    def on_colour_clicked(self, idx):
        self.dlg_row = idx
        self.dlg_color = QColorDialog()
        self.dlg_color.setModal(True)
        self.dlg_color.finished.connect(self.on_colour_finished)
        self.dlg_color.setCurrentColor(QColor(*self.rows[idx].colour))
        self.dlg_color.show()

    def on_colour_finished(self, result):
        color = self.dlg_color.selectedColor()
        targets = self._targets()
        if result != QDialog.Accepted or not color.isValid() or self.dlg_row >= len(targets):
            return
        targets[self.dlg_row] = targets[self.dlg_row]._replace(colour=(color.red(), color.green(), color.blue()))
        self._write(targets)

    def move(self, idx, delta):
        targets = self._targets()
        other = idx + delta
        if not 0 <= idx < len(targets) or not 0 <= other < len(targets):
            return
        targets[idx], targets[other] = targets[other], targets[idx]
        self._write(targets)

    def remove(self, idx):
        targets = self._targets()
        if len(targets) <= 1 or idx >= len(targets):
            return
        del targets[idx]
        self._write(targets)

    def add(self):
        targets = self._targets()
        if len(targets) >= self.keyboard.slider_max:
            return
        used = {t.control for t in targets}
        candidates = list(range(DEFAULT_CONTROL, ST_MAX_CONTROL + 1)) + list(range(DEFAULT_CONTROL))
        control = next((c for c in candidates if c not in used), DEFAULT_CONTROL)
        targets.append(SliderTarget(control, (255, 255, 255), "Target {}".format(len(targets) + 1)))
        self._write(targets)
