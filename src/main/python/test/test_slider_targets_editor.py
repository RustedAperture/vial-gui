from PyQt5.QtCore import QObject, Qt, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QLineEdit

from editor.slider_targets import SliderTargetsEditor, NOTE_TEXT
from protocol.key_colours import LedInfo
from protocol.slider_targets import SliderTarget
from test.test_key_colours_editor import make_keys
from vial_device import VialKeyboard
from widgets.editor_container import EditorContainer

WHITE = (255, 255, 255)


class FakeKeyboard:

    def __init__(self, supported=True, targets=None, current=0, maximum=8):
        self.slider_supported = supported
        self.slider_max = maximum
        self.slider_name_max = 12
        self.slider_targets = list(targets or [SliderTarget(62, WHITE, "Slider")])
        self.slider_current = current
        self.calls = []
        self.fail = False
        self.next_current = None   # what the next reload reports

    def set_slider_targets(self, targets):
        targets = [SliderTarget(*t) for t in targets]
        self.calls.append(("set", targets))
        if self.fail:
            raise RuntimeError("boom")
        for t in targets:
            if len(t.name) > self.slider_name_max or any(ord(ch) > 127 for ch in t.name):
                raise ValueError("bad slider name")
        self.slider_targets = targets
        if self.slider_current >= len(targets):
            self.slider_current = 0

    def reload_slider_targets(self):
        self.calls.append(("reload",))
        saved = list(self.slider_targets)
        self.slider_supported = False
        self.slider_targets = []
        if self.fail:
            raise RuntimeError("boom")
        self.slider_targets = saved
        self.slider_supported = True
        if self.next_current is not None:
            self.slider_current = self.next_current


def make_device(kb):
    dev = VialKeyboard.__new__(VialKeyboard)
    dev.keyboard = kb
    return dev


all_containers = []


def make_editor(qtbot, kb=None):
    kb = kb or FakeKeyboard()
    editor = SliderTargetsEditor()
    container = EditorContainer(editor)
    qtbot.addWidget(container)
    all_containers.append(container)
    editor.rebuild(make_device(kb))
    container.show()
    return editor, kb


def three():
    return [SliderTarget(62, WHITE, "Music"), SliderTarget(63, (255, 0, 0), "Game"),
            SliderTarget(64, (0, 0, 255), "Chat")]


def sets(kb):
    return [c[1] for c in kb.calls if c[0] == "set"]


def test_hidden_when_unsupported(qtbot):
    editor, kb = make_editor(qtbot, FakeKeyboard(supported=False))
    assert not editor.valid()
    editor.rebuild(None)
    assert not editor.valid()


def test_rows_match_targets(qtbot):
    editor, kb = make_editor(qtbot, FakeKeyboard(targets=three()))
    assert editor.valid()
    assert [r.name.text() for r in editor.rows] == ["Music", "Game", "Chat"]
    assert [r.control.value() for r in editor.rows] == [62, 63, 64]
    assert [r.colour for r in editor.rows] == [WHITE, (255, 0, 0), (0, 0, 255)]
    assert editor.rows[0].name.maxLength() == 12
    assert editor.rows[0].control.minimum() == 0 and editor.rows[0].control.maximum() == 127
    assert editor.note.text() == NOTE_TEXT
    assert "Next slider target" in NOTE_TEXT
    assert "User tab" in NOTE_TEXT


def test_edit_name_writes_full_list(qtbot):
    editor, kb = make_editor(qtbot, FakeKeyboard(targets=three()))
    editor.rows[1].name.setText("Games")
    editor.rows[1].name.editingFinished.emit()
    assert sets(kb) == [[three()[0], SliderTarget(63, (255, 0, 0), "Games"), three()[2]]]
    # unchanged name: no write
    editor.rows[1].name.editingFinished.emit()
    assert len(sets(kb)) == 1


def test_edit_control_writes_full_list(qtbot):
    editor, kb = make_editor(qtbot, FakeKeyboard(targets=three()))
    editor.rows[2].control.setValue(70)
    assert sets(kb) == [three()[:2] + [SliderTarget(70, (0, 0, 255), "Chat")]]
    assert kb.slider_targets[2].control == 70


def test_edit_colour_writes_on_accept(qtbot):
    editor, kb = make_editor(qtbot, FakeKeyboard(targets=three()))
    editor.rows[0].swatch.clicked.emit()
    editor.dlg_color.setCurrentColor(QColor(1, 2, 3))
    editor.dlg_color.reject()
    assert sets(kb) == []
    editor.rows[0].swatch.clicked.emit()
    editor.dlg_color.setCurrentColor(QColor(1, 2, 3))
    editor.dlg_color.accept()
    assert sets(kb) == [[SliderTarget(62, (1, 2, 3), "Music")] + three()[1:]]
    assert editor.rows[0].colour == (1, 2, 3)


def test_add_target_defaults_and_max(qtbot):
    targets = [SliderTarget(62, WHITE, "A"), SliderTarget(64, WHITE, "B")]
    editor, kb = make_editor(qtbot, FakeKeyboard(targets=targets, maximum=3))
    assert editor.btn_add.isEnabled()
    editor.btn_add.click()
    assert sets(kb) == [targets + [SliderTarget(63, WHITE, "Target 3")]]
    assert len(editor.rows) == 3
    assert not editor.btn_add.isEnabled()


def test_remove_disabled_with_one_target(qtbot):
    editor, kb = make_editor(qtbot)
    assert len(editor.rows) == 1
    assert not editor.rows[0].remove.isEnabled()


def test_remove_writes_list(qtbot):
    editor, kb = make_editor(qtbot, FakeKeyboard(targets=three()))
    editor.rows[1].remove.click()
    assert sets(kb) == [[three()[0], three()[2]]]
    assert [r.name.text() for r in editor.rows] == ["Music", "Chat"]


def test_up_down_reorder_writes(qtbot):
    editor, kb = make_editor(qtbot, FakeKeyboard(targets=three()))
    assert not editor.rows[0].up.isEnabled()
    assert not editor.rows[2].down.isEnabled()
    a, b, c = three()
    editor.rows[2].up.click()
    assert sets(kb)[-1] == [a, c, b]
    editor.rows[0].down.click()
    assert sets(kb)[-1] == [c, a, b]
    assert [r.name.text() for r in editor.rows] == ["Chat", "Music", "Game"]


def test_current_row_marked_and_updated_by_timer(qtbot):
    kb = FakeKeyboard(targets=three(), current=1)
    editor, kb = make_editor(qtbot, kb)
    assert [r.marker.text() for r in editor.rows] == ["", "▶", ""]
    assert editor.rows[1].name.font().bold()
    assert not editor.rows[0].name.font().bold()

    editor.activate()
    assert editor.timer.isActive()
    assert editor.timer.interval() == 1000
    kb.next_current = 2
    editor.rows[0].name.setText("typing")   # not yet written
    editor.on_timer()
    assert ("reload",) in kb.calls
    assert [r.marker.text() for r in editor.rows] == ["", "", "▶"]
    assert editor.rows[2].name.font().bold()
    # list didn't change, so the rows were not rebuilt under the user's typing
    assert editor.rows[0].name.text() == "typing"
    editor.deactivate()
    assert not editor.timer.isActive()


def test_errors_shown_no_crash(qtbot):
    editor, kb = make_editor(qtbot, FakeKeyboard(targets=three()))
    assert editor.error_label.isHidden()
    kb.fail = True
    editor.rows[0].control.setValue(10)
    assert not editor.error_label.isHidden()
    # table reflects the keyboard's (unchanged) state
    assert editor.rows[0].control.value() == 62
    editor.on_timer()
    assert not editor.error_label.isHidden()
    # a failed reload keeps the last known state
    assert editor.valid()
    assert kb.slider_targets == three()
    assert len(editor.rows) == 3
    kb.fail = False
    editor.rows[0].control.setValue(10)
    assert editor.error_label.isHidden()
    assert kb.slider_targets[0].control == 10


def test_bad_name_shows_error_and_reverts(qtbot):
    editor, kb = make_editor(qtbot, FakeKeyboard(targets=three()))
    editor.rows[0].name.setText("Müsic")
    editor.rows[0].name.editingFinished.emit()
    assert not editor.error_label.isHidden()
    assert editor.rows[0].name.text() == "Music"


def test_removed_row_does_not_write(qtbot):
    editor, kb = make_editor(qtbot, FakeKeyboard(targets=three()))
    old = editor.rows[2]
    editor.rows[1].remove.click()
    # a focused name field emits editingFinished when hidden; it must not write against the new list
    old.name.editingFinished.emit()
    old.control.setValue(100)
    assert sets(kb) == [[three()[0], three()[2]]]


def test_name_rejects_non_ascii(qtbot):
    editor, kb = make_editor(qtbot, FakeKeyboard(targets=three()))
    name = editor.rows[0].name
    name.clear()
    QTest.keyClicks(name, "Musée")
    assert name.text() == "Muse"
    assert all(32 <= ord(ch) <= 126 for ch in name.text())


# ---- lights that flash when switching target ----

RED, BLUE = (255, 0, 0), (0, 0, 255)
# three keys plus a side light on each side
LEDS = [LedInfo(i * 20, 0, 4, 0, i) for i in range(3)] + \
       [LedInfo(0, 32, 2, 0xFF, 0xFF), LedInfo(224, 32, 2, 0xFF, 0xFF)]


class FlashKeyboard(FakeKeyboard):

    def __init__(self, mask=0b10101, leds=LEDS, **kw):
        kw.setdefault("targets", three())
        super().__init__(**kw)
        self.slider_flash_supported = True
        self.slider_flash_mask = mask
        self.keys = make_keys()
        self.leds = list(leds)
        self.next_flash = None

    def set_slider_flash_mask(self, mask):
        self.calls.append(("flash", mask))
        if self.fail:
            raise RuntimeError("boom")
        self.slider_flash_mask = mask

    def reload_slider_targets(self):
        saved = self.slider_flash_mask
        self.slider_flash_supported = False
        super().reload_slider_targets()
        self.slider_flash_supported = True
        self.slider_flash_mask = saved if self.next_flash is None else self.next_flash


class FakeLayoutEditor(QObject):
    changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.choice = 0

    def get_choice(self, idx):
        return self.choice


def make_flash_editor(qtbot, kb=None, layout_editor=None):
    kb = kb or FlashKeyboard()
    editor = SliderTargetsEditor(layout_editor)
    container = EditorContainer(editor)
    qtbot.addWidget(container)
    all_containers.append(container)
    editor.rebuild(make_device(kb))
    container.show()
    return editor, kb


def flashes(kb):
    return [c[1] for c in kb.calls if c[0] == "flash"]


def stroke(editor, *leds):
    for led in leds:
        editor.flash_widget.stroke_painted.emit([led])
    editor.flash_widget.stroke_finished.emit()


def test_flash_hidden_on_version_1_firmware(qtbot):
    editor, kb = make_editor(qtbot, FakeKeyboard(targets=three()))
    assert editor.flash_section.isHidden()
    editor.rows[0].control.setValue(10)
    assert sets(kb)[-1][0].control == 10


def test_flash_hidden_without_led_info(qtbot):
    editor, kb = make_flash_editor(qtbot, FlashKeyboard(leds=[]))
    assert editor.flash_section.isHidden()


def test_flash_shows_mask_in_current_colour(qtbot):
    editor, kb = make_flash_editor(qtbot)
    assert not editor.flash_section.isHidden()
    assert editor.flash_widget.leds == LEDS
    assert editor.flash_widget.colours == [WHITE, None, WHITE, None, WHITE]
    editor2, kb2 = make_flash_editor(qtbot, FlashKeyboard(current=1))
    assert editor2.flash_widget.colours == [RED, None, RED, None, RED]


def test_clicking_row_previews_its_colour(qtbot):
    editor, kb = make_flash_editor(qtbot)
    QTest.mouseClick(editor.rows[2].name, Qt.LeftButton)
    assert editor.flash_widget.colours == [BLUE, None, BLUE, None, BLUE]
    QTest.mouseClick(editor.rows[1].marker, Qt.LeftButton)
    assert editor.flash_widget.colours == [RED, None, RED, None, RED]
    QTest.mouseClick(editor.rows[0].control.findChild(QLineEdit), Qt.LeftButton)
    assert editor.flash_widget.colours == [WHITE, None, WHITE, None, WHITE]
    # previewing does not touch the keyboard
    assert sets(kb) == [] and flashes(kb) == []
    assert kb.slider_current == 0


def test_stroke_first_led_turns_on_and_writes_once(qtbot):
    editor, kb = make_flash_editor(qtbot)
    editor.flash_widget.stroke_painted.emit([1])   # off -> the stroke turns lights on
    editor.flash_widget.stroke_painted.emit([0])   # already on: stays on
    editor.flash_widget.stroke_painted.emit([3])
    assert flashes(kb) == []
    assert editor.flash_widget.colours == [WHITE] * 5
    editor.flash_widget.stroke_finished.emit()
    assert flashes(kb) == [0b11111]


def test_stroke_first_led_turns_off(qtbot):
    editor, kb = make_flash_editor(qtbot)
    stroke(editor, 0, 1, 2)
    assert flashes(kb) == [0b10000]
    assert editor.flash_widget.colours == [None, None, None, None, WHITE]


def test_empty_stroke_writes_nothing(qtbot):
    editor, kb = make_flash_editor(qtbot)
    editor.flash_widget.stroke_finished.emit()
    assert flashes(kb) == []


def test_flash_buttons(qtbot):
    editor, kb = make_flash_editor(qtbot)
    editor.btn_flash_none.click()
    assert flashes(kb) == [0]
    assert editor.flash_widget.colours == [None] * 5
    editor.btn_flash_edges.click()
    assert flashes(kb) == [0, 0b11000]
    editor.btn_flash_all.click()
    assert flashes(kb) == [0, 0b11000, 0b11111]
    assert editor.flash_widget.colours == [WHITE] * 5


def test_failed_flash_write_shows_error_and_keyboard_mask(qtbot):
    editor, kb = make_flash_editor(qtbot)
    kb.fail = True
    stroke(editor, 1, 3)
    assert flashes(kb) == [0b11111]
    assert not editor.error_label.isHidden()
    assert editor.flash_widget.colours == [WHITE, None, WHITE, None, WHITE]
    kb.fail = False
    editor.btn_flash_none.click()
    assert editor.error_label.isHidden()


def test_timer_only_redraws_on_change(qtbot):
    editor, kb = make_flash_editor(qtbot)
    builds, recolours = [], []
    orig_set_keyboard, orig_set_colours = editor.flash_widget.set_keyboard, editor.flash_widget.set_colours
    editor.flash_widget.set_keyboard = lambda *a: (builds.append(1), orig_set_keyboard(*a))
    editor.flash_widget.set_colours = lambda c: (recolours.append(list(c)), orig_set_colours(c))
    editor.on_timer()
    editor.on_timer()
    assert builds == [] and recolours == [] and flashes(kb) == []
    kb.next_flash = 0b00001
    editor.on_timer()
    assert recolours == [[WHITE, None, None, None, None]]
    assert builds == [] and flashes(kb) == []
    kb.next_current = 2
    editor.on_timer()
    assert recolours[-1] == [BLUE, None, None, None, None]
    assert builds == [] and flashes(kb) == []


def test_timer_mid_stroke_keeps_pending_drawing(qtbot):
    editor, kb = make_flash_editor(qtbot)
    editor.flash_widget.stroke_painted.emit([1])
    editor.on_timer()
    assert editor.flash_widget.colours == [WHITE, WHITE, WHITE, None, WHITE]
    editor.flash_widget.stroke_finished.emit()
    assert flashes(kb) == [0b10111]


def test_layout_choice_redraws(qtbot):
    layout = FakeLayoutEditor()
    editor, kb = make_flash_editor(qtbot, layout_editor=layout)
    assert editor.flash_widget.layout_choice == layout.get_choice
    builds = []
    orig = editor.flash_widget.set_keyboard
    editor.flash_widget.set_keyboard = lambda *a: (builds.append(a), orig(*a))
    layout.changed.emit()
    assert len(builds) == 1
    assert flashes(kb) == []
