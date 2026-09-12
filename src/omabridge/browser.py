import json
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
        self.session.message.emit("TLS-Zertifikat ungültig. Zertifikat bzw. Firmen-CA auf dem System prüfen.")

    def javaScriptConsoleMessage(self, level, message, line, source):
        pass  # Portal logs can include credentials or session tickets.

    def acceptNavigationRequest(self, url, navigation_type, is_main_frame):
        if url.scheme() in {"https", "about", "blob"}:
            return True
        if url.scheme() in {"receiver", "receivers", "citrixworkspace"}:
            self.session.message.emit("Im Portal „Bereits installiert“ wählen, damit Citrix eine ICA-Datei herunterlädt.")
        else:
            self.session.message.emit("Unsichere oder externe Navigation blockiert. Das Portal muss HTTPS verwenden.")
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

    def __init__(self, site: Site, credentials: Credentials, parent=None):
        super().__init__(parent)
        self.site = site
        self.credentials = credentials
        self.totp = Totp.parse(credentials.totp) if credentials.totp else None
        self.expected_origin = origin(site.url)
        self.used_stages: set[str] = set()
        self.popup_factory = None
        self.popup_closer = None
        self.busy = False
        self.deadline = time.monotonic() + 90
        self.auto_enabled = site.auto_login
        self.disposed = False
        self.popups = []
        self.downloads = []
        self.clients = []
        self.temporary = download_directory()
        # An unnamed profile is off-the-record: no cookies/cache/history on disk.
        self.profile = QWebEngineProfile(self)
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
        self.message.emit("Portal wird geladen …")

    def url_changed(self, url):
        # Do not show query strings: launch tickets can be carried in URLs.
        self.address.emit(display_address(url))

    def loaded(self, success):
        if not success:
            self.message.emit("Portal konnte nicht geladen werden. URL, Netzwerk, VPN und Zertifikat prüfen.")
        else:
            self.message.emit("Portal bereit. Anmeldung und anschließend App oder Desktop auswählen.")

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
                                   "selector": self.site.selectors.get(self.site.mode, "")}, lambda _: None)
        if not self.auto_enabled or time.monotonic() > self.deadline:
            return
        self.busy = True
        self.evaluate(LOGIN_SCRIPT, {**self.login_options(), "fill": False}, self.probed)

    def login_options(self):
        return {"origin": self.expected_origin, "selectors": self.site.selectors,
                "passwordSubmitted": any("password" in stage.split("+") for stage in self.used_stages)}

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
                    "ambiguous": "Formular nicht eindeutig erkannt. Manuell anmelden oder Feld-Selektoren in den Site-Einstellungen anpassen.",
                    "selector-error": "Ungültiger CSS-Selektor. Bitte Site-Einstellungen korrigieren.",
                    "untrusted-action": "Das Formular sendet an eine andere Domain. Zugangsdaten werden nicht automatisch ausgefüllt."
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
            self.message.emit("Warte auf einen frischen TOTP-Code …")
            return
        values = {"username": self.credentials.username, "password": self.credentials.password,
                  "otp": self.totp.code() if self.totp else ""}
        if any(not values.get(role) for role in result["roles"]):
            self.busy = False
            self.message.emit("Zugangsdaten fehlen. Site bearbeiten oder direkt im Portal anmelden.")
            return
        # Reserve before invoking page code, so reloads and errors cannot cause a retry storm.
        options = self.login_options()
        self.used_stages.add(stage)
        self.evaluate(LOGIN_SCRIPT, {**options, "fill": True, "submit": True, "stage": stage, "values": values},
                      lambda result: self.filled(result, stage))

    def filled(self, result, stage):
        if self.disposed:
            return
        self.busy = False
        state = result.get("state") if isinstance(result, dict) else None
        if state == "submitted":
            # The next form gets its own interval, even after a slow first step.
            self.deadline = time.monotonic() + 90
            if "password" in stage.split("+") and "otp" not in stage.split("+") and self.totp:
                self.message.emit("Benutzername/Passwort gesendet. Warte auf das TOTP-Feld …")
            elif "otp" in stage.split("+"):
                self.message.emit("TOTP-Code gesendet. Anmeldung wird abgeschlossen …")
            else:
                self.message.emit("Anmeldeschritt gesendet. Warte auf den nächsten Schritt …")
        else:
            # These responses guarantee that no click took place. A missing
            # callback remains reserved because navigation may have submitted.
            if state in {"awaiting-submit", "changed", "missing", "waiting", "ambiguous", "selector-error", "untrusted", "untrusted-action"}:
                self.used_stages.discard(stage)
            if state == "awaiting-submit":
                self.message.emit("Felder ausgefüllt. Warte auf den Anmelde-Button; du kannst auch manuell bestätigen.")
            else:
                self.message.emit("Formular hat sich geändert. Bitte im Portal fortfahren oder „Anmeldung erneut“ wählen.")

    def retry(self):
        self.used_stages.clear()
        self.auto_enabled = True
        self.deadline = time.monotonic() + 90
        self.message.emit("Automatische Anmeldung erneut aktiviert.")

    def pause(self):
        self.auto_enabled = False
        self.message.emit("Automatische Anmeldung pausiert. Du kannst im Portal fortfahren.")

    def download(self, request):
        is_ica = request.suggestedFileName().lower().endswith(".ica") or request.mimeType() == "application/x-ica"
        try:
            trusted = origin(request.url().toString()) == self.expected_origin
        except ValueError:
            trusted = False
        if self.disposed or not is_ica or not trusted:
            request.cancel()
            self.message.emit("Download blockiert. OmaBridge übernimmt nur ICA-Dateien von der gespeicherten Portal-Domain.")
            return
        if self.site.mode != "workspace":
            request.cancel()
            self.message.emit("Das Portal liefert eine Workspace-Datei. Im Portal „Webbrowser verwenden“ wählen; HTML5 muss serverseitig aktiviert sein.")
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
        if request.state() != QWebEngineDownloadRequest.DownloadState.DownloadCompleted:
            path.unlink(missing_ok=True)
            self.message.emit("ICA-Download fehlgeschlagen oder abgebrochen. App im Portal erneut auswählen.")
            return
        try:
            process = launch_workspace(path)
            self.clients.append((process, path, time.monotonic()))
            self.message.emit("ICA-Datei an Citrix Workspace übergeben.")
        except (OSError, ValueError) as error:
            path.unlink(missing_ok=True)
            self.message.emit(str(error))

    def cleanup_clients(self):
        for process, path, started in self.clients[:]:
            result = process.poll()
            if result is not None or time.monotonic() - started > 300:
                path.unlink(missing_ok=True)
                self.clients.remove((process, path, started))
                if result not in {None, 0}:
                    self.message.emit("Citrix Workspace meldet einen Startfehler. Client-Installation und Verbindung prüfen.")

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
