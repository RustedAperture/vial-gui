from PyQt5.QtCore import Qt, QSize, QPointF, QRectF, pyqtSignal
from PyQt5.QtGui import QPainter, QColor, QBrush, QPen, QPalette
from PyQt5.QtWidgets import QWidget, QApplication

from constants import KEYBOARD_WIDGET_PADDING
from widgets.keyboard_widget import KeyWidget

LED_NO_KEY = 0xFF
LED_X_MAX = 224
LED_Y_MAX = 64
DOT_HIT_RADIUS = 8


class ColourKeyboardWidget(QWidget):
    """ Keyboard drawn with each key filled by its LED colour; click/drag to paint. """

    stroke_painted = pyqtSignal(list)
    stroke_finished = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setMouseTracking(True)
        self.padding = KEYBOARD_WIDGET_PADDING
        self.keys = []
        self.leds = []
        self.colours = []
        self._key_widgets = []
        self._key_led = []       # LED index per key widget, or None
        self._dots = []          # (led index, QPointF)
        self._size = QSize(0, 0)
        self.layout_choice = lambda idx: 0
        self._stroking = False
        self._stroke_seen = set()

    def set_keyboard(self, keys, leds, layout_choice=None):
        self.layout_choice = layout_choice or (lambda idx: 0)
        self.keys = list(keys)
        self.leds = list(leds)
        if len(self.colours) != len(self.leds):
            self.colours = [None] * len(self.leds)
        self._build()

    def set_colours(self, colours):
        self.colours = list(colours)
        self.update()

    def _build(self):
        scale = self.fontMetrics().height()
        by_pos = {}
        for i, led in enumerate(self.leds):
            if led.row != LED_NO_KEY:
                by_pos.setdefault((led.row, led.col), i)

        candidates = []
        for key in self.keys:
            if key.decal or key.row is None:
                continue
            candidates.append(KeyWidget(key, scale))

        # top-left of every layout option, so a chosen option lands where option 0 is
        opt_x, opt_y = {}, {}
        for w in candidates:
            if w.desc.layout_index != -1:
                k = (w.desc.layout_index, w.desc.layout_option)
                r = w.polygon.boundingRect()
                opt_x[k] = min(opt_x.get(k, 1e6), r.left())
                opt_y[k] = min(opt_y.get(k, 1e6), r.top())

        widgets = []
        for w in candidates:
            idx, opt = w.desc.layout_index, w.desc.layout_option
            if idx == -1:
                widgets.append(w)
            elif opt == self.layout_choice(idx):
                sx = opt_x[(idx, opt)] - opt_x.get((idx, 0), opt_x[(idx, opt)])
                sy = opt_y[(idx, opt)] - opt_y.get((idx, 0), opt_y[(idx, opt)])
                w.update_position(scale, -sx, -sy)
                widgets.append(w)

        if widgets:
            left = min(w.polygon.boundingRect().left() for w in widgets)
            top = min(w.polygon.boundingRect().top() for w in widgets)
        else:
            left = top = 0
        for w in widgets:
            w.update_position(scale, w.shift_x - left + self.padding, w.shift_y - top + self.padding)

        self._key_widgets = widgets
        self._key_led = [by_pos.get((w.desc.row, w.desc.col)) for w in widgets]

        if widgets:
            box = widgets[0].polygon.boundingRect()
            for w in widgets[1:]:
                box = box.united(w.polygon.boundingRect())
        else:
            box = QRectF(0, 0, 0, 0)
        self._box = box
        self._dots = []
        for i, led in enumerate(self.leds):
            if led.row == LED_NO_KEY:
                px = box.left() + box.width() * min(led.x, LED_X_MAX) / LED_X_MAX
                py = box.top() + box.height() * min(led.y, LED_Y_MAX) / LED_Y_MAX
                self._dots.append((i, QPointF(px, py)))

        self._size = QSize(round(box.right() + self.padding), round(box.bottom() + self.padding))
        self.updateGeometry()
        self.update()

    def sizeHint(self):
        return self._size

    def minimumSizeHint(self):
        return self._size

    def _colour(self, led):
        if led is None or led >= len(self.colours):
            return None
        return self.colours[led]

    def paintEvent(self, event):
        qp = QPainter(self)
        qp.setRenderHint(QPainter.Antialiasing)
        pal = QApplication.palette()
        outline = QPen(pal.color(QPalette.ButtonText))
        for widget, led in zip(self._key_widgets, self._key_led):
            qp.save()
            qp.translate(widget.shift_x, widget.shift_y)
            qp.translate(widget.rotation_x, widget.rotation_y)
            qp.rotate(widget.rotation_angle)
            qp.translate(-widget.rotation_x, -widget.rotation_y)
            path = widget.background_draw_path
            if led is None:
                qp.setPen(Qt.NoPen)
                qp.setBrush(QBrush(pal.color(QPalette.Button), Qt.SolidPattern))
                qp.setOpacity(0.35)
                qp.drawPath(path)
                qp.setOpacity(1)
            else:
                colour = self._colour(led)
                qp.setPen(outline)
                if colour is None:
                    qp.setBrush(QBrush(pal.color(QPalette.ButtonText), Qt.BDiagPattern))
                else:
                    qp.setBrush(QBrush(QColor(*colour), Qt.SolidPattern))
                qp.drawPath(path)
            qp.restore()

        for led, point in self._dots:
            colour = self._colour(led)
            qp.setPen(outline)
            if colour is None:
                qp.setBrush(QBrush(pal.color(QPalette.ButtonText), Qt.BDiagPattern))
            else:
                qp.setBrush(QBrush(QColor(*colour), Qt.SolidPattern))
            qp.drawEllipse(point, 4, 4)
        qp.end()

    def _led_at(self, pos):
        # dots are drawn on top of keys, so they win
        p = QPointF(pos)
        for led, point in self._dots:
            if (p - point).manhattanLength() <= DOT_HIT_RADIUS * 1.5:
                return led
        for widget, led in zip(self._key_widgets, self._key_led):
            if led is not None and widget.polygon.containsPoint(QPointF(pos), Qt.OddEvenFill):
                return led
        return None

    def _paint_at(self, pos):
        led = self._led_at(pos)
        if led is not None and led not in self._stroke_seen:
            self._stroke_seen.add(led)
            self.stroke_painted.emit([led])

    def mousePressEvent(self, ev):
        if ev.button() != Qt.LeftButton:
            return
        self._stroking = True
        self._stroke_seen = set()
        self._paint_at(ev.pos())

    def mouseMoveEvent(self, ev):
        if self._stroking:
            self._paint_at(ev.pos())

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.LeftButton and self._stroking:
            self._stroking = False
            self.stroke_finished.emit()
