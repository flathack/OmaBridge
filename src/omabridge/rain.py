"""Quiet Midnight rain on OmaBridge-owned pages."""

import random
import time

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QWidget


class RainBackground(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('midnightBackdrop')
        self._random = random.Random()
        self._drops = []
        self._enabled = False
        self._last_frame = time.monotonic()
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._advance)

    def set_rain_enabled(self, enabled: bool):
        self._enabled = enabled
        if enabled and not self._drops and self.width() and self.height():
            for _ in range(min(34, max(12, self.width() // 30))):
                self._drops.append((self._random.uniform(0, self.width()),
                                    self._random.uniform(0, self.height()),
                                    self._random.uniform(20, 60),
                                    self._random.uniform(100, 300),
                                    self._random.uniform(0.16, 0.30)))
        if enabled and self.isVisible():
            self._last_frame = time.monotonic()
            self._timer.start()
        else:
            self._timer.stop()
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        if self._enabled:
            self._last_frame = time.monotonic()
            self._timer.start()

    def hideEvent(self, event):
        self._timer.stop()
        super().hideEvent(event)

    def _advance(self):
        now = time.monotonic()
        elapsed = min(now - self._last_frame, 0.08)
        self._last_frame = now
        self._drops = [(x, y + speed * elapsed, length, speed, alpha)
                       for x, y, length, speed, alpha in self._drops
                       if y < self.height() + length]
        target = min(65, max(12, self.width() // 18))
        if len(self._drops) < target and self._random.random() < 0.45:
            self._drops.append((self._random.uniform(0, max(1, self.width())),
                                -self._random.uniform(20, 60),
                                self._random.uniform(20, 60),
                                self._random.uniform(100, 300),
                                self._random.uniform(0.16, 0.30)))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor('#0d1117') if self._enabled else self.palette().window())
        if not self._enabled:
            return
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for x, y, length, _, alpha in self._drops:
            gradient = QLinearGradient(x, y - length, x, y)
            gradient.setColorAt(0, QColor(255, 255, 255, 0))
            gradient.setColorAt(1, QColor(255, 255, 255, round(alpha * 255)))
            painter.setPen(QPen(gradient, 1.3))
            painter.drawLine(round(x), round(y - length), round(x), round(y))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 255, 255, round(alpha * 255)))
            painter.drawEllipse(round(x) - 1, round(y) - 1, 3, 3)
