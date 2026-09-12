import json
import os
import subprocess
import sys

import pytest

from omabridge.app_lock import AppLockStore
from omabridge.models import Site
from omabridge.storage import SiteStore


def test_hash_storage_verification_and_persistent_retry_limit(tmp_path):
    now = [1000.0]
    store = AppLockStore(tmp_path, clock=lambda: now[0])
    assert store.load() is None
    store.configure('0567', 'pin')
    first = store.load()
    assert '"0567"' not in store.path.read_text()
    assert store.path.stat().st_mode & 0o777 == 0o600
    assert store.verify('0567')
    assert not store.verify('567')
    assert not store.verify('wrong')
    assert not store.verify('wrong')
    reopened = AppLockStore(tmp_path, clock=lambda: now[0])
    with pytest.raises(ValueError, match='Too many attempts'):
        reopened.verify('0567')
    now[0] += 2
    assert reopened.verify('0567')
    assert reopened.load()['failures'] == 0
    store.configure('0567', 'pin')
    assert first['salt'] != store.load()['salt']
    assert first['digest'] != store.load()['digest']
    store.disable()
    assert store.load() is None
    with pytest.raises(ValueError, match='changed'):
        store.verify('0567')


def test_arbitrary_lengths_and_unicode_password(tmp_path):
    store = AppLockStore(tmp_path)
    for pin in ['0', '1234567890' * 20]:
        store.validate_secret(pin, 'pin')
    for invalid in ['', 'one', '１２３４', '-1', '1 2']:
        with pytest.raises(ValueError):
            store.validate_secret(invalid, 'pin')
    password = 'Grüße 🔑 ' * 50
    store.configure(password, 'password')
    assert store.verify(password)
    assert not store.verify(password[:4])


@pytest.mark.parametrize('contents', ['{', 'null', '{"version":1,"enabled":true}', 'x' * 4097])
def test_corrupt_lock_fails_closed(tmp_path, contents):
    store = AppLockStore(tmp_path)
    store.path.write_text(contents)
    with pytest.raises(ValueError, match='Access remains blocked'):
        store.load()
    assert store.path.read_text() == contents


def test_failed_change_preserves_lock(tmp_path, monkeypatch):
    store = AppLockStore(tmp_path)
    store.configure('1234', 'pin')
    original = store.path.read_bytes()
    def fail(*_):
        raise OSError('Disk full')
    monkeypatch.setattr(os, 'replace', fail)
    with pytest.raises(OSError):
        store.disable()
    assert store.path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [store.path]


def test_bar_and_cli_hide_sites_when_lock_configured(tmp_path):
    directory = tmp_path / 'omabridge'
    SiteStore(directory).save([Site('Private office', 'https://private.test')])
    lock = AppLockStore(directory)
    lock.configure('1234', 'pin')
    env = {**os.environ, 'XDG_CONFIG_HOME': str(tmp_path)}
    for option in ['--list-sites', '--bar-state']:
        result = subprocess.run([sys.executable, '-m', 'omabridge', option], env=env,
                                capture_output=True, text=True, check=True)
        assert 'Private' not in result.stdout and 'private.test' not in result.stdout
        assert json.loads(result.stdout) == ([] if option == '--list-sites' else
                                             {'language': 'en', 'locked': True, 'sites': []})
    lock.path.write_text('{')
    result = subprocess.run([sys.executable, '-m', 'omabridge', '--bar-state'], env=env,
                            capture_output=True, text=True)
    assert result.returncode == 1 and not result.stdout
