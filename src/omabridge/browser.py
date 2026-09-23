from .i18n import tr

import json
import os
import time
from importlib.resources import files
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QTimer, QUrl, Qt, Signal
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineScript, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QVBoxLayout, QWidget

from .launcher import download_directory, launch_workspace
from .models import Credentials, Site, origin
from .storage import config_directory
from .totp import Totp

LOGIN_SCRIPT = files("omabridge").joinpath("assets/login.js").read_text()
MODE_SCRIPT = files("omabridge").joinpath("assets/mode.js").read_text()
WORLD = QWebEngineScript.ScriptWorldId.ApplicationWorld


def display_address(url: QUrl) -> str:
    sanitized = QUrl(url)
    sanitized.setQuery(None)
    sanitized.setFragment(None)
    sanitized.setUserName(None)
    sanitized.setPassword(None)
    return sanitized.toString()


def ica_source_origin(url: QUrl) -> str | None:
    """Resolve HTTPS and HTTPS-backed blob downloads without exposing ticket URLs."""
    if url.scheme() == 'blob':
        url = QUrl(url.toString().removeprefix('blob:'))
    if not url.isValid() or url.scheme().lower() != 'https' or not url.host() or url.userInfo():
        return None
    host = url.host()
    host = f'[{host}]' if ':' in host and not host.startswith('[') else host
    port = url.port(-1)
    address = f'https://{host}' + (f':{port}' if port != -1 else '')
    try:
        return origin(address)
    except ValueError:
        return None


class PortalPage(QWebEnginePage):
    def __init__(self, profile, session, parent=None):
        super().__init__(profile, parent)
        self.session = session
        self.certificateError.connect(lambda error: self.reject_certificate(error))
        self.fullScreenRequested.connect(self.fullscreen)
        self.windowCloseRequested.connect(self.close_popup)
        self.settings().setAttribute(QWebEngineSettings.WebAttribute.FullScreenSupportEnabled, True)
        self.settings().setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, True)
        self.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, False)
        self.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)

    def reject_certificate(self, error):
        error.rejectCertificate()
        self.session.message.emit(tr("Invalid TLS certificate. Check the certificate or company CA on your system."))

    def javaScriptConsoleMessage(self, level, message, line, source):
        pass  # Portal logs can include credentials or session tickets.

    def acceptNavigationRequest(self, url, navigation_type, is_main_frame):
        if url.scheme() in {"https", "about", "blob"}:
            return True
        if url.scheme() in {"receiver", "receivers", "citrixworkspace"}:
            self.session.message.emit(tr("Choose “Already installed” in the portal so Citrix downloads an ICA file."))
        else:
            self.session.message.emit(tr("Unsafe or external navigation blocked. The portal must use HTTPS."))
        return False

    def createWindow(self, window_type):
        if self.session.popup_factory:
            return self.session.popup_factory(self.session)
        view = QWebEngineView()
        view.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        page = PortalPage(self.profile(), self.session, view)
        view.setPage(page)
        view.resize(1280, 850)
        view.setWindowTitle(f"{self.session.site.name} · Citrix")
        self.session.popups.append(view)
        view.destroyed.connect(lambda: self.session.popups.remove(view) if view in self.session.popups else None)
        view.show()
        return page

    def fullscreen(self, request):
        request.accept()
        window = self.view_window()
        window.showFullScreen() if request.toggleOn() else window.showNormal()

    def view_window(self):
        return self.parent().window()

    def close_popup(self):
        if self.parent() in self.session.popups:
            if self.session.popup_closer:
                self.session.popup_closer(self.parent())
            else:
                self.parent().close()


class PortalSession(QWidget):
    message = Signal(str)
    address = Signal(str)
    launch_error = Signal(str)

    def __init__(self, site: Site, credentials: Credentials, parent=None, profile_root: Path | None = None):
        super().__init__(parent)
        self.site = site
        self.credentials = credentials
        self.totp = Totp.parse(credentials.totp) if credentials.totp else None
        self.expected_origin = origin(site.url)
        self.used_stages: set[str] = set()
        self.popup_factory = None
        self.popup_closer = None
        self.approve_ica_origin = None
        self.busy = False
        self.deadline = time.monotonic() + 90
        self.auto_enabled = site.auto_login
        self.disposed = False
        self.popups = []
        self.downloads = []
        self.clients = []
        self.temporary = download_directory()
        profile_root = profile_root or config_directory() / 'browser'
        profile_path = profile_root / site.id
        if profile_root.is_symlink() or profile_path.is_symlink():
            raise ValueError(tr("The browser profile directory must not be a symlink."))
        profile_path.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(profile_path, 0o700)
        self.profile = QWebEngineProfile(site.id, self)
        self.profile.setPersistentStoragePath(str(profile_path / 'storage'))
        self.profile.setCachePath(str(profile_path / 'cache'))
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
        self.profile.setHttpAcceptLanguage("de-DE,de;q=0.9,en;q=0.8")
        self.profile.downloadRequested.connect(self.download)
        self.view = QWebEngineView(self)
        self.page = PortalPage(self.profile, self, self.view)
        self.view.setPage(self.page)
        self.view.urlChanged.connect(self.url_changed)
        self.view.loadFinished.connect(self.loaded)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view)
        self.timer = QTimer(self)
        self.timer.setInterval(800)
        self.timer.timeout.connect(self.tick)
        self.timer.start()

    def start(self):
        self.view.load(QUrl(self.site.url))
        self.message.emit(tr("Loading portal …"))

    def url_changed(self, url):
        # Do not show query strings: launch tickets can be carried in URLs.
        self.address.emit(display_address(url))

    def loaded(self, success):
        if not success:
            self.message.emit(tr("Could not load the portal. Check the URL, network, VPN and certificate."))
        else:
            self.message.emit(tr("Portal ready. Sign in, then select an app or desktop."))

    def evaluate(self, script, options, callback):
        def decoded(value):
            try:
                result = json.loads(value)
            except (ValueError, TypeError):
                result = None
            callback(result)
        self.page.runJavaScript(f"JSON.stringify({script}({json.dumps(options, ensure_ascii=True)}))", WORLD, decoded)

    def tick(self):
        if self.disposed or self.busy:
            return
        self.cleanup_clients()
        try:
            trusted = origin(self.view.url().toString()) == self.expected_origin
        except ValueError:
            trusted = False
        if not trusted:
            return
        self.evaluate(MODE_SCRIPT, {"origin": self.expected_origin, "mode": self.site.mode,
                                   "selector": self.site.selectors.get(self.site.mode, "")}, self.mode_selected)
        if not self.auto_enabled or time.monotonic() > self.deadline:
            return
        self.busy = True
        self.evaluate(LOGIN_SCRIPT, {**self.login_options(), "fill": False}, self.probed)

    def login_options(self):
        return {"origin": self.expected_origin, "selectors": self.site.selectors,
                "passwordSubmitted": any("password" in stage.split("+") for stage in self.used_stages)}

    def mode_selected(self, result):
        if result == "detecting":
            self.message.emit(tr("Detecting Citrix Workspace. If the portal asks, choose “Already installed”."))
        elif result == "selector-error":
            self.message.emit(tr("Invalid launch mode selector. Correct it in the site settings."))

    def probed(self, result):
        if self.disposed:
            return
        if not self.auto_enabled or time.monotonic() > self.deadline:
            self.busy = False
            return
        if not isinstance(result, dict) or result.get("state") != "ready":
            self.busy = False
            if isinstance(result, dict):
                messages = {
                    "ambiguous": tr("Form is ambiguous. Sign in manually or adjust field selectors in the site settings."),
                    "selector-error": tr("Invalid CSS selector. Please correct the site settings."),
                    "untrusted-action": tr("The form submits to another origin. Credentials will not be filled automatically.")
                }
                if result.get("state") in messages:
                    self.message.emit(messages[result["state"]])
            return
        stage = result["stage"]
        if stage in self.used_stages or len(self.used_stages) >= 3:
            self.busy = False
            return
        if self.totp and "otp" in result["roles"] and self.totp.remaining() < 5:
            self.busy = False
            self.message.emit(tr("Waiting for a fresh TOTP code …"))
            return
        values = {"username": self.credentials.username, "password": self.credentials.password,
                  "otp": self.totp.code() if self.totp else ""}
        manual_otp = "otp" in result["roles"] and self.totp is None
        required_roles = [role for role in result["roles"] if not (manual_otp and role == "otp")]
        if any(not values.get(role) for role in required_roles):
            self.busy = False
            self.message.emit(tr("Credentials are missing. Edit the site or sign in directly in the portal."))
            return
        # Reserve before invoking page code, so reloads and errors cannot cause a retry storm.
        options = self.login_options()
        self.used_stages.add(stage)
        self.evaluate(LOGIN_SCRIPT, {**options, "fill": True, "submit": not manual_otp,
                                    "manualOtp": manual_otp, "stage": stage, "values": values},
                      lambda result: self.filled(result, stage))

    def filled(self, result, stage):
        if self.disposed:
            return
        self.busy = False
        state = result.get("state") if isinstance(result, dict) else None
        if state == "manual-otp":
            self.message.emit(tr("Enter the verification code in the portal and submit it there. Saving TOTP is optional."))
        elif state == "submitted":
            # The next form gets its own interval, even after a slow first step.
            self.deadline = time.monotonic() + 90
            if "password" in stage.split("+") and "otp" not in stage.split("+") and self.totp:
                self.message.emit(tr("Username/password submitted. Waiting for the TOTP field …"))
            elif "otp" in stage.split("+"):
                self.message.emit(tr("TOTP code submitted. Completing sign-in …"))
            else:
                self.message.emit(tr("Sign-in step submitted. Waiting for the next step …"))
        else:
            # These responses guarantee that no click took place. A missing
            # callback remains reserved because navigation may have submitted.
            if state in {"awaiting-submit", "changed", "missing", "waiting", "ambiguous", "selector-error", "untrusted", "untrusted-action"}:
                self.used_stages.discard(stage)
            if state == "awaiting-submit":
                self.message.emit(tr("Fields filled. Waiting for the sign-in button; you can also submit manually."))
            else:
                self.message.emit(tr("The form changed. Continue in the portal or choose “Retry sign-in”."))

    def retry(self):
        self.used_stages.clear()
        self.auto_enabled = True
        self.deadline = time.monotonic() + 90
        self.message.emit(tr("Automatic sign-in enabled again."))

    def pause(self):
        self.auto_enabled = False
        self.message.emit(tr("Automatic sign-in paused. You can continue in the portal."))

    def download(self, request):
        is_ica = request.suggestedFileName().lower().endswith(".ica") or request.mimeType() == "application/x-ica"
        download_origin = ica_source_origin(request.url())
        trusted = download_origin == self.expected_origin or download_origin in self.site.ica_origins
        if request.url().scheme() == 'data' and is_ica:
            page = request.page()
            owned = page is self.page or any(view.page() is page for view in self.popups)
            if owned:
                try:
                    source_origin = origin(page.url().toString())
                    trusted = source_origin == self.expected_origin or source_origin in self.site.ica_origins
                except ValueError:
                    pass
        if download_origin and not trusted and is_ica and self.site.mode == "workspace":
            # This signal belongs to this site's profile. Some redirected
            # downloads have no page(), so rely on explicit origin approval.
            if self.approve_ica_origin:
                trusted = self.approve_ica_origin(self.site, download_origin)
        if self.disposed or not is_ica or not trusted:
            request.cancel()
            scheme = request.url().scheme().lower()
            scheme = scheme if scheme in {'https', 'http', 'blob', 'data', 'file'} else 'other'
            error = tr("Download blocked (source: {scheme}). ICA files must come from the saved portal or an allowed HTTPS address.", scheme=scheme)
            self.message.emit(error)
            if is_ica and not self.disposed:
                self.launch_error.emit(error)
            return
        if self.site.mode != "workspace":
            request.cancel()
            self.message.emit(tr("The portal returned a Workspace file. Choose “Use web browser” in the portal; HTML5 must be enabled on the server."))
            return
        filename = f"{uuid4()}.ica"
        request.setDownloadDirectory(self.temporary.name)
        request.setDownloadFileName(filename)
        self.downloads.append(request)
        path = Path(self.temporary.name) / filename
        request.receivedBytesChanged.connect(lambda: request.cancel() if request.receivedBytes() > 2_000_000 else None)
        request.isFinishedChanged.connect(lambda: self.download_finished(request, path))
        request.accept()

    def download_finished(self, request, path):
        from PySide6.QtWebEngineCore import QWebEngineDownloadRequest
        if not request.isFinished() or request not in self.downloads:
            return
        self.downloads.remove(request)
        # The user may switch modes or close the session while a download is pending.
        if self.disposed or self.site.mode != "workspace":
            path.unlink(missing_ok=True)
            if not self.disposed:
                self.message.emit(tr("Workspace launch cancelled: browser mode is now active."))
            return
        if request.state() != QWebEngineDownloadRequest.DownloadState.DownloadCompleted:
            path.unlink(missing_ok=True)
            error = tr("ICA download failed or was cancelled. Select the app in the portal again.")
            self.message.emit(error)
            self.launch_error.emit(error)
            return
        try:
            process = launch_workspace(path)
            self.clients.append((process, path, time.monotonic()))
            self.message.emit(tr("ICA file handed off to Citrix Workspace."))
        except (OSError, ValueError) as error:
            path.unlink(missing_ok=True)
            self.message.emit(str(error))
            self.launch_error.emit(str(error))

    def cleanup_clients(self):
        for process, path, started in self.clients[:]:
            result = process.poll()
            if result is not None or time.monotonic() - started > 300:
                path.unlink(missing_ok=True)
                self.clients.remove((process, path, started))
                if result not in {None, 0}:
                    error = tr("Citrix Workspace reported a launch error. Check the client installation and connection.")
                    self.message.emit(error)
                    self.launch_error.emit(error)

    def dispose(self):
        if self.disposed:
            return
        self.disposed = True
        self.timer.stop()
        self.credentials = Credentials()
        self.totp = None
        for request in self.downloads[:]:
            request.cancel()
        for popup in self.popups[:]:
            if self.popup_closer:
                self.popup_closer(popup)
            else:
                popup.close()
        self.view.stop()
        self.view.close()
        # Explicit ordering avoids destroying a profile while its page still exists.
        self.page.deleteLater()
        self.temporary.cleanup()
