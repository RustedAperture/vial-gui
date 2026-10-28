import unittest

from editor.key_colours_history import ColourHistory


class TestColourHistory(unittest.TestCase):

    def test_stroke_keeps_first_old(self):
        h = ColourHistory()
        h.begin_stroke(2)
        h.record(1, (1, 1, 1), (9, 9, 9))
        h.record(2, None, (8, 8, 8))
        h.record(1, (9, 9, 9), (7, 7, 7))
        h.end_stroke()
        self.assertTrue(h.can_undo())
        self.assertEqual(h.undo(), (2, {1: (1, 1, 1), 2: None}))
        self.assertFalse(h.can_undo())

    def test_empty_stroke_not_pushed(self):
        h = ColourHistory()
        h.begin_stroke(0)
        h.end_stroke()
        self.assertFalse(h.can_undo())

    def test_limit_drops_oldest(self):
        h = ColourHistory(limit=2)
        for n in range(3):
            h.begin_stroke(n)
            h.record(n, None, (n, n, n))
            h.end_stroke()
        self.assertEqual(h.undo()[0], 2)
        self.assertEqual(h.undo()[0], 1)
        self.assertIsNone(h.undo())

    def test_undo_empty(self):
        self.assertIsNone(ColourHistory().undo())
