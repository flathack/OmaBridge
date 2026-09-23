"""Small, private favicon cache shared by the app and the bar widget."""
import os
import tempfile
from pathlib import Path
from uuid import UUID

from PySide6.QtCore import QBuffer, QIODevice, Qt
from PySide6.QtGui import QIcon


class FaviconStore:
    def __init__(self, directory: Path):
        self.directory = directory / 'favicons'

    def path(self, site_id: str) -> Path:
        return self.directory / (str(UUID(site_id)) + '.png')

    def icon(self, site_id: str) -> QIcon:
        path = self.path(site_id)
        return QIcon(str(path)) if path.is_file() else QIcon()

    def url(self, site_id: str) -> str:
        path = self.path(site_id)
        try:
            return path.as_uri() + '?v=' + str(path.stat().st_mtime_ns) if path.is_file() else ''
        except OSError:
            return ''

    def save(self, site_id: str, icon: QIcon) -> bool:
        if icon.isNull():
            return False
        pixmap = icon.pixmap(32, 32)
        if pixmap.isNull():
            return False
        pixmap = pixmap.scaled(32, 32, Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        if not pixmap.save(buffer, 'PNG'):
            return False
        path = self.path(site_id)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.directory, 0o700)
        fd, temporary = tempfile.mkstemp(prefix='.favicon-', suffix='.png', dir=self.directory)
        try:
            with os.fdopen(fd, 'wb') as output:
                output.write(bytes(buffer.data()))
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, path)
            return True
        finally:
            Path(temporary).unlink(missing_ok=True)

    def remove(self, site_id: str):
        self.path(site_id).unlink(missing_ok=True)
