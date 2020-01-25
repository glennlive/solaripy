class FakeLoad:
    def __init__(self):
        self._current = 0.0
        self.voltage = 1.7
        self.enabled = True

    @property
    def current(self):
        self._current += 0.01
        return self._current

    @current.setter
    def current(self, value):
        self._current = value
        self.voltage -= 0.01 * value

