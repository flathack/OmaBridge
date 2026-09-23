"""Read Omarchy's active palette without executing theme code."""
import os
import re
import tomllib
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QColor, QPalette

HEX = re.compile(r'#[0-9a-fA-F]{6}\Z')


def theme_paths():
    state = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state'))
    config = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config'))
    return [state / 'omarchy/current/theme/colors.toml', config / 'omarchy/current/theme/colors.toml']


def mix(first, second, amount):
    a, b = QColor(first), QColor(second)
    return QColor(*(round(x * (1 - amount) + y * amount) for x, y in
                    zip(a.getRgb()[:3], b.getRgb()[:3]))).name()


def contrast_text(color):
    rgb = QColor(color).getRgbF()[:3]
    linear = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in rgb]
    luminance = sum(c * weight for c, weight in zip(linear, (.2126, .7152, .0722)))
    return '#000000' if luminance > .179 else '#ffffff'


def palette(values=None):
    values = values or {}
    def pick(*keys, fallback):
        return next((values[k].lower() for k in keys if isinstance(values.get(k), str)
                     and HEX.fullmatch(values[k])), fallback)
    bg = pick('background', 'bg', 'color0', fallback='#151f2c')
    fg = pick('foreground', 'fg', 'color7', fallback=contrast_text(bg))
    accent = pick('accent', 'blue', 'color4', fallback='#8fb9e8')
    warning = pick('yellow', 'color3', fallback='#dfac50')
    return dict(background=bg, foreground=fg, accent=accent,
                surface=pick('lighter_bg', fallback=mix(bg, fg, .06)),
                raised=mix(bg, fg, .12), hover=mix(bg, accent, .22),
                border=mix(bg, fg, .28), muted=mix(bg, fg, .64),
                disabled=mix(bg, fg, .4), accent_hover=mix(accent, fg, .2),
                on_accent=contrast_text(accent), warning_bg=mix(bg, warning, .15),
                warning_fg=mix(fg, warning, .4), warning_border=mix(bg, warning, .65))


def midnight_palette():
    # Odysseus Midnight's base colors, mapped onto OmaBridge's Qt controls.
    return dict(background='#0d1117', foreground='#c9d1d9', accent='#f85149',
                surface='#161b22', raised='#21262d', hover='#30363d',
                border='#30363d', muted='#8b949e', disabled='#6e7681',
                accent_hover='#ff6a61', on_accent='#0d1117',
                warning_bg='#382b18', warning_fg='#e3b341',
                warning_border='#9e6a03')


def stylesheet(template, colors):
    replacements = {
        '#151f2c': 'background', '#dce7f5': 'foreground', '#9bafc5': 'muted',
        '#b6cee8': 'foreground', '#1d2b3b': 'surface', '#26384d': 'raised',
        '#3c516a': 'border', '#344b65': 'hover', '#8fb9e8': 'accent',
        '#b0d0f2': 'accent_hover', '#587a9f': 'accent', '#607489': 'disabled',
    }
    result = re.sub(r'#[0-9a-fA-F]{6}', lambda m: colors.get(replacements.get(m[0]), m[0]), template)
    result += '\nQPushButton#primary { color: ' + colors['on_accent'] + '; }'
    result += '\nQLabel#totpWarning { color: ' + colors['warning_fg'] + '; background: ' + colors['warning_bg'] + '; border: 1px solid ' + colors['warning_border'] + '; border-radius: 5px; padding: 10px; }'
    return result


def qt_palette(colors):
    result = QPalette()
    for role, key in [(QPalette.ColorRole.Window, 'background'), (QPalette.ColorRole.WindowText, 'foreground'),
                      (QPalette.ColorRole.Base, 'surface'), (QPalette.ColorRole.AlternateBase, 'raised'),
                      (QPalette.ColorRole.Text, 'foreground'), (QPalette.ColorRole.Button, 'raised'),
                      (QPalette.ColorRole.ButtonText, 'foreground'), (QPalette.ColorRole.Highlight, 'accent'),
                      (QPalette.ColorRole.HighlightedText, 'on_accent'), (QPalette.ColorRole.ToolTipBase, 'surface'),
                      (QPalette.ColorRole.ToolTipText, 'foreground')]:
        result.setColor(role, QColor(colors[key]))
    return result


class ThemeWatcher(QObject):
    changed = Signal(dict)

    def __init__(self, parent=None, paths=None):
        super().__init__(parent)
        self.paths = paths if paths is not None else theme_paths()
        self.colors = None
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()

    def refresh(self):
        # Poll the logical path: Omarchy atomically replaces directories/symlinks.
        # Keep the previous palette while a theme switch is incomplete.
        for path in self.paths:
            try:
                with path.open('rb') as source:
                    content = source.read(65537)
                if len(content) > 65536:
                    continue
                values = tomllib.loads(content.decode('utf-8'))
                colors = palette(values)
                break
            except (OSError, ValueError):
                continue
        else:
            colors = self.colors or palette()
        if colors != self.colors:
            self.colors = colors
            self.changed.emit(colors)
