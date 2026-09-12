"""Render local UI previews without opening a portal or touching the keyring."""
import os
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtGui import QColor
from omabridge.browser import PortalSession
from omabridge.models import Credentials, Site
from omabridge.storage import SiteStore
from omabridge.ui import MainWindow, SiteDialog

app = QApplication([])
destination = Path(__file__).resolve().parents[1] / "docs"
with tempfile.TemporaryDirectory() as directory:
    store = SiteStore(Path(directory))
    window = MainWindow(store)
    window.show()
    app.processEvents()
    window.grab().save(str(destination / "overview.png"))
    dialog = SiteDialog(window)
    dialog.show()
    app.processEvents()
    dialog.grab().save(str(destination / "add-site.png"))
    dialog.close()
    window.close()
    store.save([Site("Büro · Demo", "https://citrix.example.test"), Site("Kunde · Demo", "https://customer.example.test")])
    window = MainWindow(store)
    # Inert portal preview, not a real Citrix session or network request.
    site = window.sites[0]
    session = PortalSession(site, Credentials())
    session.timer.stop()
    window.sessions[site.id] = session
    session.popup_factory = window.open_popup
    session.popup_closer = window.close_popup
    window.stack.addWidget(session)
    window.refresh(site.id)
    window.show()
    page = window.open_popup(session)
    page.setBackgroundColor(QColor('#eef1f5'))
    window.popup_title(window.current_key(), "Virtueller Desktop · Demo")
    app.processEvents()
    window.grab().save(str(destination / "tabs.png"))
    window.close()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
