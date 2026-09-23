import threading

import pytest

from PySide6.QtCore import QTimer, QPoint, QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from omabridge.models import Credentials, Site
from omabridge.browser import PortalSession
from omabridge.storage import SiteStore
from omabridge.ui import MainWindow, SiteDialog
from test_browser import wait_for


class MemoryVault:
    def __init__(self):
        self.entries = {}
        self.threads = []

    def get(self, key):
        self.threads.append(threading.current_thread())
        return self.entries.get(key, Credentials())

    def set(self, key, value):
        self.threads.append(threading.current_thread())
        self.entries[key] = value

    def delete(self, key):
        self.threads.append(threading.current_thread())
        self.entries.pop(key, None)


def enter_site(name="Büro", url="https://citrix.test/Citrix/StoreWeb/"):
    dialog = QApplication.activeModalWidget()
    assert isinstance(dialog, SiteDialog)
    dialog.name.setText(name)
    dialog.url.setText(url)
    dialog.username.setText("demo-user")
    dialog.password.setText("test-password")
    dialog.store_totp.setChecked(True)
    dialog.totp.setText("GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ")
    dialog.validate()


def test_create_edit_mode_delete_and_vault_threads(app, tmp_path):
    vault, store = MemoryVault(), SiteStore(tmp_path)
    window = MainWindow(store, vault)
    errors = []
    window.show_error = errors.append
    window.show()
    QTimer.singleShot(0, enter_site)
    window.add_site()
    wait_for(app, lambda: not window.jobs)
    assert not errors
    first = store.load()[0]
    assert first.name == "Büro"
    assert vault.entries[first.id].password == "test-password"
    assert "test-password" not in store.path.read_text()
    QTimer.singleShot(0, lambda: enter_site("Kunde", "https://customer.test"))
    window.add_site()
    wait_for(app, lambda: not window.jobs)
    assert len(store.load()) == 2
    window.change_mode("browser")
    assert store.load()[1].mode == "browser"
    # Editing fetches the keyring asynchronously before opening the dialog.
    edit_timer = QTimer()
    def edit_when_open():
        if isinstance(QApplication.activeModalWidget(), SiteDialog):
            edit_timer.stop()
            enter_site("Kunde neu", "https://customer.test")
    edit_timer.timeout.connect(edit_when_open)
    edit_timer.start(10)
    window.edit_site()
    wait_for(app, lambda: store.load()[1].name == "Kunde neu")
    wait_for(app, lambda: not window.jobs)
    QTimer.singleShot(0, lambda: QApplication.activeModalWidget().done(QMessageBox.StandardButton.Yes))
    window.delete_site()
    wait_for(app, lambda: not window.jobs)
    assert len(store.load()) == 1 and len(vault.entries) == 1
    assert all(thread is not threading.main_thread() for thread in vault.threads)
    assert not errors
    window.close()


def test_failed_config_write_rolls_back_new_secret(app, tmp_path, monkeypatch):
    vault, store = MemoryVault(), SiteStore(tmp_path)
    window = MainWindow(store, vault)
    errors = []
    window.show_error = errors.append
    def fail(_):
        raise OSError("Disk full")
    monkeypatch.setattr(store, "save", fail)
    QTimer.singleShot(0, enter_site)
    window.add_site()
    wait_for(app, lambda: not window.jobs)
    assert errors and str(errors[0]) == "Disk full"
    assert not vault.entries and not window.sites
    window.close()


def test_ica_address_approval_is_site_scoped_and_persistent(app, tab_window):
    window = tab_window
    site = window.sites[0]
    def approve():
        box = QApplication.activeModalWidget()
        assert isinstance(box, QMessageBox)
        assert "https://downloads.test" in box.text()
        next(button for button in box.buttons() if box.buttonRole(button) == QMessageBox.ButtonRole.AcceptRole).click()
    QTimer.singleShot(0, approve)
    assert window.approve_ica_origin(site, "https://downloads.test")
    assert window.store.load()[0].ica_origins == ["https://downloads.test"]
    assert window.store.load()[1].ica_origins == []


def test_ica_address_rejection_does_not_save(app, tab_window):
    window = tab_window
    QTimer.singleShot(0, lambda: QApplication.activeModalWidget().reject())
    assert not window.approve_ica_origin(window.sites[0], "https://downloads.test")
    assert window.store.load()[0].ica_origins == []


def test_removing_site_clears_persistent_browser_profile(app, tab_window):
    window = tab_window
    site = window.sites[0]
    window.connect_site()
    wait_for(app, lambda: site.id in window.sessions)
    profile = window.store.directory / 'browser' / site.id
    assert profile.is_dir()
    QTimer.singleShot(0, lambda: QApplication.activeModalWidget().done(QMessageBox.StandardButton.Yes))
    window.delete_site()
    wait_for(app, lambda: site.id not in window.sessions)
    wait_for(app, lambda: not profile.exists())


def test_reopening_site_waits_for_old_browser_profile_removal(app, tab_window):
    window = tab_window
    site = window.sites[0]
    window.connect_site()
    wait_for(app, lambda: site.id in window.sessions)
    profile = window.store.directory / 'browser' / site.id
    (profile / 'old-session').write_text('marker')

    window.remove_session(site.id, remove_browser_data=True)
    window.connect_site()
    assert site.id in window.pending_profile_deletions
    assert site.id not in window.sessions
    assert window.pending_site_id == site.id

    wait_for(app, lambda: site.id in window.sessions)
    assert profile.is_dir()
    assert not (profile / 'old-session').exists()
    assert site.id not in window.pending_profile_deletions


def test_invalid_totp_prevents_saving(app):
    dialog = SiteDialog(None)
    dialog.name.setText("Büro")
    dialog.url.setText("https://citrix.test")
    dialog.store_totp.setChecked(True)
    dialog.totp.setText("123456")
    dialog.validate()
    assert dialog.value is None
    assert dialog.error.text()
    dialog.close()


def test_edit_site_preserves_only_relevant_ica_addresses(app):
    site = Site("Test", "https://citrix.test/Store", ica_origins=["https://downloads.test"])
    dialog = SiteDialog(None, site)
    dialog.url.setText("https://citrix.test/NewStore")
    dialog.validate()
    assert dialog.value[0].ica_origins == ["https://downloads.test"]
    dialog.close()
    dialog = SiteDialog(None, site)
    dialog.url.setText("https://other.test")
    dialog.validate()
    assert dialog.value[0].ica_origins == []
    dialog.close()


@pytest.fixture
def tab_window(app, tmp_path, monkeypatch):
    store = SiteStore(tmp_path)
    store.save([Site("Büro", "https://citrix.test"), Site("Kunde", "https://customer.test")])
    window = MainWindow(store, MemoryVault())
    # No external portals or credentials are used by these UI tests.
    monkeypatch.setattr(PortalSession, "start", lambda self: self.timer.stop())
    window.show()
    app.processEvents()
    yield window
    window.close()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.mark.parametrize("width", [640, 1320])
def test_portal_uses_entire_window_below_single_row(app, tab_window, width):
    window = tab_window
    window.resize(width, 700)
    window.connect_site()
    wait_for(app, lambda: not window.jobs)
    app.processEvents()
    view = window.current_view()
    assert window.toolbar.height() == 42
    assert view.mapTo(window, QPoint(0, 0)) == QPoint(0, 42)
    assert view.width() == window.width()
    assert view.height() == window.height() - 42
    assert window.status.parentWidget() is window.toolbar


def test_tabs_switch_sessions_and_reopen_closed_site(app, tab_window):
    window = tab_window
    first, second = window.sites
    window.connect_site()
    wait_for(app, lambda: not window.jobs)
    first_session = window.sessions[first.id]
    window.tabs.setCurrentIndex(1)
    wait_for(app, lambda: not window.jobs)
    assert window.current_site().id == second.id
    assert window.stack.currentWidget() is window.sessions[second.id]
    window.tabs.setCurrentIndex(0)
    assert window.stack.currentWidget() is first_session
    window.close_current_tab()
    assert first.id not in window.sessions
    assert first.id in window.hidden_sites
    assert len(window.store.load()) == 2
    window.open_site_id(first.id)
    wait_for(app, lambda: not window.jobs)
    assert first.id not in window.hidden_sites
    assert window.current_site().id == first.id
    assert window.sessions[first.id] is not first_session


def test_html5_popup_is_a_tab_with_same_profile_and_cleanup(app, tab_window):
    from PySide6.QtWebEngineCore import QWebEnginePage
    window = tab_window
    window.connect_site()
    wait_for(app, lambda: not window.jobs)
    site = window.current_site()
    session = window.sessions[site.id]
    popup_page = session.page.createWindow(QWebEnginePage.WebWindowType.WebBrowserTab)
    view = window.current_view()
    assert popup_page is view.page()
    assert popup_page.profile() is session.profile
    assert window.tabs.count() == 3
    assert window.stack.currentWidget() is view
    assert not view.isWindow()
    window.popup_title(window.current_key(), "Virtueller Desktop")
    assert window.tabs.tabText(window.tabs.currentIndex()) == "Virtueller Desktop"
    popup_page.windowCloseRequested.emit()
    assert window.tabs.count() == 2
    assert window.stack.currentWidget() is session
    assert not session.popups and not window.popup_tabs
    session.page.createWindow(QWebEnginePage.WebWindowType.WebBrowserTab)
    # Closing the parent Site tab closes its HTML5 children as well.
    window.close_tab(0)
    assert not window.popup_tabs
    assert site.id not in window.sessions


def test_menu_status_does_not_cover_portal(app, tab_window):
    window = tab_window
    assert window.font().family() == "monospace"
    assert [control.text() for control in (window.back_button, window.forward_button,
            window.reload_button, window.add_button, window.menu_button)] == ["󰁍", "󰁔", "󰑐", "󰐕", "󰇙"]
    window.show_session_message(window.sites[0].id, "Warte auf TOTP …")
    assert "Warte auf TOTP" in window.status.toolTip()
    assert window.status.text() == "󰋽"
    window.change_mode("browser")
    assert window.store.load()[0].mode == "browser"
    assert window.mode_actions["browser"].isChecked()


def test_unknown_site_id_does_not_connect_another_site(app, tab_window):
    tab_window.open_site_id("missing-site")
    assert not tab_window.jobs and not tab_window.sessions
    assert "not found" in tab_window.status.message


def test_language_settings_apply_live_and_persist_without_reconnecting(app, tab_window):
    from omabridge.ui import SettingsDialog
    from omabridge.i18n import language
    from PySide6.QtWebEngineCore import QWebEnginePage
    window = tab_window
    window.connect_site()
    wait_for(app, lambda: not window.jobs)
    session = window.sessions[window.sites[0].id]
    popup = session.page.createWindow(QWebEnginePage.WebWindowType.WebBrowserTab)
    view = window.current_view()
    site_names = [site.name for site in window.sites]
    assert language() == 'en' and window.settings_action.text() == 'Settings'
    def select_german():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, SettingsDialog)
        assert dialog.windowTitle() == 'Settings'
        dialog.language.setCurrentIndex(dialog.language.findData('de'))
        dialog.accept()
    QTimer.singleShot(0, select_german)
    window.open_settings()
    assert language() == 'de'
    assert window.settings_action.text() == 'Einstellungen'
    assert window.edit_action.text() == 'Site bearbeiten …'
    assert window.back_button.toolTip() == 'Zurück (Alt+Links)'
    assert window.preferences.load() == 'de'
    assert window.sessions[window.sites[0].id] is session
    assert window.current_view() is view and view.page() is popup
    assert [site.name for site in window.sites] == site_names
    dialog = SiteDialog(window)
    assert dialog.windowTitle() == 'Citrix-Site hinzufügen'
    assert dialog.password.accessibleName() == 'Passwort'
    dialog.close()
    dialog.deleteLater()
    window.close()
    reopened = MainWindow(window.store, MemoryVault())
    assert reopened.settings_action.text() == 'Einstellungen'
    reopened.change_language('en')
    assert reopened.settings_action.text() == 'Settings'
    assert reopened.preferences.load() == 'en'
    dialog = SiteDialog(reopened)
    assert dialog.password.accessibleName() == 'Password'
    dialog.close()
    dialog.deleteLater()
    reopened.close()
    reopened.deleteLater()


def test_language_save_failure_preserves_current_language(app, tab_window, monkeypatch):
    from omabridge.i18n import language
    window = tab_window
    errors = []
    window.show_error = errors.append
    def fail(_):
        raise OSError('Disk full')
    monkeypatch.setattr(window.preferences, 'save', fail)
    window.change_language('de')
    assert errors and language() == 'en'
    assert window.settings_action.text() == 'Settings'


def test_cancel_language_settings_does_not_change_preference(app, tab_window):
    from omabridge.i18n import language
    def cancel():
        dialog = QApplication.activeModalWidget()
        dialog.language.setCurrentIndex(1)
        dialog.reject()
    QTimer.singleShot(0, cancel)
    tab_window.open_settings()
    assert language() == 'en'
    assert not tab_window.preferences.path.exists()


def test_totp_storage_is_opt_in_and_warning_follows_input(app):
    dialog = SiteDialog(None)
    dialog.name.setText('Demo')
    dialog.url.setText('https://citrix.test')
    dialog.username.setText('demo-user')
    dialog.password.setText('test-password')
    assert not dialog.store_totp.isChecked()
    assert not dialog.totp.isEnabled() and dialog.totp_warning.isHidden()
    dialog.store_totp.setChecked(True)
    dialog.totp.setText('GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ')
    assert not dialog.totp_warning.isHidden()
    assert 'insecure' in dialog.totp_warning.text()
    assert 'your responsibility' in dialog.totp_warning.text()
    dialog.store_totp.setChecked(False)
    assert dialog.totp_warning.isHidden()
    dialog.validate()
    assert dialog.value[1] == Credentials('demo-user', 'test-password', '')
    dialog.deleteLater()


def test_disabling_totp_removes_only_saved_secret(app, tmp_path):
    site = Site('Demo', 'https://citrix.test')
    credentials = Credentials('demo-user', 'test-password', 'GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ')
    store, vault = SiteStore(tmp_path), MemoryVault()
    store.save([site])
    vault.set(site.id, credentials)
    window = MainWindow(store, vault)
    def disable():
        dialog = QApplication.activeModalWidget()
        assert dialog.store_totp.isChecked()
        assert not dialog.totp_warning.isHidden()
        dialog.store_totp.setChecked(False)
        dialog.validate()
    QTimer.singleShot(0, disable)
    window.edit_dialog(site, credentials)
    wait_for(app, lambda: not window.jobs)
    assert vault.get(site.id) == Credentials('demo-user', 'test-password', '')
    assert store.load() == [site]
    window.close()


def test_totp_warning_is_available_in_german(app):
    from omabridge.i18n import set_language
    set_language('de')
    dialog = SiteDialog(None, credentials=Credentials(totp='GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ'))
    assert 'optional' in dialog.store_totp.text()
    assert 'unsicher' in dialog.totp_warning.text()
    assert 'Verantwortung liegt bei dir' in dialog.totp_warning.text()
    dialog.close()
    dialog.deleteLater()


def test_bar_launch_waits_for_edit_dialog_and_save(app, tab_window, monkeypatch):
    window = tab_window
    first, second = window.sites
    saving, release = threading.Event(), threading.Event()
    original_set = window.vault.set
    opened = []
    def slow_save(key, value):
        saving.set()
        assert release.wait(5)
        original_set(key, value)
    monkeypatch.setattr(window.vault, 'set', slow_save)
    monkeypatch.setattr(window, 'connect_site', lambda: opened.append(window.current_site().id))
    observations = []
    def request_while_editing():
        window.open_site_id(second.id)
        observations.append((window.pending_site_id, len(window.jobs), list(opened)))
        enter_site('Updated demo')
    QTimer.singleShot(0, request_while_editing)
    try:
        window.edit_dialog(first, Credentials())
        wait_for(app, saving.is_set)
        assert observations == [(second.id, 0, [])]
        assert len(window.jobs) == 1 and window.mutating
        window.open_pending_site()
        assert not opened
        window.lock_config = {'enabled': True}
        window.lock_app()
        assert not window.locked  # Saving still owns the mutation guard.
        release.set()
        wait_for(app, lambda: bool(opened))
        assert opened == [second.id] and not window.jobs
    finally:
        release.set()
        wait_for(app, lambda: not window.jobs)


@pytest.mark.parametrize('unlock_again', [False, True])
def test_late_credentials_cannot_start_a_session_after_lock(app, tab_window, monkeypatch, unlock_again):
    window = tab_window
    sites = list(window.sites)
    callbacks = []
    monkeypatch.setattr(window, 'run_job', lambda operation, callback: callbacks.append(callback))
    window.connect_site()
    assert len(callbacks) == 1
    window.lock_config = {'enabled': True}
    window.lock_app()
    assert window.locked and not window.sessions
    if unlock_again:
        # A callback from the old unlocked generation is also stale after unlock.
        window.locked = False
        window.sites = sites
    callbacks[0](Credentials('demo-user', 'demo-password'), None)
    assert not window.sessions
