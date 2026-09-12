from .i18n import tr, language, set_language, retranslate, apply_qt_language, ENGLISH
from .preferences import PreferencesStore
from .app_lock import AppLockStore
from .theme import ThemeWatcher, stylesheet, qt_palette

from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Qt, Signal
from PySide6.QtGui import QAction, QActionGroup, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
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
        self.setWindowTitle(tr("Edit site") if site else tr("Add Citrix site"))
        self.resize(640, 760)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.addWidget(label(tr("Edit site") if site else tr("Your next workspace"), "title"))
        outer.addWidget(label(tr("StoreFront credentials and launch mode in one place."), "muted"))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        form = QFormLayout(body)
        form.setVerticalSpacing(16)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.name = QLineEdit(site.name if site else "")
        self.name.setPlaceholderText(tr("e.g. Office or Customer"))
        self.url = QLineEdit(site.url if site else "")
        self.url.setPlaceholderText("https://citrix.firma.de/Citrix/StoreWeb/")
        self.username = QLineEdit(credentials.username)
        self.username.setPlaceholderText(tr("DOMAIN\\user or name@company.com"))
        self.password = QLineEdit(credentials.password)
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.totp = QLineEdit(credentials.totp)
        self.totp.setEchoMode(QLineEdit.EchoMode.Password)
        self.totp.setPlaceholderText(tr("Base32 secret or otpauth://totp/…"))
        self.store_totp = QCheckBox(tr("Store TOTP secret (optional)"))
        self.store_totp.setChecked(bool(credentials.totp))
        self.mode = QComboBox()
        self.mode.addItem("Citrix Workspace App", "workspace")
        self.mode.addItem(tr("Browser · HTML5 in OmaBridge"), "browser")
        self.mode.setCurrentIndex(1 if site and site.mode == "browser" else 0)
        self.auto = QCheckBox(tr("Sign in automatically when selecting a site"))
        self.auto.setChecked(site.auto_login if site else True)
        for text, widget in [("Name", self.name), (tr("Portal URL"), self.url), (tr("Username"), self.username),
                             (tr("Password"), self.password)]:
            form.addRow(text, widget)
            widget.setAccessibleName(text)
        form.addRow("", self.store_totp)
        form.addRow(tr("TOTP secret"), self.totp)
        self.totp.setAccessibleName(tr("TOTP secret"))
        form.addRow("", label(tr("Leave this off to enter verification codes manually in the portal. Turning it off and saving removes an existing TOTP secret."), "muted"))
        self.totp_warning = label(tr("Storing TOTP secrets alongside passwords is insecure: access to both can defeat two-factor authentication. Only use this option if you accept the risk; it is your responsibility."))
        self.totp_warning.setObjectName("totpWarning")
        self.totp_warning.setAccessibleName(tr("TOTP security warning"))
        self.totp_warning.setAccessibleDescription(self.totp_warning.text())
        form.addRow("", self.totp_warning)
        self.store_totp.toggled.connect(self.update_totp_state)
        self.totp.textChanged.connect(self.update_totp_state)
        self.update_totp_state()
        form.addRow(tr("Open with"), self.mode)
        self.mode.setAccessibleName(tr("Open with"))
        form.addRow("", self.auto)
        form.addRow("", label(tr("Username, password and TOTP are stored in the Linux keyring. Empty credential fields remove the saved value."), "muted"))
        self.advanced = QCheckBox(tr("Customize sign-in form"))
        form.addRow("", self.advanced)
        advanced = QWidget()
        advanced_form = QFormLayout(advanced)
        advanced_form.setContentsMargins(0, 0, 0, 0)
        self.selectors = {}
        for role, title, placeholder in [
            ("username", tr("Username"), tr("Automatic · e.g. #username")),
            ("password", tr("Password"), tr("Automatic · e.g. #password")),
            ("otp", "TOTP", tr("Automatic · e.g. #otp")),
            ("submit", tr("Sign-in button"), tr("Automatic · e.g. #loginBtn")),
            ("browser", tr("Browser selection"), tr("Optional CSS selector")),
            ("workspace", tr("Workspace selection"), tr("Optional CSS selector")),
        ]:
            entry = QLineEdit(site.selectors.get(role, "") if site else "")
            entry.setPlaceholderText(placeholder)
            entry.setAccessibleName(title + tr(" CSS selector"))
            self.selectors[role] = entry
            advanced_form.addRow(title, entry)
        advanced_form.addRow(label(tr("Only needed if your portal uses different field names or client selection buttons."), "muted"))
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
        actions.button(QDialogButtonBox.StandardButton.Save).setText(tr("Save site"))
        actions.button(QDialogButtonBox.StandardButton.Save).setObjectName("primary")
        actions.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Cancel"))
        actions.accepted.connect(self.validate)
        actions.rejected.connect(self.reject)
        outer.addWidget(actions)

    def update_totp_state(self, *_):
        enabled = self.store_totp.isChecked()
        self.totp.setEnabled(enabled)
        self.totp_warning.setVisible(enabled and bool(self.totp.text().strip()))

    def validate(self):
        try:
            data = dict(name=self.name.text(), url=self.url.text(), mode=self.mode.currentData(),
                        auto_login=self.auto.isChecked(), selectors={k: w.text().strip() for k, w in self.selectors.items() if w.text().strip()})
            if self.site:
                data["id"] = self.site.id
            site = Site(**data)
            credentials = Credentials(self.username.text().strip(), self.password.text(),
                                      self.totp.text().strip() if self.store_totp.isChecked() else "")
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
        self.message = tr("Ready. Select a site or add one with +.")
        self.address = ""
        self.setFixedSize(30, 30)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.setStyleSheet("QToolButton:enabled { color: #dce7f5; }")
        super().setText("ⓘ")
        self.setAccessibleName(tr("Connection status and portal address"))
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
        dialog.setWindowTitle(tr("Connection status"))
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setText(self.toolTip())
        dialog.setStandardButtons(QMessageBox.StandardButton.Ok)
        dialog.button(QMessageBox.StandardButton.Ok).setText(tr("OK"))
        dialog.exec()


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.lock_config = getattr(parent, "lock_config", None)
        self.setWindowTitle(tr("Settings"))
        self.setMinimumWidth(480)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.language = QComboBox()
        self.language.addItem("English", "en")
        self.language.addItem("Deutsch", "de")
        self.language.setCurrentIndex(self.language.findData(language()))
        self.language.setAccessibleName(tr("Language"))
        form.addRow(tr("Language"), self.language)
        layout.addLayout(form)
        layout.addWidget(label(tr("Applies immediately. Open Citrix sessions stay connected."), "muted"))
        layout.addWidget(label(tr("Colors follow your Omarchy theme and update live."), "muted"))
        self.lock_enabled = QCheckBox(tr("Require a PIN or password when opening OmaBridge"))
        self.lock_enabled.setChecked(bool(self.lock_config))
        layout.addWidget(self.lock_enabled)
        lock_form = QFormLayout()
        self.lock_kind = QComboBox()
        self.lock_kind.addItem(tr("PIN"), "pin")
        self.lock_kind.addItem(tr("Password"), "password")
        self.lock_kind.setCurrentIndex(self.lock_kind.findData(self.lock_config['kind'] if self.lock_config else 'pin'))
        self.current_secret = QLineEdit()
        self.new_secret = QLineEdit()
        self.confirm_secret = QLineEdit()
        for title, field in [("Current PIN or password", self.current_secret),
                             ("New PIN or password", self.new_secret),
                             ("Confirm PIN or password", self.confirm_secret)]:
            field.setEchoMode(QLineEdit.EchoMode.Password)
            field.setAccessibleName(tr(title))
        self.lock_kind.setAccessibleName(tr("App lock"))
        lock_form.addRow(tr("App lock"), self.lock_kind)
        lock_form.addRow(tr("Current PIN or password"), self.current_secret)
        lock_form.addRow(tr("New PIN or password"), self.new_secret)
        lock_form.addRow(tr("Confirm PIN or password"), self.confirm_secret)
        layout.addLayout(lock_form)
        layout.addWidget(label(tr("Choose any length. A longer password is safer than a short PIN. Leave new fields empty to keep your existing lock."), "muted"))
        layout.addWidget(label(tr("This locks OmaBridge, not your keyring or Linux account. Lock app closes local browser sessions; Workspace sessions continue separately."), "muted"))
        self.error = label("", "muted")
        layout.addWidget(self.error)
        self.lock_enabled.toggled.connect(self.update_lock_fields)
        self.update_lock_fields()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText(tr("Save"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Cancel"))
        buttons.accepted.connect(self.validate)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def update_lock_fields(self):
        self.current_secret.setEnabled(bool(self.lock_config))
        for field in (self.lock_kind, self.new_secret, self.confirm_secret):
            field.setEnabled(self.lock_enabled.isChecked())

    def lock_changed(self):
        return (self.lock_enabled.isChecked() != bool(self.lock_config) or
                self.lock_enabled.isChecked() and (bool(self.new_secret.text()) or
                self.lock_config and self.lock_kind.currentData() != self.lock_config['kind']))

    def validate(self):
        try:
            if self.lock_enabled.isChecked() and self.new_secret.text() != self.confirm_secret.text():
                raise ValueError(tr("The PINs or passwords do not match."))
            if self.lock_changed():
                if self.lock_config and not self.current_secret.text():
                    raise ValueError(tr("Enter your current PIN or password to change or disable the lock."))
                if self.lock_enabled.isChecked():
                    AppLockStore.validate_secret(self.new_secret.text(), self.lock_kind.currentData())
        except ValueError as error:
            self.error.setText(str(error))
            return
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self, store=None, vault=None):
        super().__init__()
        self.store = store or SiteStore()
        self.preferences = PreferencesStore(self.store.directory)
        set_language(self.preferences.load())
        apply_qt_language()
        self.lock_store = AppLockStore(self.store.directory)
        self.lock_config = self.lock_store.load()
        self.locked = bool(self.lock_config)
        self.pending_site_id = None
        self.pending_site_timer = QTimer(self)
        self.pending_site_timer.setInterval(100)
        self.pending_site_timer.timeout.connect(self.open_pending_site)
        self.session_generation = 0
        self.vault = vault or SecretVault()
        self.sites = [] if self.locked else self.store.load()
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
        self.back_button = self.nav_button("←", tr("Back (Alt+Left)"), lambda: self.navigate("back"))
        self.forward_button = self.nav_button("→", tr("Forward (Alt+Right)"), lambda: self.navigate("forward"))
        self.reload_button = self.nav_button("↻", tr("Reload (Ctrl+R)"), lambda: self.navigate("reload"))
        for control in (self.back_button, self.forward_button, self.reload_button):
            row.addWidget(control)
        self.tabs = QTabBar()
        self.tabs.setAccessibleName(tr("Citrix sites and sessions"))
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
        self.add_button = self.nav_button("+", tr("Add site (Ctrl+T)"), self.add_site)
        row.addWidget(self.add_button)
        self.status = StatusNotice()
        row.addWidget(self.status)
        self.menu_button = self.nav_button("⋮", tr("OmaBridge menu"), lambda: None)
        self.menu_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.menu = QMenu(self)
        self.menu_button.setMenu(self.menu)
        row.addWidget(self.menu_button)
        self.sites_menu = self.menu.addMenu(tr("Saved sites"))
        self.sites_menu.aboutToShow.connect(self.populate_sites_menu)
        self.edit_action = self.add_action(tr("Edit site …"), self.edit_site)
        self.delete_action = self.add_action(tr("Remove site …"), self.delete_site)
        self.connect_action = self.add_action(tr("Open portal"), self.connect_site)
        self.mode_menu = self.menu.addMenu(tr("Open with"))
        self.mode_group = QActionGroup(self)
        self.mode_group.setExclusive(True)
        self.mode_actions = {}
        for title, mode in (("Citrix Workspace", "workspace"), ("Browser · HTML5", "browser")):
            action = self.mode_menu.addAction(title)
            action.setCheckable(True)
            self.mode_group.addAction(action)
            action.triggered.connect(lambda checked=False, mode=mode: self.change_mode(mode))
            self.mode_actions[mode] = action
        self.menu.addSeparator()
        self.retry_action = self.add_action(tr("Retry sign-in"), self.retry)
        self.pause_action = self.add_action(tr("Pause automation"), self.pause)
        self.close_action = self.add_action(tr("Close tab"), self.close_current_tab, "Ctrl+W")
        self.menu.addSeparator()
        self.lock_action = self.add_action(tr("Lock app"), self.lock_app, "Ctrl+Shift+L")
        self.settings_action = self.add_action(tr("Settings"), self.open_settings)
        self.add_action(tr("Fullscreen"), self.toggle_fullscreen, "F11")
        self.add_action(tr("Quit"), self.close, "Ctrl+Q")
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
        self.empty_hint = label(tr("Select a site above or add one with +."), "muted")
        self.empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(self.empty_hint)
        self.empty_connect = button(tr("Open portal"), self.connect_site)
        empty_layout.addWidget(self.empty_connect, 0, Qt.AlignmentFlag.AlignHCenter)
        empty_layout.addStretch()
        self.stack.addWidget(self.empty)
        layout.addWidget(self.stack, 1)
        self.pages = QStackedWidget()
        self.pages.addWidget(root)
        self.build_lock_page()
        self.setCentralWidget(self.pages)
        self.pages.setCurrentIndex(1 if self.locked else 0)
        self.refresh()
        self.theme = ThemeWatcher(self)
        self.theme.changed.connect(self.apply_theme)
        self.theme.refresh()
        if self.locked:
            self.unlock_secret.setFocus()

    def apply_theme(self, colors):
        self.theme_colors = colors
        self.setPalette(qt_palette(colors))
        self.setStyleSheet(stylesheet(STYLE, colors))
        # Explicit local foreground keeps text-only navigation glyphs visible in Qt.
        for control in self.findChildren(QToolButton):
            control.setStyleSheet("QToolButton:enabled { color: " + colors['foreground'] + "; }")

    def add_tab_close(self, index):
        control = QToolButton(self.tabs)
        control.setText("×")
        control.setAccessibleName(tr("Close tab"))
        control.setFixedSize(18, 22)
        control.clicked.connect(lambda: self.close_tab(next((i for i in range(self.tabs.count())
            if self.tabs.tabButton(i, QTabBar.ButtonPosition.RightSide) is control), -1)))
        if hasattr(self, 'theme_colors'):
            control.setStyleSheet("QToolButton:enabled { color: " + self.theme_colors['foreground'] + "; }")
        self.tabs.setTabButton(index, QTabBar.ButtonPosition.RightSide, control)

    def build_lock_page(self):
        self.lock_page = QWidget()
        layout = QVBoxLayout(self.lock_page)
        layout.addStretch()
        panel = QWidget()
        panel.setMinimumWidth(360)
        panel.setMaximumWidth(440)
        form = QVBoxLayout(panel)
        title = label("OmaBridge", "title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        form.addWidget(title)
        self.lock_hint = label(tr("Enter your PIN or password to unlock."), "muted")
        form.addWidget(self.lock_hint)
        self.unlock_secret = QLineEdit()
        self.unlock_secret.setEchoMode(QLineEdit.EchoMode.Password)
        self.unlock_secret.setAccessibleName(tr("PIN or password"))
        self.unlock_secret.returnPressed.connect(self.unlock_app)
        form.addWidget(self.unlock_secret)
        self.unlock_button = button(tr("Unlock"), self.unlock_app, primary=True)
        form.addWidget(self.unlock_button)
        self.unlock_error = label("", "muted")
        form.addWidget(self.unlock_error)
        self.lock_quit = button(tr("Quit"), self.close)
        form.addWidget(self.lock_quit)
        layout.addWidget(panel, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch()
        self.pages.addWidget(self.lock_page)

    def unlock_app(self):
        secret = self.unlock_secret.text()
        self.unlock_secret.clear()
        self.unlock_with_secret(secret)

    def unlock_with_secret(self, secret, callback=None):
        def report(error=None):
            if error:
                self.unlock_error.setText(str(error))
                self.unlock_secret.setFocus()
            if callback:
                callback(error)
        if self.mutating:
            report(tr("Please wait for the current operation to finish."))
            return
        if not self.locked:
            report()
            return
        self.unlock_error.setText("")
        def done(valid, error):
            if error or not valid:
                report(error or tr("Incorrect PIN or password."))
                return
            try:
                sites = self.store.load()
            except (ValueError, OSError) as error:
                report(error)
                return
            self.sites = sites
            self.locked = False
            self.pages.setCurrentIndex(0)
            self.refresh()
            report()
            pending, self.pending_site_id = self.pending_site_id, None
            if pending:
                self.open_site_id(pending)
        self.run_job(lambda: self.lock_store.verify(secret), done)

    def lock_app(self):
        if self.locked or self.jobs or self.mutating or not self.lock_config:
            return
        # Dispose browser profiles and automation before hiding all site information.
        self.locked = True
        self.session_generation += 1
        self.pending_site_timer.stop()
        self.pages.setCurrentIndex(1)
        for site_id in list(self.sessions):
            self.remove_session(site_id)
        self.sites = []
        self.hidden_sites.clear()
        self.messages.clear()
        self.sites_menu.clear()
        self.pending_site_id = None
        self.unlock_secret.clear()
        self.unlock_error.clear()
        self.refresh()
        self.unlock_secret.setFocus()

    def nav_button(self, text, tooltip, action):
        control = QToolButton()
        control.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        control.setStyleSheet("QToolButton:enabled { color: #dce7f5; }")
        control.setText(text)
        control.setToolTip(tooltip)
        control.setAccessibleName(tooltip)
        control.source_tooltip = ENGLISH.get(tooltip, tooltip)
        control.setFixedSize(30, 30)
        control.clicked.connect(action)
        return control

    def add_action(self, text, callback, shortcut=None, visible=True):
        action = QAction(text, self)
        action.source_text = ENGLISH.get(text, text)
        action.triggered.connect(lambda checked=False: callback())
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        self.addAction(action)
        if visible:
            self.menu.addAction(action)
        return action

    def open_settings(self):
        if self.locked or self.mutating:
            return
        dialog = SettingsDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            value = dialog.language.currentData()
            if dialog.lock_changed():
                enabled, kind = dialog.lock_enabled.isChecked(), dialog.lock_kind.currentData()
                current, secret = dialog.current_secret.text(), dialog.new_secret.text()
                self.save_lock_settings(enabled, kind, current, secret, value)
            else:
                self.change_language(value)
        for field in (dialog.current_secret, dialog.new_secret, dialog.confirm_secret):
            field.clear()
        dialog.deleteLater()

    def save_lock_settings(self, enabled, kind, current, secret, selected_language):
        if self.locked or self.mutating:
            return
        def save():
            if self.lock_config and not self.lock_store.verify(current):
                raise ValueError(tr("Incorrect PIN or password."))
            if enabled:
                self.lock_store.configure(secret, kind)
            else:
                self.lock_store.disable()
            return self.lock_store.load()
        def done(config, error):
            if error:
                self.show_error(error)
                return
            self.lock_config = config
            self.change_language(selected_language)
            self.set_controls()
        self.run_job(save, done)

    def change_language(self, value):
        if self.locked or self.mutating:
            return
        # Persist first: a failed write leaves the current UI and preference intact.
        try:
            self.preferences.save(value)
        except (OSError, ValueError) as error:
            self.show_error(error)
            return
        set_language(value)
        apply_qt_language()
        for action in self.actions():
            if hasattr(action, "source_text"):
                action.setText(tr(action.source_text))
        for control in (self.back_button, self.forward_button, self.reload_button, self.add_button, self.menu_button):
            control.setToolTip(tr(control.source_tooltip))
            control.setAccessibleName(tr(control.source_tooltip))
        self.sites_menu.setTitle(tr("Saved sites"))
        self.mode_menu.setTitle(tr("Open with"))
        self.tabs.setAccessibleName(tr("Citrix sites and sessions"))
        self.status.setAccessibleName(tr("Connection status and portal address"))
        self.empty_connect.setText(tr("Open portal"))
        self.lock_hint.setText(tr("Enter your PIN or password to unlock."))
        self.unlock_secret.setAccessibleName(tr("PIN or password"))
        self.unlock_button.setText(tr("Unlock"))
        self.lock_quit.setText(tr("Quit"))
        self.messages = {key: retranslate(message) for key, message in self.messages.items()}
        self.refresh()
        self.status.setText(tr("Language changed."))

    def run_job(self, operation, callback):
        if self.jobs:
            raise RuntimeError("Background operations must be serialized.")
        self.mutating = True
        self.set_controls()
        def finished(result, error):
            self.jobs.discard(job)
            self.mutating = bool(self.jobs)
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
        enabled = bool(site) and not self.mutating and not self.locked
        for action in (self.edit_action, self.delete_action, self.connect_action, *self.mode_actions.values()):
            action.setEnabled(enabled)
        for action in (self.retry_action, self.pause_action):
            action.setEnabled(enabled and site.id in self.sessions if site else False)
        self.close_action.setEnabled(bool(self.tabs.count()) and not self.mutating)
        self.add_button.setEnabled(not self.mutating and not self.locked)
        self.settings_action.setEnabled(not self.mutating and not self.locked)
        self.lock_action.setEnabled(bool(self.lock_config) and not self.locked and not self.mutating)
        self.unlock_button.setEnabled(self.locked and not self.mutating)
        self.unlock_secret.setEnabled(self.locked and not self.mutating)
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
            self.add_tab_close(index)
            self.tabs.setTabData(index, site.id)
            self.tabs.setTabToolTip(index, site.url)
            if key == site.id:
                selected = index
        for token, (owner, view) in self.popup_tabs.items():
            index = self.tabs.addTab(view.title() or tr("Citrix session"))
            self.add_tab_close(index)
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
        self.empty_hint.setText(tr("Click the site tab or open the portal.") if site else tr("Choose a saved site from the menu or add one with +."))
        view = self.current_view()
        self.status.set_address(display_address(view.url()) if view else (site.url if site else ""))
        self.status.setText(self.messages.get(site.id, tr("Ready.")) if site else tr("Ready."))
        self.set_controls()
        if connect and site and not page:
            self.connect_site()

    def populate_sites_menu(self):
        self.sites_menu.clear()
        for site in self.sites:
            action = self.sites_menu.addAction(site.name)
            action.triggered.connect(lambda checked=False, site_id=site.id: self.open_site_id(site_id))
        if not self.sites:
            self.sites_menu.addAction(tr("No saved sites yet")).setEnabled(False)

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
        if self.locked or self.mutating:
            return
        view = self.current_view()
        if view:
            getattr(view, action)()

    def cycle_tab(self, step):
        if self.tabs.count() and not self.mutating:
            self.tabs.setCurrentIndex((self.tabs.currentIndex() + step) % self.tabs.count())

    def toggle_fullscreen(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def open_popup(self, session):
        if self.locked or self.mutating:
            return
        view = QWebEngineView(self.stack)
        page = PortalPage(session.profile, session, view)
        view.setPage(page)
        token = "session:" + str(uuid4())
        self.popup_tabs[token] = (session.site.id, view)
        session.popups.append(view)
        self.stack.addWidget(view)
        self.tabs.blockSignals(True)
        index = self.tabs.addTab(tr("Citrix session"))
        self.add_tab_close(index)
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
                self.tabs.setTabText(index, title[:100] or tr("Citrix session"))
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
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        box.button(QMessageBox.StandardButton.Ok).setText(tr("OK"))
        box.exec()

    def add_site(self):
        if self.locked or self.mutating:
            return
        self.edit_dialog()

    def edit_site(self):
        if self.locked or self.mutating:
            return
        site = self.current_site()
        if not site:
            return
        self.status.setText(tr("Loading credentials from the keyring …"))
        self.run_job(lambda: self.vault.get(site.id), lambda credentials, error:
                     self.show_error(error) if error else self.edit_dialog(site, credentials))

    def edit_dialog(self, site=None, credentials=None):
        if self.locked or self.mutating:
            return
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
            self.status.setText(tr("Site saved. Click its tab to open it."))
        self.status.setText(tr("Saving to the keyring …"))
        self.run_job(save, done)

    def delete_site(self):
        if self.locked or self.mutating:
            return
        site = self.current_site()
        if not site:
            return
        box = QMessageBox(self)
        box.setWindowTitle(tr("Remove site"))
        box.setTextFormat(Qt.TextFormat.PlainText)
        box.setText(tr("Remove “{name}” and its saved credentials?", name=site.name))
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
        box.button(QMessageBox.StandardButton.Yes).setText(tr("Yes"))
        box.button(QMessageBox.StandardButton.Cancel).setText(tr("Cancel"))
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
            self.status.setText(tr("Site and credentials removed."))
        self.run_job(remove, done)

    def change_mode(self, mode):
        if self.locked or self.mutating:
            return
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
        self.status.setText(tr("Launch mode saved. If the portal has already selected a client, change its mode there too."))

    def connect_site(self):
        if self.locked or self.mutating:
            return
        site = self.current_site()
        if not site:
            return
        if site.id in self.sessions:
            self.selected(self.tabs.currentIndex())
            return
        if site.mode == "workspace" and not workspace_executable():
            self.status.setText(tr("Citrix Workspace is not installed. You can sign in; install Workspace or select browser mode to launch a session."))
        generation = self.session_generation
        def connected(credentials, error):
            if self.locked or generation != self.session_generation or site not in self.sites:
                return
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
        self.status.setText(tr("Opening the keyring …"))
        self.run_job(lambda: self.vault.get(site.id), connected)

    def open_pending_site(self):
        if self.locked or not self.pending_site_id:
            self.pending_site_timer.stop()
            return
        if self.jobs or self.mutating or QApplication.activeModalWidget():
            return
        site_id, self.pending_site_id = self.pending_site_id, None
        self.pending_site_timer.stop()
        self.open_site_id(site_id)

    def open_site_id(self, site_id):
        if self.locked:
            self.pending_site_id = site_id
            self.unlock_secret.setFocus()
            return
        if self.jobs or self.mutating or QApplication.activeModalWidget():
            self.pending_site_id = site_id
            self.pending_site_timer.start()
            return
        # Reload so changes from the bar's on-disk list are reflected.
        self.sites = self.store.load()
        if not any(site.id == site_id for site in self.sites):
            self.status.setText(tr("This site was not found."))
            return
        self.refresh(site_id)
        if self.current_site():
            self.connect_site()
        else:
            self.status.setText(tr("This site was not found."))

    def retry(self):
        if self.locked or self.mutating:
            return
        site = self.current_site()
        if site and site.id in self.sessions:
            self.sessions[site.id].retry()

    def pause(self):
        if self.locked or self.mutating:
            return
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
            self.status.setText(tr("Local portal session closed. Workspace sessions continue separately. Sign out in the Citrix portal if needed."))

    def closeEvent(self, event):
        if self.jobs:
            self.status.setText(tr("Please wait for the current operation to finish."))
            event.ignore()
            return
        self.session_generation += 1
        self.pending_site_timer.stop()
        for site_id in list(self.sessions):
            self.remove_session(site_id)
        event.accept()
