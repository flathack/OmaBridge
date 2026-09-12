from pathlib import Path

from PySide6.QtCore import QObject, Signal, QUrl, QCoreApplication, QEvent
from PySide6.QtWebEngineCore import QWebEngineDownloadRequest

from omabridge.browser import PortalSession
from omabridge.models import Credentials, Site


class Download(QObject):
    receivedBytesChanged = Signal()
    isFinishedChanged = Signal()

    def __init__(self, url="https://citrix.test/launch.ica"):
        super().__init__()
        self.source = url
        self.cancelled = False
        self.accepted = False
        self.finished = False
        self.directory = ""
        self.filename = ""

    def suggestedFileName(self): return "../../untrusted-name.ica"
    def mimeType(self): return "application/x-ica"
    def url(self): return QUrl(self.source)
    def cancel(self): self.cancelled = True
    def accept(self): self.accepted = True
    def setDownloadDirectory(self, value): self.directory = value
    def setDownloadFileName(self, value): self.filename = value
    def receivedBytes(self): return 0
    def isFinished(self): return self.finished
    def state(self): return QWebEngineDownloadRequest.DownloadState.DownloadCompleted


def dispose(session):
    session.dispose()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    session.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_workspace_download_handoff_and_cleanup(app, monkeypatch):
    import omabridge.browser as browser
    session = PortalSession(Site("Test", "https://citrix.test"), Credentials())
    session.timer.stop()
    launched = []
    class Process:
        def poll(self): return 0
    monkeypatch.setattr(browser, "launch_workspace", lambda path: launched.append(path) or Process())
    request = Download()
    session.download(request)
    assert request.accepted and "/" not in request.filename and request.filename.endswith(".ica")
    path = Path(request.directory) / request.filename
    path.write_text("test fixture ticket")
    request.finished = True
    request.isFinishedChanged.emit()
    assert launched == [path]
    session.cleanup_clients()
    assert not path.exists()
    dispose(session)


def test_browser_mode_never_launches_workspace(app):
    session = PortalSession(Site("Test", "https://citrix.test", mode="browser"), Credentials())
    session.timer.stop()
    request = Download()
    session.download(request)
    assert request.cancelled and not request.accepted
    dispose(session)


def test_foreign_download_never_launches(app):
    session = PortalSession(Site("Test", "https://citrix.test"), Credentials())
    session.timer.stop()
    request = Download("https://other.test/launch.ica")
    session.download(request)
    assert request.cancelled and not request.accepted
    dispose(session)
