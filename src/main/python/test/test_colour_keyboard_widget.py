from PyQt5.QtCore import Qt, QPoint, QPointF
from PyQt5.QtGui import QMouseEvent
from PyQt5.QtCore import QEvent
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication

from kle_serial import Serial as KleSerial
from protocol.key_colours import LedInfo
from widgets.colour_keyboard_widget import ColourKeyboardWidget


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
