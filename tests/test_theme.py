from PySide6.QtGui import QPalette
from omabridge.theme import palette, stylesheet, ThemeWatcher
from omabridge.ui import MainWindow, SettingsDialog, STYLE
from omabridge.storage import SiteStore
from test_browser import wait_for
from test_ui import MemoryVault


def test_light_dark_and_untrusted_palette_values():
    light = palette({'background': '#ffffff', 'foreground': '#111111', 'accent': '#ffee00'})
    dark = palette({'bg': '#080512', 'fg': '#e0feea', 'blue': '#123456'})
    assert light['on_accent'] == '#000000'
    assert dark['on_accent'] == '#ffffff'
    assert dark['background'] == '#080512'
    assert light['surface'] != dark['surface']
    malicious = palette({'background': 'url(/private/file)', 'accent': {'nested': 'value'}})
    assert 'private' not in stylesheet(STYLE, malicious)


def test_live_theme_rotation_updates_window_and_open_dialog(app, tmp_path, monkeypatch):
    from omabridge import theme
    first, second = tmp_path / 'first', tmp_path / 'second'
    first.mkdir(); second.mkdir()
    (first / 'colors.toml').write_text('background = "#111111"\nforeground = "#eeeeee"\naccent = "#445566"')
    (second / 'colors.toml').write_text('background = "#ffffff"\nforeground = "#222222"\naccent = "#aabbcc"')
    current = tmp_path / 'current'
    current.symlink_to(first, target_is_directory=True)
    monkeypatch.setattr(theme, 'theme_paths', lambda: [current / 'colors.toml'])
    from omabridge.browser import PortalSession
    from omabridge.models import Site
    store = SiteStore(tmp_path / 'config')
    store.save([Site('Demo', 'https://citrix.test')])
    monkeypatch.setattr(PortalSession, 'start', lambda self: self.timer.stop())
    window = MainWindow(store, MemoryVault())
    window.connect_site()
    wait_for(app, lambda: not window.jobs)
    session = window.sessions[window.sites[0].id]
    vault_reads = len(window.vault.threads)
    window.show()
    dialog = SettingsDialog(window)
    dialog.show()
    assert window.theme_colors['background'] == '#111111'
    replacement = tmp_path / 'next'
    replacement.symlink_to(second, target_is_directory=True)
    replacement.replace(current)
    # Exercise the timer, not a manual refresh or application restart.
    wait_for(app, lambda: window.theme_colors['background'] == '#ffffff')
    assert '#ffffff' in window.styleSheet()
    assert '#222222' in window.back_button.styleSheet()
    assert dialog.palette().color(QPalette.ColorRole.Window).name() == '#ffffff'
    assert window.sessions[window.sites[0].id] is session
    assert not session.disposed and len(window.vault.threads) == vault_reads
    (second / 'colors.toml').write_text('invalid = [')
    window.theme.refresh()
    assert window.theme_colors['background'] == '#ffffff'
    current.unlink()
    window.theme.refresh()
    assert window.theme_colors['background'] == '#ffffff'
    dialog.close(); window.close()
    dialog.deleteLater(); window.deleteLater()


def test_missing_theme_uses_fallback(app, tmp_path):
    watcher = ThemeWatcher(paths=[tmp_path / 'missing'])
    watcher.refresh()
    assert watcher.colors == palette()
    watcher.deleteLater()
