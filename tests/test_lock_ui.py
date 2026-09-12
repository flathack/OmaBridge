import pytest
from PySide6.QtCore import QTimer, QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineCore import QWebEnginePage

from omabridge.app_lock import AppLockStore
from omabridge.browser import PortalSession
from omabridge.models import Site
from omabridge.storage import SiteStore
from omabridge.ui import MainWindow, SettingsDialog
from test_browser import wait_for
from test_ui import MemoryVault


def test_startup_ipc_and_shortcuts_require_unlock_and_manual_lock_disposes_sessions(app, tmp_path, monkeypatch):
    store, vault = SiteStore(tmp_path), MemoryVault()
    site = Site('Private office', 'https://citrix.test')
    store.save([site])
    AppLockStore(tmp_path).configure('1234', 'pin')
    real_load = store.load
    loads = []
    def counted_load():
        loads.append(True)
        return real_load()
    monkeypatch.setattr(store, 'load', counted_load)
    monkeypatch.setattr(PortalSession, 'start', lambda self: self.timer.stop())
    window = MainWindow(store, vault)
    window.show()
    assert window.locked and not loads and not window.sites
    assert window.pages.currentWidget() is window.lock_page
    for action in [window.add_site, window.edit_site, window.edit_dialog, window.delete_site,
                   window.connect_site, window.open_settings, lambda: window.change_mode('browser')]:
        action()
    window.open_site_id(site.id)  # Same entry point as startup --site and IPC.
    assert not window.jobs and not window.sessions and not vault.threads and not loads
    window.unlock_secret.setText('incorrect')
    window.unlock_app()
    wait_for(app, lambda: not window.jobs)
    assert window.locked and not loads and 'Incorrect' in window.unlock_error.text()
    assert not window.unlock_secret.text()
    window.unlock_secret.setText('1234')
    window.unlock_app()
    wait_for(app, lambda: not window.jobs)
    assert not window.locked and loads and site.id in window.sessions
    session = window.sessions[site.id]
    session.page.createWindow(QWebEnginePage.WebWindowType.WebBrowserTab)
    assert window.popup_tabs
    window.lock_app()
    assert window.locked and not window.sessions and not window.popup_tabs and not window.sites
    assert session.disposed
    assert window.tabs.count() == 0 and window.windowTitle() == 'OmaBridge'
    assert not window.status.address and window.sites_menu.isEmpty()
    # A missing lock file in the running process must never grant access.
    window.lock_store.path.unlink()
    window.unlock_secret.setText('1234')
    window.unlock_app()
    wait_for(app, lambda: not window.jobs)
    assert window.locked and 'changed' in window.unlock_error.text()
    window.close(); window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_setting_changing_and_disabling_lock_requires_old_secret(app, tmp_path):
    window = MainWindow(SiteStore(tmp_path), MemoryVault())
    errors = []
    window.show_error = errors.append
    window.save_lock_settings(True, 'pin', '', '1234567', 'en')
    wait_for(app, lambda: not window.jobs)
    assert window.lock_config['kind'] == 'pin' and window.lock_action.isEnabled()
    assert not window.locked  # Enabling protects the next launch or manual lock.
    original = window.lock_store.load()['digest']
    for enabled in [True, False]:
        window.save_lock_settings(enabled, 'password', 'wrong', 'long new password', 'en')
        wait_for(app, lambda: not window.jobs)
        assert window.lock_store.load()['digest'] == original
    assert len(errors) == 2
    window.save_lock_settings(True, 'password', '1234567', 'long new password', 'de')
    wait_for(app, lambda: not window.jobs)
    assert window.lock_config['kind'] == 'password'
    assert window.lock_action.text() == 'App sperren'
    assert window.unlock_button.text() == 'Entsperren'
    window.save_lock_settings(False, 'password', 'long new password', '', 'en')
    wait_for(app, lambda: not window.jobs)
    assert window.lock_config is None and not window.lock_action.isEnabled()
    assert window.lock_store.load() is None
    window.close(); window.deleteLater()


def test_settings_validate_confirmation_and_arbitrary_pin_length(app):
    dialog = SettingsDialog()
    assert not dialog.lock_enabled.isChecked()
    dialog.lock_enabled.setChecked(True)
    dialog.new_secret.setText('123456789012345')
    dialog.confirm_secret.setText('different')
    dialog.validate()
    assert dialog.error.text() and not dialog.result()
    dialog.confirm_secret.setText('123456789012345')
    dialog.validate()
    assert dialog.result() == dialog.DialogCode.Accepted
    dialog.deleteLater()
