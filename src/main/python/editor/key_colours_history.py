class ColourHistory:
    """ Undo stack of paint strokes. Each entry is (layer, {led: old colour}). """

    def __init__(self, limit=50):
        self.limit = limit
        self.stack = []
        self.layer = None
        self.current = None

    def begin_stroke(self, layer):
        self.layer = layer
        self.current = {}

    def record(self, led, old, new):
        if self.current is not None and led not in self.current:
            self.current[led] = old

    def end_stroke(self):
        if self.current:
            self.stack.append((self.layer, self.current))
            del self.stack[:-self.limit]
        self.current = None

    def can_undo(self):
        return bool(self.stack)

    def undo(self):
        return self.stack.pop() if self.stack else None
