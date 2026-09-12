from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal
from PySide6.QtGui import QAction, QActionGroup, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMenu,
    QMessageBox, QPushButton, QScrollArea, QStackedWidget, QTabBar,
    QToolButton, QVBoxLayout, QWidget, QSizePolicy,
)

from .browser import PortalPage, PortalSession, display_address
from PySide6.QtWebEngineWidgets import QWebEngineView
from .launcher import workspace_executable
from .models import Credentials, Site, origin
from .storage import SecretVault, SiteStore
from .totp import Totp

STYLE = """
QWidget { background: #151f2c; color: #dce7f5; font-size: 14px; }
QLabel { background: transparent; }
QLabel#brand { font-size: 26px; font-weight: 700; letter-spacing: 1px; }
QLabel#title { font-size: 24px; font-weight: 600; }
QLabel#muted { color: #9bafc5; }
QLabel#status { color: #b6cee8; padding: 10px 16px; background: #1d2b3b; }
QLabel#emptyTitle { font-size: 30px; font-weight: 600; }
QLabel#connectionMark { color: #8fb9e8; font-family: monospace; font-size: 52px; }
QPushButton { background: #26384d; border: 1px solid #3c516a; border-radius: 6px; padding: 9px 14px; }
QPushButton:hover { background: #344b65; }
QPushButton:focus { border: 2px solid #8fb9e8; }
QPushButton:disabled { color: #9bafc5; background: #1d2b3b; border-color: #26384d; }
QPushButton#primary { background: #8fb9e8; color: #151f2c; border-color: #8fb9e8; font-weight: 600; }
QPushButton#primary:hover { background: #b0d0f2; }
QPushButton#primary:disabled { color: #9bafc5; background: #26384d; border-color: #3c516a; }
QLineEdit, QComboBox { background: #1d2b3b; border: 1px solid #3c516a; border-radius: 5px; padding: 9px; }
QLineEdit:focus, QComboBox:focus { border-color: #8fb9e8; }
QComboBox QAbstractItemView { selection-background-color: #344b65; }
QListWidget { border: none; outline: none; background: transparent; }
QListWidget::item { border: 1px solid transparent; border-radius: 6px; padding: 15px 10px; margin: 3px 0; }
QListWidget::item:selected { background: #26384d; border-color: #587a9f; }
QListWidget::item:hover { background: #1d2b3b; }
QCheckBox { spacing: 9px; padding: 5px 0; }
QScrollArea { border: none; }
QWidget#navigation { background: #1d2b3b; }
QToolButton { background: transparent; color: #dce7f5; border: 0; border-radius: 4px; padding: 0; font-size: 18px; }
QToolButton:hover, QToolButton:checked { background: #344b65; }
QToolButton:disabled { color: #607489; }
QToolButton:focus { border: 1px solid #8fb9e8; }
QToolButton::menu-indicator { image: none; width: 0; }
QTabBar { background: #1d2b3b; }
QTabBar::tab { background: #1d2b3b; color: #9bafc5; min-width: 85px; max-width: 210px; height: 34px; padding: 0 10px; border: 0; border-bottom: 2px solid transparent; }
QTabBar::tab:selected { background: #26384d; color: #dce7f5; border-bottom-color: #8fb9e8; }
QTabBar::tab:hover { background: #26384d; }
QTabBar::close-button { image: url("@ASSET_ROOT@/close.svg"); width: 16px; height: 16px; }
QTabBar::close-button:hover { background: #344b65; border-radius: 3px; }
QMenu { background: #1d2b3b; border: 1px solid #3c516a; padding: 5px; }
QMenu::item { padding: 8px 26px; }
QMenu::item:selected { background: #344b65; }
QMenu::item:disabled { color: #607489; }
QMenu::separator { background: #3c516a; height: 1px; margin: 5px; }
QToolTip { color: #dce7f5; background: #26384d; border: 1px solid #587a9f; padding: 6px; }
"""


class Result(QObject):
    finished = Signal(object, object)


class Job(QRunnable):
    def __init__(self, operation, callback):
        super().__init__()
        self.operation = operation
        self.result = Result()
        self.result.finished.connect(callback)

    def run(self):
        try:
            result, error = self.operation(), None
        except Exception as caught:
            result, error = None, caught
        self.result.finished.emit(result, error)


def label(text, name=None):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(True)
    if name:
        widget.setObjectName(name)
    return widget


def button(text, action, primary=False):
    widget = QPushButton(text)
    if primary:
        widget.setObjectName("primary")
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    widget.clicked.connect(action)
    return widget


class SiteDialog(QDialog):
    def __init__(self, parent, site=None, credentials=None):
        super().__init__(parent)
        self.site = site
        self.value = None
        credentials = credentials or Credentials()
        self.setWindowTitle("Site bearbeiten" if site else "Citrix-Site hinzufügen")
        self.resize(640, 760)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.addWidget(label("Site bearbeiten" if site else "Dein nächster Arbeitsplatz", "title"))
        outer.addWidget(label("StoreFront-Zugang und Startmodus an einem Ort.", "muted"))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        form = QFormLayout(body)
        form.setVerticalSpacing(16)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.name = QLineEdit(site.name if site else "")
        self.name.setPlaceholderText("z. B. Büro oder Kunde")
        self.url = QLineEdit(site.url if site else "")
        self.url.setPlaceholderText("https://citrix.firma.de/Citrix/StoreWeb/")
        self.username = QLineEdit(credentials.username)
        self.username.setPlaceholderText("DOMÄNE\\Benutzer oder name@firma.de")
        self.password = QLineEdit(credentials.password)
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.totp = QLineEdit(credentials.totp)
        self.totp.setEchoMode(QLineEdit.EchoMode.Password)
        self.totp.setPlaceholderText("Base32-Schlüssel oder otpauth://totp/…")
        self.mode = QComboBox()
        self.mode.addItem("Citrix Workspace App", "workspace")
        self.mode.addItem("Browser · HTML5 in OmaBridge", "browser")
        self.mode.setCurrentIndex(1 if site and site.mode == "browser" else 0)
        self.auto = QCheckBox("Nach Auswahl der Site automatisch anmelden")
        self.auto.setChecked(site.auto_login if site else True)
        for text, widget in [("Name", self.name), ("Portal-URL", self.url), ("Benutzername", self.username),
                             ("Passwort", self.password), ("TOTP-Schlüssel", self.totp), ("Öffnen mit", self.mode)]:
            form.addRow(text, widget)
            widget.setAccessibleName(text)
        form.addRow("", label("Gespeichert wird der TOTP-Schlüssel. Daraus entsteht bei jeder Anmeldung ein neuer Einmalcode.", "muted"))
        form.addRow("", self.auto)
        form.addRow("", label("Benutzername, Passwort und TOTP bleiben im Linux-Schlüsselbund. Leere Geheimnisfelder entfernen den bisherigen Wert.", "muted"))
        self.advanced = QCheckBox("Anmeldeformular anpassen")
        form.addRow("", self.advanced)
        advanced = QWidget()
        advanced_form = QFormLayout(advanced)
        advanced_form.setContentsMargins(0, 0, 0, 0)
        self.selectors = {}
        for role, title, placeholder in [
            ("username", "Benutzername", "Automatisch · z. B. #username"),
            ("password", "Passwort", "Automatisch · z. B. #password"),
            ("otp", "TOTP", "Automatisch · z. B. #otp"),
            ("submit", "Anmelde-Button", "Automatisch · z. B. #loginBtn"),
            ("browser", "Browser-Auswahl", "Optionaler CSS-Selektor"),
            ("workspace", "Workspace-Auswahl", "Optionaler CSS-Selektor"),
        ]:
            entry = QLineEdit(site.selectors.get(role, "") if site else "")
            entry.setPlaceholderText(placeholder)
            entry.setAccessibleName(title + " CSS-Selektor")
            self.selectors[role] = entry
            advanced_form.addRow(title, entry)
        advanced_form.addRow(label("Nur nötig, wenn dein Portal andere Feldnamen oder Startmodus-Schaltflächen verwendet.", "muted"))
        form.addRow(advanced)
        advanced.setVisible(False)
        self.advanced.toggled.connect(advanced.setVisible)
        if site and site.selectors:
            self.advanced.setChecked(True)
        scroll.setWidget(body)
        outer.addWidget(scroll)
        self.error = label("", "muted")
        outer.addWidget(self.error)
        actions = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        actions.button(QDialogButtonBox.StandardButton.Save).setText("Site speichern")
        actions.button(QDialogButtonBox.StandardButton.Save).setObjectName("primary")
        actions.button(QDialogButtonBox.StandardButton.Cancel).setText("Abbrechen")
        actions.accepted.connect(self.validate)
        actions.rejected.connect(self.reject)
        outer.addWidget(actions)

    def validate(self):
        try:
            data = dict(name=self.name.text(), url=self.url.text(), mode=self.mode.currentData(),
                        auto_login=self.auto.isChecked(), selectors={k: w.text().strip() for k, w in self.selectors.items() if w.text().strip()})
            if self.site:
                data["id"] = self.site.id
            site = Site(**data)
            credentials = Credentials(self.username.text().strip(), self.password.text(), self.totp.text().strip())
            if credentials.totp:
                Totp.parse(credentials.totp)
            self.value = site, credentials
        except ValueError as error:
            self.error.setText(str(error))
            return
        self.accept()


class StatusNotice(QToolButton):
    """Connection details live in the top row, never over the remote screen."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.message = "Bereit. Site auswählen oder mit + hinzufügen."
        self.address = ""
        self.setFixedSize(30, 30)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.setStyleSheet("QToolButton:enabled { color: #dce7f5; }")
        super().setText("ⓘ")
        self.setAccessibleName("Verbindungsstatus und Portal-Adresse")
        self.clicked.connect(self.show_details)
        self.refresh_tooltip()

    def setText(self, message):
        self.message = message
        self.refresh_tooltip()

    def set_address(self, address):
        self.address = address
        self.refresh_tooltip()

    def refresh_tooltip(self):
        self.setToolTip((self.address + "\n\n" if self.address else "") + self.message)

    def show_details(self):
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Verbindungsstatus")
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setText(self.toolTip())
        dialog.exec()


class MainWindow(QMainWindow):
    def __init__(self, store=None, vault=None):
        super().__init__()
        self.store = store or SiteStore()
        self.vault = vault or SecretVault()
        self.sites = self.store.load()
        self.sessions = {}
        self.popup_tabs = {}
        self.hidden_sites = set()
        self.messages = {}
        self.jobs = set()
        self.mutating = False
        self.setWindowTitle("OmaBridge")
        self.setWindowIcon(QIcon(str(Path(__file__).parent / "assets/omabridge.svg")))
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.resize(1320, 870)
        self.setMinimumSize(640, 400)
        self.setStyleSheet(STYLE.replace("@ASSET_ROOT@", str(Path(__file__).parent / "assets")))
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.toolbar = QWidget()
        self.toolbar.setObjectName("navigation")
        self.toolbar.setFixedHeight(42)
        row = QHBoxLayout(self.toolbar)
        row.setContentsMargins(6, 3, 6, 3)
        row.setSpacing(3)
        self.back_button = self.nav_button("←", "Zurück (Alt+Links)", lambda: self.navigate("back"))
        self.forward_button = self.nav_button("→", "Vorwärts (Alt+Rechts)", lambda: self.navigate("forward"))
        self.reload_button = self.nav_button("↻", "Neu laden (Ctrl+R)", lambda: self.navigate("reload"))
        for control in (self.back_button, self.forward_button, self.reload_button):
            row.addWidget(control)
        self.tabs = QTabBar()
        self.tabs.setAccessibleName("Citrix-Sites und Sitzungen")
        self.tabs.setExpanding(False)
        self.tabs.setMovable(False)
        self.tabs.setTabsClosable(True)
        self.tabs.setElideMode(Qt.TextElideMode.ElideRight)
        self.tabs.setUsesScrollButtons(True)
        self.tabs.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.tabs.currentChanged.connect(lambda index: self.selected(index, connect=True))
        self.tabs.tabBarClicked.connect(lambda _: self.connect_site())
        self.tabs.tabCloseRequested.connect(self.close_tab)
        row.addWidget(self.tabs, 1)
        self.add_button = self.nav_button("+", "Site hinzufügen (Ctrl+T)", self.add_site)
        row.addWidget(self.add_button)
        self.status = StatusNotice()
        row.addWidget(self.status)
        self.menu_button = self.nav_button("⋮", "OmaBridge-Menü", lambda: None)
        self.menu_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.menu = QMenu(self)
        self.menu_button.setMenu(self.menu)
        row.addWidget(self.menu_button)
        self.sites_menu = self.menu.addMenu("Gespeicherte Sites")
        self.sites_menu.aboutToShow.connect(self.populate_sites_menu)
        self.edit_action = self.add_action("Site bearbeiten …", self.edit_site)
        self.delete_action = self.add_action("Site entfernen …", self.delete_site)
        self.connect_action = self.add_action("Portal öffnen", self.connect_site)
        mode_menu = self.menu.addMenu("Öffnen mit")
        self.mode_group = QActionGroup(self)
        self.mode_group.setExclusive(True)
        self.mode_actions = {}
        for title, mode in (("Citrix Workspace", "workspace"), ("Browser · HTML5", "browser")):
            action = mode_menu.addAction(title)
            action.setCheckable(True)
            self.mode_group.addAction(action)
            action.triggered.connect(lambda checked=False, mode=mode: self.change_mode(mode))
            self.mode_actions[mode] = action
        self.menu.addSeparator()
        self.retry_action = self.add_action("Anmeldung erneut", self.retry)
        self.pause_action = self.add_action("Automatik pausieren", self.pause)
        self.close_action = self.add_action("Tab schließen", self.close_current_tab, "Ctrl+W")
        self.menu.addSeparator()
        self.add_action("Vollbild", self.toggle_fullscreen, "F11")
        self.add_action("Beenden", self.close, "Ctrl+Q")
        self.add_action("", self.add_site, "Ctrl+T", visible=False)
        self.add_action("", lambda: self.navigate("back"), "Alt+Left", visible=False)
        self.add_action("", lambda: self.navigate("forward"), "Alt+Right", visible=False)
        self.add_action("", lambda: self.navigate("reload"), "Ctrl+R", visible=False)
        self.add_action("", lambda: self.cycle_tab(1), "Ctrl+Tab", visible=False)
        self.add_action("", lambda: self.cycle_tab(-1), "Ctrl+Shift+Tab", visible=False)
        layout.addWidget(self.toolbar)
        self.stack = QStackedWidget()
        self.stack.setContentsMargins(0, 0, 0, 0)
        self.empty = QWidget()
        empty_layout = QVBoxLayout(self.empty)
        empty_layout.setContentsMargins(24, 24, 24, 24)
        empty_layout.addStretch()
        self.empty_title = label("OmaBridge", "title")
        self.empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(self.empty_title)
        self.empty_hint = label("Wähle oben eine Site oder füge mit + einen Zugang hinzu.", "muted")
        self.empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(self.empty_hint)
        self.empty_connect = button("Portal öffnen", self.connect_site)
        empty_layout.addWidget(self.empty_connect, 0, Qt.AlignmentFlag.AlignHCenter)
        empty_layout.addStretch()
        self.stack.addWidget(self.empty)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(root)
        self.refresh()

    def nav_button(self, text, tooltip, action):
        control = QToolButton()
        control.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        control.setStyleSheet("QToolButton:enabled { color: #dce7f5; }")
        control.setText(text)
        control.setToolTip(tooltip)
        control.setAccessibleName(tooltip)
        control.setFixedSize(30, 30)
        control.clicked.connect(action)
        return control

    def add_action(self, text, callback, shortcut=None, visible=True):
        action = QAction(text, self)
        action.triggered.connect(lambda checked=False: callback())
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        self.addAction(action)
        if visible:
            self.menu.addAction(action)
        return action

    def run_job(self, operation, callback):
        self.mutating = True
        self.set_controls()
        def finished(result, error):
            self.mutating = False
            self.jobs.discard(job)
            self.set_controls()
            callback(result, error)
        job = Job(operation, finished)
        self.jobs.add(job)
        QThreadPool.globalInstance().start(job)

    def current_key(self):
        return self.tabs.tabData(self.tabs.currentIndex())

    def current_site(self):
        key = self.current_key()
        site_id = self.popup_tabs[key][0] if key in self.popup_tabs else key
        return next((site for site in self.sites if site.id == site_id), None)

    def current_view(self):
        key = self.current_key()
        if key in self.popup_tabs:
            return self.popup_tabs[key][1]
        session = self.sessions.get(key)
        return session.view if session else None

    def set_controls(self):
        site = self.current_site()
        enabled = bool(site) and not self.mutating
        for action in (self.edit_action, self.delete_action, self.connect_action, *self.mode_actions.values()):
            action.setEnabled(enabled)
        for action in (self.retry_action, self.pause_action):
            action.setEnabled(enabled and site.id in self.sessions if site else False)
        self.close_action.setEnabled(bool(self.tabs.count()) and not self.mutating)
        self.add_button.setEnabled(not self.mutating)
        self.tabs.setEnabled(not self.mutating)
        view = self.current_view()
        self.back_button.setEnabled(bool(view) and view.history().canGoBack() and not self.mutating)
        self.forward_button.setEnabled(bool(view) and view.history().canGoForward() and not self.mutating)
        self.reload_button.setEnabled(bool(view) and not self.mutating)
        self.empty_connect.setEnabled(enabled)
        self.empty_connect.setVisible(bool(site))
        if site:
            self.mode_actions[site.mode].setChecked(True)

    def refresh(self, site_id=None):
        key = site_id or self.current_key()
        if site_id:
            self.hidden_sites.discard(site_id)
        self.tabs.blockSignals(True)
        while self.tabs.count():
            self.tabs.removeTab(0)
        selected = 0
        for site in self.sites:
            if site.id in self.hidden_sites:
                continue
            index = self.tabs.addTab(site.name)
            self.tabs.setTabData(index, site.id)
            self.tabs.setTabToolTip(index, site.url)
            if key == site.id:
                selected = index
        for token, (owner, view) in self.popup_tabs.items():
            index = self.tabs.addTab(view.title() or "Citrix-Sitzung")
            self.tabs.setTabData(index, token)
            if key == token:
                selected = index
        self.tabs.setCurrentIndex(selected if self.tabs.count() else -1)
        self.tabs.blockSignals(False)
        self.selected(self.tabs.currentIndex())

    def selected(self, _, connect=False):
        site, key = self.current_site(), self.current_key()
        page = self.popup_tabs[key][1] if key in self.popup_tabs else self.sessions.get(key)
        self.stack.setCurrentWidget(page or self.empty)
        self.setWindowTitle((site.name + " · OmaBridge") if site else "OmaBridge")
        self.empty_title.setText(site.name if site else "OmaBridge")
        self.empty_hint.setText("Site-Tab anklicken oder Portal öffnen." if site else "Wähle eine gespeicherte Site im Menü oder füge mit + einen Zugang hinzu.")
        view = self.current_view()
        self.status.set_address(display_address(view.url()) if view else (site.url if site else ""))
        self.status.setText(self.messages.get(site.id, "Bereit.") if site else "Bereit.")
        self.set_controls()
        if connect and site and not page:
            self.connect_site()

    def populate_sites_menu(self):
        self.sites_menu.clear()
        for site in self.sites:
            action = self.sites_menu.addAction(site.name)
            action.triggered.connect(lambda checked=False, site_id=site.id: self.open_site_id(site_id))
        if not self.sites:
            self.sites_menu.addAction("Noch keine Sites gespeichert").setEnabled(False)

    def show_session_message(self, site_id, text):
        self.messages[site_id] = text
        site = self.current_site()
        if site and site.id == site_id:
            self.status.setText(text)

    def view_changed(self, view):
        if self.current_view() is view:
            self.status.set_address(display_address(view.url()))
            self.set_controls()

    def navigate(self, action):
        view = self.current_view()
        if view:
            getattr(view, action)()

    def cycle_tab(self, step):
        if self.tabs.count() and not self.mutating:
            self.tabs.setCurrentIndex((self.tabs.currentIndex() + step) % self.tabs.count())

    def toggle_fullscreen(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def open_popup(self, session):
        view = QWebEngineView(self.stack)
        page = PortalPage(session.profile, session, view)
        view.setPage(page)
        token = "session:" + str(uuid4())
        self.popup_tabs[token] = (session.site.id, view)
        session.popups.append(view)
        self.stack.addWidget(view)
        self.tabs.blockSignals(True)
        index = self.tabs.addTab("Citrix-Sitzung")
        self.tabs.setTabData(index, token)
        self.tabs.setCurrentIndex(index)
        self.tabs.blockSignals(False)
        view.titleChanged.connect(lambda title: self.popup_title(token, title))
        view.urlChanged.connect(lambda _: self.view_changed(view))
        view.loadFinished.connect(lambda _: self.view_changed(view))
        self.selected(index)
        return page

    def popup_title(self, token, title):
        for index in range(self.tabs.count()):
            if self.tabs.tabData(index) == token:
                self.tabs.setTabText(index, title[:100] or "Citrix-Sitzung")
                break

    def close_popup(self, view):
        token = next((key for key, (_, candidate) in self.popup_tabs.items() if candidate is view), None)
        if token is None:
            return
        was_current = self.current_key() == token
        owner, _ = self.popup_tabs.pop(token)
        session = self.sessions.get(owner)
        if session and view in session.popups:
            session.popups.remove(view)
        self.stack.removeWidget(view)
        view.stop()
        view.page().deleteLater()
        view.deleteLater()
        self.refresh(owner if was_current and owner not in self.hidden_sites else None)

    def close_current_tab(self):
        self.close_tab(self.tabs.currentIndex())

    def close_tab(self, index):
        if index < 0 or self.mutating:
            return
        key = self.tabs.tabData(index)
        if key in self.popup_tabs:
            self.close_popup(self.popup_tabs[key][1])
        else:
            self.hidden_sites.add(key)
            self.remove_session(key)
            self.refresh()

    def show_error(self, error):
        self.status.setText(str(error))
        box = QMessageBox(self)
        box.setWindowTitle("OmaBridge")
        box.setIcon(QMessageBox.Icon.Warning)
        box.setTextFormat(Qt.TextFormat.PlainText)
        box.setText(str(error))
        box.exec()

    def add_site(self):
        if self.mutating:
            return
        self.edit_dialog()

    def edit_site(self):
        site = self.current_site()
        if not site or self.mutating:
            return
        self.status.setText("Zugangsdaten aus dem Schlüsselbund laden …")
        self.run_job(lambda: self.vault.get(site.id), lambda credentials, error:
                     self.show_error(error) if error else self.edit_dialog(site, credentials))

    def edit_dialog(self, site=None, credentials=None):
        dialog = SiteDialog(self, site, credentials)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            dialog.deleteLater()
            return
        updated, secrets = dialog.value
        dialog.value = None
        dialog.password.clear()
        dialog.totp.clear()
        dialog.deleteLater()
        new_sites = [updated if s.id == updated.id else s for s in self.sites]
        if site is None:
            new_sites.append(updated)
        def save():
            self.vault.set(updated.id, secrets)
            try:
                self.store.save(new_sites)
            except Exception:
                if site:
                    self.vault.set(site.id, credentials)
                else:
                    self.vault.delete(updated.id)
                raise
        def done(_, error):
            if error:
                self.show_error(error)
                return
            self.remove_session(updated.id)
            self.sites = new_sites
            self.refresh(updated.id)
            self.status.setText("Site gespeichert. Zum Öffnen den Site-Tab anklicken.")
        self.status.setText("Im Schlüsselbund speichern …")
        self.run_job(save, done)

    def delete_site(self):
        site = self.current_site()
        if not site:
            return
        box = QMessageBox(self)
        box.setWindowTitle("Site entfernen")
        box.setTextFormat(Qt.TextFormat.PlainText)
        box.setText(f"„{site.name}“ und die zugehörigen Zugangsdaten entfernen?")
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        if box.exec() != QMessageBox.StandardButton.Yes:
            return
        new_sites = [s for s in self.sites if s.id != site.id]
        def remove():
            previous = self.vault.get(site.id)
            self.vault.delete(site.id)
            try:
                self.store.save(new_sites)
            except Exception:
                self.vault.set(site.id, previous)
                raise
        def done(_, error):
            if error:
                self.show_error(error)
                return
            self.remove_session(site.id)
            self.sites = new_sites
            self.refresh()
            self.status.setText("Site und Zugangsdaten entfernt.")
        self.run_job(remove, done)

    def change_mode(self, mode):
        site = self.current_site()
        if not site:
            return
        updated = replace(site, mode=mode)
        new_sites = [updated if s.id == site.id else s for s in self.sites]
        try:
            self.store.save(new_sites)
        except OSError as error:
            self.selected(0)
            self.show_error(error)
            return
        self.sites = new_sites
        session = self.sessions.get(site.id)
        if session:
            session.site = updated
        self.refresh(site.id)
        self.status.setText("Startmodus gespeichert. Falls das Portal bereits einen Client gewählt hat, dort den Startmodus ebenfalls umstellen.")

    def connect_site(self):
        site = self.current_site()
        if not site or self.mutating:
            return
        if site.id in self.sessions:
            self.selected(self.tabs.currentIndex())
            return
        if site.mode == "workspace" and not workspace_executable():
            self.status.setText("Citrix Workspace ist nicht installiert. Du kannst dich anmelden; zum Starten Workspace installieren oder Browser-Modus wählen.")
        def connected(credentials, error):
            if error:
                self.show_error(error)
                return
            try:
                session = PortalSession(site, credentials, self)
            except ValueError as error:
                self.show_error(error)
                return
            self.sessions[site.id] = session
            session.popup_factory = self.open_popup
            session.popup_closer = self.close_popup
            session.message.connect(lambda text: self.show_session_message(site.id, text))
            session.view.urlChanged.connect(lambda _: self.view_changed(session.view))
            session.view.loadFinished.connect(lambda _: self.view_changed(session.view))
            self.stack.addWidget(session)
            self.stack.setCurrentWidget(session)
            session.start()
            self.set_controls()
        self.status.setText("Schlüsselbund öffnen …")
        self.run_job(lambda: self.vault.get(site.id), connected)

    def open_site_id(self, site_id):
        if self.mutating:
            return
        # Reload so changes from the bar's on-disk list are reflected.
        self.sites = self.store.load()
        if not any(site.id == site_id for site in self.sites):
            self.status.setText("Diese Site wurde nicht gefunden.")
            return
        self.refresh(site_id)
        if self.current_site():
            self.connect_site()
        else:
            self.status.setText("Diese Site wurde nicht gefunden.")

    def retry(self):
        site = self.current_site()
        if site and site.id in self.sessions:
            self.sessions[site.id].retry()

    def pause(self):
        site = self.current_site()
        if site and site.id in self.sessions:
            self.sessions[site.id].pause()

    def remove_session(self, site_id):
        session = self.sessions.get(site_id)
        if session:
            for popup in session.popups[:]:
                self.close_popup(popup)
            self.sessions.pop(site_id, None)
            self.stack.removeWidget(session)
            session.dispose()
            session.deleteLater()

    def close_session(self):
        site = self.current_site()
        if site:
            self.remove_session(site.id)
            self.selected(0)
            self.status.setText("Lokale Portal-Sitzung geschlossen. Workspace-Sitzungen laufen separat weiter. Serverseitig bei Bedarf im Citrix-Portal abmelden.")

    def closeEvent(self, event):
        if self.jobs:
            self.status.setText("Bitte warten, bis der Schlüsselbund-Vorgang abgeschlossen ist.")
            event.ignore()
            return
        for site_id in list(self.sessions):
            self.remove_session(site_id)
        event.accept()
