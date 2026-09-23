import json
import os
import subprocess
import sys

import pytest

from omabridge.preferences import PreferencesStore
from omabridge.storage import SiteStore
from omabridge.models import Site


def test_preferences_default_private_and_atomic(tmp_path, monkeypatch):
    store = PreferencesStore(tmp_path)
    assert store.load() == 'en'
    store.save('de')
    assert store.load() == 'de'
    assert store.path.stat().st_mode & 0o777 == 0o600
    assert json.loads(store.path.read_text()) == {'version': 1, 'language': 'de'}
    def fail(*_):
        raise OSError('Disk full')
    monkeypatch.setattr(os, 'replace', fail)
    with pytest.raises(OSError):
        store.save('en')
    assert store.load() == 'de'
    assert list(tmp_path.iterdir()) == [store.path]


def test_invalid_preferences_are_not_overwritten(tmp_path):
    store = PreferencesStore(tmp_path)
    store.path.write_text('{"version": 1, "language": "other"}')
    with pytest.raises(ValueError, match='not been overwritten'):
        store.load()
    with pytest.raises(ValueError):
        store.save('other')
    assert 'other' in store.path.read_text()


def test_appearance_persists_without_changing_language(tmp_path):
    store = PreferencesStore(tmp_path)
    assert store.load_appearance() == 'omarchy'
    store.save('de')
    store.save_appearance('midnight')
    assert store.load() == 'de'
    assert store.load_appearance() == 'midnight'
    store.save('en')
    assert store.load_appearance() == 'midnight'
    with pytest.raises(ValueError, match='Unsupported appearance'):
        store.save_appearance('unknown')


def test_bar_state_shares_language_without_credentials(tmp_path):
    directory = tmp_path / 'omabridge'
    sites = SiteStore(directory)
    sites.save([Site('Private office', 'https://citrix.test')])
    PreferencesStore(directory).save('de')
    env = {**os.environ, 'XDG_CONFIG_HOME': str(tmp_path)}
    result = subprocess.run([sys.executable, '-m', 'omabridge', '--bar-state'], env=env,
                            capture_output=True, text=True, check=True)
    state = json.loads(result.stdout)
    assert state['language'] == 'de'
    assert state['sites'] == [{'id': sites.load()[0].id, 'name': 'Private office', 'mode': 'workspace'}]
    result = subprocess.run([sys.executable, '-m', 'omabridge', '--list-sites'], env=env,
                            capture_output=True, text=True, check=True)
    assert json.loads(result.stdout) == state['sites']
