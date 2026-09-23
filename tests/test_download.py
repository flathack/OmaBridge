from pathlib import Path

import pytest

from PySide6.QtCore import QObject, Signal, QUrl, QCoreApplication, QEvent
from PySide6.QtWebEngineCore import QWebEngineDownloadRequest

from omabridge.browser import PortalSession, ica_source_origin
from omabridge.models import Credentials, Site


class Download(QObject):
    receivedBytesChanged = Signal()
    isFinishedChanged = Signal()

    def __init__(self, url="https://citrix.test/launch.ica", page=None):
        super().__init__()
        self.source = url
        self.source_page = page
        self.cancelled = False
        self.accepted = False
        self.finished = False
        self.directory = ""
        self.filename = ""

    def suggestedFileName(self): return "../../untrusted-name.ica"
    def mimeType(self): return "application/x-ica"
    def url(self): return QUrl(self.source)
    def page(self): return self.source_page
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


def test_workspace_launch_failure_is_visible(app, monkeypatch):
    import omabridge.browser as browser
    session = PortalSession(Site("Test", "https://citrix.test"), Credentials())
    session.timer.stop()
    errors = []
    session.launch_error.connect(errors.append)
    monkeypatch.setattr(browser, "launch_workspace", lambda _: (_ for _ in ()).throw(ValueError("Workspace failed")))
    request = Download()
    session.download(request)
    path = Path(request.directory) / request.filename
    path.write_text("test fixture ticket")
    request.finished = True
    request.isFinishedChanged.emit()
    assert errors == ["Workspace failed"] and not path.exists()
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


def test_foreign_ica_requires_explicit_approval_from_site_profile(app):
    session = PortalSession(Site("Test", "https://citrix.test"), Credentials())
    session.timer.stop()
    requests = []
    session.approve_ica_origin = lambda site, address: requests.append((site.id, address)) or True
    unknown_page = Download("https://downloads.test/launch.ica")
    session.download(unknown_page)
    assert unknown_page.accepted and requests == [(session.site.id, "https://downloads.test")]
    portal_page = Download("https://downloads.test/launch.ica", session.page)
    session.download(portal_page)
    assert portal_page.accepted and len(requests) == 2
    dispose(session)


def test_allowed_ica_origin_does_not_prompt_again(app):
    site = Site("Test", "https://citrix.test", ica_origins=["https://downloads.test"])
    session = PortalSession(site, Credentials())
    session.timer.stop()
    request = Download("https://downloads.test/launch.ica")
    session.download(request)
    assert request.accepted
    dispose(session)


def test_https_blob_download_uses_embedded_origin(app):
    session = PortalSession(Site("Test", "https://citrix.test"), Credentials())
    session.timer.stop()
    assert ica_source_origin(QUrl("blob:https://citrix.test/ticket-id")) == "https://citrix.test"
    request = Download("blob:https://citrix.test/ticket-id")
    session.download(request)
    assert request.accepted
    dispose(session)


def test_https_download_origin_ignores_pretty_decoded_path_and_ticket(app):
    url = QUrl('https://citrix.test/Personal%20Computer.ica?ticket=a%5Cb')
    assert 'Personal Computer' in url.toString()
    assert ica_source_origin(url) == 'https://citrix.test'
    session = PortalSession(Site("Test", "https://citrix.test"), Credentials())
    session.timer.stop()
    request = Download(url.toString())
    session.download(request)
    assert request.accepted
    dispose(session)


@pytest.mark.parametrize('address', ['http://citrix.test/launch.ica',
    'https://user:pass@citrix.test/launch.ica', 'blob:http://citrix.test/ticket'])
def test_ica_source_origin_rejects_untrusted_scheme_and_userinfo(address):
    assert ica_source_origin(QUrl(address)) is None


def test_foreign_blob_origin_requires_approval(app):
    session = PortalSession(Site("Test", "https://citrix.test"), Credentials())
    session.timer.stop()
    origins = []
    session.approve_ica_origin = lambda _, address: origins.append(address) or True
    request = Download("blob:https://downloads.test/ticket-id")
    session.download(request)
    assert request.accepted and origins == ["https://downloads.test"]
    dispose(session)


def test_portal_generated_data_ica_is_allowed_but_unowned_data_is_blocked(app):
    session = PortalSession(Site("Test", "https://citrix.test"), Credentials())
    session.timer.stop()
    session.page.setUrl(QUrl("https://citrix.test"))
    accepted = Download("data:application/x-ica;base64,dGVzdA==", session.page)
    session.download(accepted)
    assert accepted.accepted
    blocked = Download("data:application/x-ica;base64,dGVzdA==")
    session.download(blocked)
    assert blocked.cancelled
    dispose(session)


def test_insecure_ica_error_reports_scheme_without_ticket(app):
    session = PortalSession(Site("Test", "https://citrix.test"), Credentials())
    session.timer.stop()
    errors = []
    session.launch_error.connect(errors.append)
    request = Download("http://citrix.test/launch.ica?ticket=secret")
    session.download(request)
    assert request.cancelled and "http" in errors[0] and "secret" not in errors[0]
    dispose(session)


@pytest.mark.parametrize("closed", [False, True])
def test_completed_download_rechecks_mode_and_lifetime(app, monkeypatch, closed):
    import omabridge.browser as browser
    session = PortalSession(Site("Test", "https://citrix.test"), Credentials())
    session.timer.stop()
    launched = []
    monkeypatch.setattr(browser, "launch_workspace", lambda path: launched.append(path))
    request = Download()
    session.download(request)
    path = Path(request.directory) / request.filename
    path.write_text("test fixture ticket")
    if closed:
        session.dispose()
    else:
        session.site.mode = "browser"
    request.finished = True
    request.isFinishedChanged.emit()
    assert not launched and not path.exists()
    assert request not in session.downloads
    dispose(session)
