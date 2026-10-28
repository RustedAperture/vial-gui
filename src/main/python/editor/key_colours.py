# SPDX-License-Identifier: GPL-2.0-or-later
import logging

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget, QButtonGroup, QColorDialog, QSizePolicy

from editor.basic_editor import BasicEditor
from editor.key_colours_history import ColourHistory
from util import tr
from vial_device import VialKeyboard
from widgets.clickable_label import ClickableLabel
from widgets.colour_keyboard_widget import ColourKeyboardWidget

SWATCHES = [
    ("Orange", "#ff4200"),
    ("Pink", "#fa59ff"),
    ("Purple", "#8a2be2"),
    ("Ice blue", "#7fd4ff"),
    ("Green", "#00c853"),
    ("Red", "#ff1744"),
    ("Yellow", "#ffd600"),
    ("White", "#ffffff"),
    ("Off", "#000000"),
]

BANNER_TEXT = "Your key colours were reset, usually by a firmware update. " \
              "Load your saved layout file to bring them back."

TOOLS = [("brush", "Brush"), ("fill", "Fill"), ("eraser", "Eraser")]

PREVIEW_INTERVAL_MS = 1000


def _swatch_style(name):
    return "QLabel { background-color: %s; border: 1px solid palette(button-text); }" % name


def _rgb(name):
    c = QColor(name)
    return (c.red(), c.green(), c.blue())


class KeyColoursEditor(BasicEditor):
    """ Paint per-layer key colours: pick a colour, then brush it onto keys. """

    save_requested = pyqtSignal()
    load_requested = pyqtSignal()

    def __init__(self, layout_editor):
        super().__init__()
        self.layout_editor = layout_editor
        self.keyboard = None
        self.layer = 0
        self.tool = "brush"
        self.brush_colour = _rgb(SWATCHES[0][1])
        self.history = ColourHistory()
        self.active = False
        self.in_stroke = False
        self.dlg_color = None
        self.write_error = False   # error label shows a failed write

        self.preview_timer = QTimer()
        self.preview_timer.setInterval(PREVIEW_INTERVAL_MS)
        self.preview_timer.timeout.connect(self.on_preview_timer)

        self._build_banner()

        self.error_label = QLabel()
        self.error_label.setStyleSheet("QLabel { color: #d32f2f; }")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        self.addWidget(self.error_label)

        self.layout_layers = QHBoxLayout()
        self.layer_group = QButtonGroup()
        self.layer_group.setExclusive(True)
        self.layer_buttons = []
        self.addLayout(self.layout_layers)

        self._build_tools()

        self.addStretch()
        self.widget = ColourKeyboardWidget()
        self.widget.stroke_painted.connect(self.on_stroke_painted)
        self.widget.stroke_finished.connect(self.on_stroke_finished)
        self.addWidget(self.widget)
        self.setAlignment(self.widget, Qt.AlignHCenter)
        self.addStretch()

        self._build_files()

        layout_editor.changed.connect(self.on_layout_changed)

    # ---- UI construction ----

    def _build_banner(self):
        self.banner = QWidget()
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        self.banner_label = QLabel(tr("KeyColours", BANNER_TEXT))
        self.banner_label.setWordWrap(True)
        row.addWidget(self.banner_label, 1)
        self.btn_banner_load = QPushButton(tr("KeyColours", "Load"))
        self.btn_banner_load.clicked.connect(self.load_requested.emit)
        row.addWidget(self.btn_banner_load)
        self.banner.setLayout(row)
        self.banner.hide()
        self.addWidget(self.banner)

    def _build_tools(self):
        row = QHBoxLayout()
        self.tool_group = QButtonGroup()
        self.tool_group.setExclusive(True)
        self.tool_buttons = {}
        for name, label in TOOLS:
            btn = QPushButton(tr("KeyColours", label))
            btn.setCheckable(True)
            btn.setFocusPolicy(Qt.NoFocus)
            btn.clicked.connect(lambda state, n=name: self.set_tool(n))
            self.tool_group.addButton(btn)
            self.tool_buttons[name] = btn
            row.addWidget(btn)
        self.tool_buttons[self.tool].setChecked(True)

        row.addSpacing(16)
        row.addWidget(QLabel(tr("KeyColours", "Colour:")))
        self.current_swatch = QLabel(" ")
        self.current_swatch.setMinimumWidth(32)
        row.addWidget(self.current_swatch)

        for name, value in SWATCHES:
            sw = ClickableLabel(" ")
            sw.setToolTip(tr("KeyColours", name))
            sw.setMinimumWidth(24)
            sw.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
            sw.setStyleSheet(_swatch_style(value))
            sw.clicked.connect(lambda v=value: self.set_brush_colour(_rgb(v)))
            row.addWidget(sw)

        btn_any = QPushButton(tr("KeyColours", "Any colour"))
        btn_any.clicked.connect(self.on_any_colour)
        row.addWidget(btn_any)

        row.addStretch()
        self.btn_undo = QPushButton(tr("KeyColours", "Undo"))
        self.btn_undo.clicked.connect(self.on_undo)
        self.btn_undo.setEnabled(False)
        row.addWidget(self.btn_undo)
        self.addLayout(row)
        self._show_brush_colour()

    def _build_files(self):
        row = QHBoxLayout()
        row.addStretch()
        self.btn_save = QPushButton(tr("KeyColours", "Save backup…"))
        self.btn_save.clicked.connect(self.save_requested.emit)
        row.addWidget(self.btn_save)
        self.btn_load = QPushButton(tr("KeyColours", "Load backup…"))
        self.btn_load.clicked.connect(self.load_requested.emit)
        row.addWidget(self.btn_load)
        self.addLayout(row)

    def _rebuild_layer_buttons(self):
        for btn in self.layer_buttons:
            self.layer_group.removeButton(btn)
            btn.hide()
            btn.deleteLater()
        self.layer_buttons = []
        for x in range(self.keyboard.key_colours_layers):
            btn = QPushButton(tr("KeyColours", "Layer {}").format(x))
            btn.setCheckable(True)
            btn.setFocusPolicy(Qt.NoFocus)
            btn.clicked.connect(lambda state, idx=x: self.set_layer(idx))
            self.layer_group.addButton(btn)
            self.layout_layers.addWidget(btn)
            self.layer_buttons.append(btn)

    # ---- BasicEditor ----

    def valid(self):
        return isinstance(self.device, VialKeyboard) and bool(self.device.keyboard.key_colours_supported)

    def rebuild(self, device):
        super().rebuild(device)
        self.history = ColourHistory()
        self.in_stroke = False
        self.write_error = False
        self.error_label.hide()
        if not self.valid():
            self.keyboard = None
            self.preview_timer.stop()
            return
        self.keyboard = device.keyboard
        if self.layer >= self.keyboard.key_colours_layers:
            self.layer = 0
        self._rebuild_layer_buttons()
        self.on_layout_changed()
        self.set_layer(self.layer)

    def activate(self):
        self.active = True
        if self.valid():
            self._send_preview()
            self.preview_timer.start()

    def deactivate(self):
        self.active = False
        self.preview_timer.stop()
        if self.valid():
            self._call(self.keyboard.set_key_colours_preview, None)

    # ---- state ----

    def on_layout_changed(self):
        if self.keyboard is None:
            return
        self.widget.set_keyboard(self.keyboard.keys, self.keyboard.leds, self.layout_editor.get_choice)
        self.refresh()

    def set_layer(self, layer):
        self.layer = layer
        if layer < len(self.layer_buttons):
            self.layer_buttons[layer].setChecked(True)
        self.refresh()
        if self.active:
            self._send_preview()

    def set_tool(self, tool):
        self.tool = tool
        self.tool_buttons[tool].setChecked(True)

    def set_brush_colour(self, colour):
        self.brush_colour = tuple(colour)
        if self.tool == "eraser":
            self.set_tool("brush")
        self._show_brush_colour()

    def _show_brush_colour(self):
        self.current_swatch.setStyleSheet(_swatch_style(QColor(*self.brush_colour).name()))

    def refresh(self):
        self.btn_undo.setEnabled(self.history.can_undo())
        if self.keyboard is None:
            return
        self.widget.set_colours(self.keyboard.key_colours[self.layer])
        self.banner.setVisible(not self.keyboard.key_colours_initialised)

    # ---- keyboard I/O ----

    def _call(self, fn, *args, write=False):
        """ Run a keyboard call; on failure show the error inline instead of crashing.
        A failed write stays shown until the next successful write; previews never clear it. """
        try:
            fn(*args)
        except Exception as e:
            logging.warning("key colours: %s", e)
            self.error_label.setText(tr("KeyColours", "Could not talk to the keyboard: {}").format(e))
            self.error_label.show()
            self.write_error = self.write_error or write
            return False
        if write or not self.write_error:
            self.error_label.hide()
            self.write_error = False
        return True

    def _send_preview(self):
        self._call(self.keyboard.set_key_colours_preview, self.layer)

    def on_preview_timer(self):
        if self.active and self.valid():
            self._send_preview()

    def _apply(self, leds):
        """ Paint leds on the current layer with the current tool, as part of the open stroke. """
        new = None if self.tool == "eraser" else self.brush_colour
        row = self.keyboard.key_colours[self.layer]
        changes = {}
        for led in leds:
            old = row[led]
            if old != new:
                self.history.record(led, old, new)
                changes[led] = new
        if changes:
            self._call(self.keyboard.set_key_colours, self.layer, changes, write=True)
        self.refresh()

    # ---- painting ----

    def on_stroke_painted(self, leds):
        if self.keyboard is None:
            return
        if self.tool == "fill":
            if self.in_stroke:
                return
            leds = range(len(self.keyboard.key_colours[self.layer]))
        if not self.in_stroke:
            self.history.begin_stroke(self.layer)
            self.in_stroke = True
        self._apply(leds)

    def on_stroke_finished(self):
        if self.in_stroke:
            self.history.end_stroke()
            self.in_stroke = False
        self.refresh()

    def on_undo(self):
        if self.keyboard is None or self.in_stroke:
            return
        entry = self.history.undo()
        if entry is None:
            return
        layer, olds = entry
        if not self._call(self.keyboard.set_key_colours, layer, olds, write=True):
            # keep it so the user can retry once the keyboard answers again
            self.history.stack.append(entry)
        self.set_layer(layer)

    def on_any_colour(self):
        self.dlg_color = QColorDialog()
        self.dlg_color.setModal(True)
        self.dlg_color.finished.connect(self.on_any_colour_finished)
        self.dlg_color.setCurrentColor(QColor(*self.brush_colour))
        self.dlg_color.show()

    def on_any_colour_finished(self):
        color = self.dlg_color.selectedColor()
        if color.isValid():
            self.set_brush_colour((color.red(), color.green(), color.blue()))
