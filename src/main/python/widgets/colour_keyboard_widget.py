import math

from PyQt5.QtCore import Qt, QSize, QPointF, QRectF, pyqtSignal
from PyQt5.QtGui import QPainter, QColor, QBrush, QPen, QPalette
from PyQt5.QtWidgets import QWidget, QApplication

from constants import KEYBOARD_WIDGET_PADDING
from widgets.keyboard_widget import KeyWidget

LED_NO_KEY = 0xFF
LED_X_MAX = 224
LED_Y_MAX = 64
DOT_HIT_RADIUS = 12
DOT_RADIUS = 7


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
        self._last_pos = QPointF()
        self._step = 4.0         # hit-test spacing along a drag, about a quarter key width

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

        # LEDs that aren't under a key (side strips, underglow) are drawn around the keys, half a key away;
        # only the sides that have such LEDs get the extra room
        edge = [led for led in self.leds if led.row == LED_NO_KEY]
        has_sides = any(led.x in (0, LED_X_MAX) for led in edge)
        has_ends = any(led.x not in (0, LED_X_MAX) and led.y in (0, LED_Y_MAX) for led in edge)
        half_key = min(w.polygon.boundingRect().width() for w in widgets) / 2 if widgets else 0
        margin_x = half_key + DOT_RADIUS if has_sides else 0
        margin_y = half_key + DOT_RADIUS if has_ends else (DOT_RADIUS if has_sides else 0)

        if widgets:
            left = min(w.polygon.boundingRect().left() for w in widgets)
            top = min(w.polygon.boundingRect().top() for w in widgets)
        else:
            left = top = 0
        for w in widgets:
            w.update_position(scale, w.shift_x - left + self.padding + margin_x,
                              w.shift_y - top + self.padding + margin_y)

        self._key_widgets = widgets
        self._key_led = [by_pos.get((w.desc.row, w.desc.col)) for w in widgets]
        if widgets:
            self._step = max(1.0, min(w.polygon.boundingRect().width() for w in widgets) / 4)

        if widgets:
            box = widgets[0].polygon.boundingRect()
            for w in widgets[1:]:
                box = box.united(w.polygon.boundingRect())
        else:
            box = QRectF(0, 0, 0, 0)
        self._box = box
        # dots sit half a key from the keys; DOT_RADIUS more of canvas keeps them off the widget's edge
        dot_box = box.adjusted(-half_key, -half_key, half_key, half_key)
        canvas = box.adjusted(-margin_x, -margin_y, margin_x, margin_y)
        self._dots = []
        for i, led in enumerate(self.leds):
            if led.row == LED_NO_KEY:
                x, y = min(led.x, LED_X_MAX), min(led.y, LED_Y_MAX)
                px = box.left() + box.width() * x / LED_X_MAX
                py = box.top() + box.height() * y / LED_Y_MAX
                # LEDs on the outer edge sit half a key outside the keys: side strips move out
                # sideways only, so they still span the keys' height; top/bottom strips move vertically
                side = x in (0, LED_X_MAX)
                if x == 0:
                    px = dot_box.left()
                elif x == LED_X_MAX:
                    px = dot_box.right()
                if not side and y == 0:
                    py = dot_box.top()
                elif not side and y == LED_Y_MAX:
                    py = dot_box.bottom()
                self._dots.append((i, QPointF(px, py)))

        self._size = QSize(round(canvas.right() + self.padding), round(canvas.bottom() + self.padding))
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
            qp.drawEllipse(point, DOT_RADIUS, DOT_RADIUS)
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

    def _paint_to(self, end):
        """ Paint every key along the segment from the last position, so fast drags skip nothing. """
        start = self._last_pos
        dx, dy = end.x() - start.x(), end.y() - start.y()
        steps = max(1, int(math.ceil(math.hypot(dx, dy) / self._step)))
        for i in range(1, steps + 1):
            self._paint_at(QPointF(start.x() + dx * i / steps, start.y() + dy * i / steps))
        self._last_pos = end

    def _finish_stroke(self):
        self._stroking = False
        self.stroke_finished.emit()

    def mousePressEvent(self, ev):
        if ev.button() != Qt.LeftButton:
            return
        if self._stroking:
            # the previous release was lost
            self._finish_stroke()
        self._stroking = True
        self._stroke_seen = set()
        self._last_pos = QPointF(ev.pos())
        self._paint_at(self._last_pos)

    def mouseMoveEvent(self, ev):
        if not self._stroking:
            return
        if not ev.buttons() & Qt.LeftButton:
            # the release went elsewhere (focus stolen, released outside the canvas)
            self._finish_stroke()
            return
        self._paint_to(QPointF(ev.pos()))

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.LeftButton and self._stroking:
            self._finish_stroke()
