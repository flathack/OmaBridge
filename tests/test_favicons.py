import json
import os
import subprocess
import sys

from PySide6.QtCore import QUrl
from PySide6.QtGui import QColor, QIcon, QPixmap

from omabridge.bar_ipc import window_state
from omabridge.favicons import FaviconStore
from omabridge.models import Site
from omabridge.storage import SiteStore
from omabridge.ui import MainWindow
from test_ui import MemoryVault


def test_favicon_is_private_and_shared_with_tabs_menu_and_bar(app, tmp_path):
    site = Site('Office', 'https://citrix.test/Citrix/StoreWeb/')
    store = SiteStore(tmp_path)
    store.save([site])
    window = MainWindow(store, MemoryVault())
    image = QPixmap(32, 32)
    image.fill(QColor('#b03040'))
    class View:
        def url(self):
            return QUrl('https://citrix.test/Citrix/StoreWeb/')
    try:
        assert window.tabs.tabIcon(0).isNull()
        assert 'icon' not in window_state(window)['sites'][0]
        window.save_portal_favicon(site.id, View(), QIcon(image))
        path = window.favicons.path(site.id)
        assert path.is_file() and path.stat().st_mode & 0o777 == 0o600
        assert window.tabs.tabIcon(0).isNull() is False
        window.populate_sites_menu()
        assert window.sites_menu.actions()[0].icon().isNull() is False
        assert window_state(window)['sites'][0]['icon'].startswith(path.as_uri())
        window.locked = True
        assert window_state(window)['sites'] == []
    finally:
        window.close()


def test_favicon_rejects_other_origins_and_invalid_site_ids(app, tmp_path):
    site = Site('Office', 'https://citrix.test/')
    store = SiteStore(tmp_path)
    store.save([site])
    window = MainWindow(store, MemoryVault())
    image = QPixmap(32, 32)
    image.fill(QColor('red'))
    class View:
        def url(self):
            return QUrl('https://other.test/')
    try:
        window.save_portal_favicon(site.id, View(), QIcon(image))
        assert not window.favicons.path(site.id).exists()
        try:
            FaviconStore(tmp_path).path('../escape')
        except ValueError:
            pass
        else:
            assert False, 'Invalid site IDs must not escape the favicon directory'
    finally:
        window.close()


def test_cold_bar_state_uses_cached_icon_but_list_sites_stays_stable(app, tmp_path):
    directory = tmp_path / 'omabridge'
    site = Site('Office', 'https://citrix.test/')
    SiteStore(directory).save([site])
    image = QPixmap(32, 32)
    image.fill(QColor('red'))
    icons = FaviconStore(directory)
    assert icons.save(site.id, QIcon(image))
    env = {**os.environ, 'XDG_CONFIG_HOME': str(tmp_path)}
    state = json.loads(subprocess.check_output([sys.executable, '-m', 'omabridge', '--bar-state'], env=env))
    listed = json.loads(subprocess.check_output([sys.executable, '-m', 'omabridge', '--list-sites'], env=env))
    assert state['sites'][0]['icon'] == icons.url(site.id)
    assert listed == [{'id': site.id, 'name': site.name, 'mode': site.mode}]
