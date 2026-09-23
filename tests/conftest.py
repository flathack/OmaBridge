import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(autouse=True)
def reset_language():
    from omabridge.i18n import set_language
    set_language("en")
    yield
    set_language("en")


@pytest.fixture(autouse=True)
def isolated_browser_profiles(tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'xdg-config'))


@pytest.fixture(scope="session")
def app():
    application = QApplication.instance() or QApplication([])
    yield application
