# SPDX-License-Identifier: GPL-2.0-or-later
import logging

from PyQt5.QtCore import QEvent, QObject, QRegularExpression, Qt, QTimer
from PyQt5.QtGui import QColor, QRegularExpressionValidator
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget, QVBoxLayout, QColorDialog, QLineEdit, \
    QSpinBox, QSizePolicy, QDialog

from editor.basic_editor import BasicEditor
from protocol.slider_targets import SliderTarget, ST_MAX_CONTROL
from util import tr
from vial_device import VialKeyboard
from widgets.clickable_label import ClickableLabel
from widgets.colour_keyboard_widget import ColourKeyboardWidget, LED_NO_KEY

NOTE_TEXT = "Assign the \"Next slider target\" key in the Keymap tab (it's in the User tab)."

REFRESH_INTERVAL_MS = 1000
DEFAULT_CONTROL = 62
CURRENT_MARK = "▶"


class _PressFilter(QObject):
    """ Calls back on a mouse press, letting the press through. """

    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonPress:
            self.callback()
        return False


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
        # clicking anywhere on the row previews its colour in the flash drawing
        self.press_filter = _PressFilter(lambda: editor.preview(idx))
        for w in (self.widget, self.marker, self.name, self.control, self.control.findChild(QLineEdit),
                  self.swatch):
            w.installEventFilter(self.press_filter)
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

    def __init__(self, layout_editor=None):
        super().__init__()
        self.layout_editor = layout_editor
        self.keyboard = None
        self.rows = []
        self.shown = []           # targets the rows were built from
        self.preview_idx = None   # row whose colour the flash drawing uses; None = current target
        self.stroke_mask = None   # flash mask being painted by the open stroke
        self.stroke_on = True     # whether the open stroke turns lights on or off
        self.flash_shown = None   # colours the flash drawing was last given
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
        self._build_flash()
        self.addStretch()

        if layout_editor is not None:
            layout_editor.changed.connect(self.on_layout_changed)

    def _build_flash(self):
        self.flash_section = QWidget()
        box = QVBoxLayout()
        box.setContentsMargins(0, 0, 0, 0)
        box.addWidget(QLabel(tr("SliderTargets", "Lights that flash when switching target")))
        self.flash_widget = ColourKeyboardWidget()
        self.flash_widget.stroke_painted.connect(self.on_flash_painted)
        self.flash_widget.stroke_finished.connect(self.on_flash_finished)
        box.addWidget(self.flash_widget, 0, Qt.AlignHCenter)
        buttons = QHBoxLayout()
        self.btn_flash_all = QPushButton(tr("SliderTargets", "All"))
        self.btn_flash_all.clicked.connect(lambda: self._write_flash(self._led_mask(lambda led: True)))
        self.btn_flash_none = QPushButton(tr("SliderTargets", "None"))
        self.btn_flash_none.clicked.connect(lambda: self._write_flash(0))
        self.btn_flash_edges = QPushButton(tr("SliderTargets", "Edge lights only"))
        self.btn_flash_edges.clicked.connect(
            lambda: self._write_flash(self._led_mask(lambda led: led.row == LED_NO_KEY)))
        for btn in (self.btn_flash_all, self.btn_flash_none, self.btn_flash_edges):
            buttons.addWidget(btn)
        buttons.addStretch()
        box.addLayout(buttons)
        self.flash_section.setLayout(box)
        self.flash_section.hide()
        self.addWidget(self.flash_section)

    # ---- BasicEditor ----

    def valid(self):
        return isinstance(self.device, VialKeyboard) and bool(self.device.keyboard.slider_supported)

    def rebuild(self, device):
        super().rebuild(device)
        self.write_error = False
        self.error_label.hide()
        self.preview_idx = None
        self.stroke_mask = None
        if not self.valid():
            self.keyboard = None
            self.timer.stop()
            self._clear_rows()
            self.flash_section.hide()
            return
        self.keyboard = device.keyboard
        self._build_rows()
        self.on_layout_changed()

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
        self._show_flash()

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
        self._show_flash()

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
        names = ("slider_supported", "slider_max", "slider_name_max", "slider_targets", "slider_current",
                 "slider_flash_supported", "slider_flash_mask")
        saved = {n: getattr(kb, n, None) for n in names}
        try:
            kb.reload_slider_targets()
            if not kb.slider_supported:
                raise RuntimeError("slider targets not available")
        except Exception:
            # keep the last known state so the tab stays usable
            for n, value in saved.items():
                setattr(kb, n, value)
            raise

    def on_timer(self):
        if self.keyboard is None or not self._call(self._reload):
            return
        if list(self.keyboard.slider_targets) != self.shown:
            self._sync()
        else:
            self._mark_current()
            self._show_flash()

    # ---- lights that flash when switching target ----

    def _flash_available(self):
        kb = self.keyboard
        return kb is not None and bool(getattr(kb, "slider_flash_supported", False)) and \
            bool(getattr(kb, "leds", None))

    def on_layout_changed(self):
        """ (Re)build the flash drawing; only on rebuild and layout option changes. """
        self.flash_section.setVisible(self._flash_available())
        if not self._flash_available():
            return
        choice = self.layout_editor.get_choice if self.layout_editor is not None else None
        self.flash_widget.set_keyboard(self.keyboard.keys, self.keyboard.leds, choice)
        self.flash_shown = None
        self._show_flash()

    def _led_mask(self, wanted):
        return sum(1 << i for i, led in enumerate(self.keyboard.leds[:32]) if wanted(led))

    def _show_flash(self):
        """ Draw the flash mask (the open stroke's, else the keyboard's) in the previewed colour. """
        if not self._flash_available():
            return
        targets = self.keyboard.slider_targets
        idx = self.preview_idx
        if idx is None or idx >= len(targets):
            idx = min(self.keyboard.slider_current, len(targets) - 1)
        colour = tuple(targets[idx].colour) if targets else None
        mask = self.keyboard.slider_flash_mask if self.stroke_mask is None else self.stroke_mask
        colours = [colour if i < 32 and mask & (1 << i) else None for i in range(len(self.keyboard.leds))]
        if colours != self.flash_shown:
            self.flash_shown = colours
            self.flash_widget.set_colours(colours)

    def preview(self, idx):
        self.preview_idx = idx
        self._show_flash()

    def on_flash_painted(self, leds):
        if not self._flash_available():
            return
        leds = [led for led in leds if led < 32]
        if not leds:
            return
        if self.stroke_mask is None:
            self.stroke_mask = self.keyboard.slider_flash_mask
            # the stroke's first light decides whether the whole stroke turns lights on or off
            self.stroke_on = not self.stroke_mask & (1 << leds[0])
        for led in leds:
            if self.stroke_on:
                self.stroke_mask |= 1 << led
            else:
                self.stroke_mask &= ~(1 << led)
        self._show_flash()

    def on_flash_finished(self):
        mask, self.stroke_mask = self.stroke_mask, None
        if mask is not None:
            self._write_flash(mask)

    def _write_flash(self, mask):
        """ Send the mask; the drawing then shows what the keyboard holds. """
        if self._flash_available():
            self._call(self.keyboard.set_slider_flash_mask, mask, write=True)
            self._show_flash()

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
