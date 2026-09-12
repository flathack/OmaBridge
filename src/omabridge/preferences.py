"""User interface preferences, separate from site configuration and credentials."""
import json
import os
import tempfile
from pathlib import Path

from .i18n import tr
from .storage import config_directory


class PreferencesStore:
    def __init__(self, directory: Path | None = None):
        self.path = (directory or config_directory()) / 'settings.json'

    def load(self) -> str:
        if not self.path.exists():
            return 'en'
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
            if data.get('version') != 1 or data.get('language') not in {'en', 'de'}:
                raise ValueError
            return data['language']
        except (ValueError, TypeError, AttributeError) as error:
            raise ValueError(tr('settings.json is invalid; it has not been overwritten.')) from error

    def save(self, language: str):
        if language not in {'en', 'de'}:
            raise ValueError(tr('Unsupported language.'))
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, temporary = tempfile.mkstemp(prefix='.settings-', dir=self.path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as output:
                json.dump({'version': 1, 'language': language}, output)
                output.write('\n')
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, self.path)
        finally:
            Path(temporary).unlink(missing_ok=True)
