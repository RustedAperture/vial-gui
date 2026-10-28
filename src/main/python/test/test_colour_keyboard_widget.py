from PyQt5.QtCore import Qt, QPoint, QPointF
from PyQt5.QtGui import QMouseEvent
from PyQt5.QtCore import QEvent
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication

from kle_serial import Serial as KleSerial
from protocol.key_colours import LedInfo
from widgets.colour_keyboard_widget import ColourKeyboardWidget, DOT_RADIUS


def make_keys():
    keys = []
    for key in KleSerial().deserialize([["0,0", "0,1", "0,2"]]).keys:
        row, col = key.labels[0].split(",")
        key.row, key.col = int(row), int(col)
        key.encoder_idx = key.encoder_dir = None
        key.layout_index = key.layout_option = -1
        keys.append(key)
    return keys


def make_widget(qtbot):
    w = ColourKeyboardWidget()
    qtbot.addWidget(w)
    w.set_keyboard(make_keys(), [LedInfo(i * 20, 0, 4, 0, i) for i in range(3)])
    w.set_colours([(255, 0, 0), None, (0, 0, 255)])
    w.resize(w.sizeHint())
    w.show()
    return w


def move(w, pos):
    QApplication.sendEvent(w, QMouseEvent(QEvent.MouseMove, QPointF(pos), Qt.NoButton, Qt.LeftButton, Qt.NoModifier))


def centre(w, i):
    return w._key_widgets[i].polygon.boundingRect().center().toPoint()


def test_stroke_paints_each_led_once(qtbot):
    w = make_widget(qtbot)
    painted, finished = [], []
    w.stroke_painted.connect(painted.extend)
    w.stroke_finished.connect(lambda: finished.append(1))

    QTest.mousePress(w, Qt.LeftButton, Qt.NoModifier, centre(w, 0))
    for i in (1, 2, 1, 0):
        move(w, centre(w, i))
    QTest.mouseRelease(w, Qt.LeftButton, Qt.NoModifier, QPoint(-50, -50))
    assert painted == [0, 1, 2]
    assert finished == [1]

    del painted[:]
    QTest.mousePress(w, Qt.LeftButton, Qt.NoModifier, centre(w, 0))
    QTest.mouseRelease(w, Qt.LeftButton, Qt.NoModifier, centre(w, 0))
    assert painted == [0]
    assert finished == [1, 1]


def test_move_without_press_paints_nothing(qtbot):
    w = make_widget(qtbot)
    painted = []
    w.stroke_painted.connect(painted.extend)
    move(w, centre(w, 1))
    assert painted == []


def test_renders(qtbot):
    w = make_widget(qtbot)
    assert not w.grab().isNull()


def test_layout_choice_selects_option(qtbot):
    keys = []
    kle = [["0,0\n\n\n0,0"], [{"x": 3}, "0,1\n\n\n0,1"]]
    for key in KleSerial().deserialize(kle).keys:
        row, col = key.labels[0].split(",")
        key.row, key.col = int(row), int(col)
        idx, opt = key.labels[8].split(",")
        key.layout_index, key.layout_option = int(idx), int(opt)
        keys.append(key)
    leds = [LedInfo(0, 0, 4, 0, 0), LedInfo(10, 0, 4, 0, 1)]
    for choice, expected in ((0, [0]), (1, [1])):
        w = ColourKeyboardWidget()
        qtbot.addWidget(w)
        w.set_keyboard(keys, leds, lambda idx, c=choice: c)
        w.resize(w.sizeHint())
        painted = []
        w.stroke_painted.connect(painted.extend)
        assert len(w._key_widgets) == 1
        # the chosen alternative is shifted to the same place
        assert w._key_widgets[0].polygon.boundingRect().topLeft().x() == w.padding
        pos = w._key_widgets[0].polygon.boundingRect().center().toPoint()
        QTest.mousePress(w, Qt.LeftButton, Qt.NoModifier, pos)
        QTest.mouseRelease(w, Qt.LeftButton, Qt.NoModifier, pos)
        assert painted == expected


def test_edge_led_dot_paintable(qtbot):
    w = ColourKeyboardWidget()
    qtbot.addWidget(w)
    leds = [LedInfo(i * 20, 0, 4, 0, i) for i in range(3)] + [LedInfo(112, 32, 2, 0xFF, 0xFF)]
    w.set_keyboard(make_keys(), leds)
    w.resize(w.sizeHint())
    painted = []
    w.stroke_painted.connect(painted.extend)
    pos = w._dots[0][1].toPoint()
    QTest.mousePress(w, Qt.LeftButton, Qt.NoModifier, pos)
    move(w, pos + QPoint(1, 1))
    QTest.mouseRelease(w, Qt.LeftButton, Qt.NoModifier, pos)
    assert painted == [3]


def test_edge_led_dots_sit_outside_the_keys(qtbot):
    # side strips like the GMMK Numpad's: x = 0 (left) and x = 224 (right), full height
    w = ColourKeyboardWidget()
    qtbot.addWidget(w)
    leds = [LedInfo(i * 20, 0, 4, 0, i) for i in range(3)]
    leds += [LedInfo(0, y, 2, 0xFF, 0xFF) for y in (0, 32, 64)]
    leds += [LedInfo(224, y, 2, 0xFF, 0xFF) for y in (0, 32, 64)]
    w.set_keyboard(make_keys(), leds)
    keys = w._key_widgets[0].polygon.boundingRect()
    for k in w._key_widgets[1:]:
        keys = keys.united(k.polygon.boundingRect())
    gap = DOT_RADIUS * 2
    dots = dict(w._dots)
    for led in (3, 4, 5):
        assert dots[led].x() <= keys.left() - gap
    for led in (6, 7, 8):
        assert dots[led].x() >= keys.right() + gap
    # side strips span the keys' height rather than sticking out above and below
    for led in (3, 4, 5, 6, 7, 8):
        assert keys.top() <= dots[led].y() <= keys.bottom()
    size = w.sizeHint()
    for p in dots.values():
        assert DOT_RADIUS <= p.x() <= size.width() - DOT_RADIUS
        assert DOT_RADIUS <= p.y() <= size.height() - DOT_RADIUS


def test_no_edge_leds_no_extra_margin(qtbot):
    w = make_widget(qtbot)
    keys = w._key_widgets[0].polygon.boundingRect()
    assert keys.left() == w.padding


def test_fast_drag_paints_every_key_crossed(qtbot):
    w = make_widget(qtbot)
    painted = []
    w.stroke_painted.connect(painted.extend)
    QTest.mousePress(w, Qt.LeftButton, Qt.NoModifier, centre(w, 0))
    # one move event that jumps straight across key 1
    move(w, centre(w, 2))
    QTest.mouseRelease(w, Qt.LeftButton, Qt.NoModifier, centre(w, 2))
    assert painted == [0, 1, 2]


def test_move_without_button_finishes_lost_stroke(qtbot):
    w = make_widget(qtbot)
    painted, finished = [], []
    w.stroke_painted.connect(painted.extend)
    w.stroke_finished.connect(lambda: finished.append(1))
    QTest.mousePress(w, Qt.LeftButton, Qt.NoModifier, centre(w, 0))
    # the release went elsewhere; the next move has no button held
    QApplication.sendEvent(w, QMouseEvent(QEvent.MouseMove, QPointF(centre(w, 1)), Qt.NoButton, Qt.NoButton,
                                          Qt.NoModifier))
    assert painted == [0]
    assert finished == [1]
    move(w, centre(w, 2))
    assert painted == [0]


def test_press_finishes_lost_stroke_first(qtbot):
    w = make_widget(qtbot)
    events = []
    w.stroke_painted.connect(lambda leds: events.append(("paint", leds)))
    w.stroke_finished.connect(lambda: events.append("finish"))
    QTest.mousePress(w, Qt.LeftButton, Qt.NoModifier, centre(w, 0))
    # release lost, then a new press
    QTest.mousePress(w, Qt.LeftButton, Qt.NoModifier, centre(w, 1))
    QTest.mouseRelease(w, Qt.LeftButton, Qt.NoModifier, centre(w, 1))
    assert events == [("paint", [0]), "finish", ("paint", [1]), "finish"]
