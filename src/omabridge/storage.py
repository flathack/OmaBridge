import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

from .models import Credentials, Site


def config_directory() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "omabridge"


class SiteStore:
    def __init__(self, directory: Path | None = None):
        self.directory = directory or config_directory()
        self.path = self.directory / "sites.json"

    def load(self) -> list[Site]:
        if not self.path.exists():
            return []
        try:
            raw = json.loads(self.path.read_text())
            if raw.get("version") != 1 or not isinstance(raw.get("sites"), list):
                raise ValueError("Unbekanntes Konfigurationsformat.")
            sites = [Site(**item) for item in raw["sites"]]
            if len({s.id for s in sites}) != len(sites):
                raise ValueError("Doppelte Site-ID.")
            return sites
        except (ValueError, TypeError, KeyError, AttributeError) as error:
            raise ValueError("sites.json ist ungültig. Datei sichern und korrigieren; sie wurde nicht überschrieben.") from error

    def save(self, sites: list[Site]):
        if len({s.id for s in sites}) != len(sites):
            raise ValueError("Doppelte Site-ID.")
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.directory, 0o700)
        fd, name = tempfile.mkstemp(prefix=".sites-", dir=self.directory)
        try:
            with os.fdopen(fd, "w") as file:
                json.dump({"version": 1, "sites": [s.public_dict() for s in sites]}, file, indent=2, ensure_ascii=False)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            os.replace(name, self.path)
        finally:
            Path(name).unlink(missing_ok=True)


class VaultError(RuntimeError):
    pass


class SecretVault:
    """Use Secret Service directly; never fall back to a plaintext backend."""

    @contextmanager
    def _collection(self):
        import secretstorage
        connection = None
        try:
            connection = secretstorage.dbus_init()
            collection = secretstorage.get_default_collection(connection)
            if collection.is_locked():
                collection.unlock()
            if collection.is_locked():
                raise VaultError("Der Schlüsselbund ist gesperrt. Bitte entsperren und erneut versuchen.")
        except VaultError:
            if connection:
                connection.close()
            raise
        except Exception as error:
            if connection:
                connection.close()
            raise VaultError("Linux-Schlüsselbund nicht erreichbar. Secret Service (z. B. GNOME Keyring) starten und entsperren.") from error
        try:
            yield collection
        finally:
            connection.close()

    @staticmethod
    def _attributes(site_id: str):
        return {"application": "omabridge", "site-id": site_id}

    def get(self, site_id: str) -> Credentials:
        try:
            with self._collection() as collection:
                items = list(collection.search_items(self._attributes(site_id)))
                if not items:
                    return Credentials()
                item = items[0]
                if item.is_locked():
                    item.unlock()
                return Credentials(**json.loads(item.get_secret().decode("utf-8")))
        except VaultError:
            raise
        except Exception as error:
            raise VaultError("Zugangsdaten konnten nicht aus dem Schlüsselbund gelesen werden.") from error

    def set(self, site_id: str, credentials: Credentials):
        try:
            from dataclasses import asdict
            with self._collection() as collection:
                collection.create_item("OmaBridge-Zugangsdaten", self._attributes(site_id),
                                       json.dumps(asdict(credentials)).encode(), replace=True)
        except VaultError:
            raise
        except Exception as error:
            raise VaultError("Zugangsdaten konnten nicht im Schlüsselbund gespeichert werden.") from error

    def delete(self, site_id: str):
        try:
            with self._collection() as collection:
                for item in collection.search_items(self._attributes(site_id)):
                    item.delete()
        except VaultError:
            raise
        except Exception as error:
            raise VaultError("Zugangsdaten konnten nicht aus dem Schlüsselbund gelöscht werden.") from error
