import io
import json
import os
import subprocess
import sys

import pytest
from PySide6.QtCore import QCoreApplication, QEvent
from omabridge.app_lock import AppLockStore
from omabridge.bar_ipc import start_server, unlock_from_stdin
from omabridge.models import Site
from omabridge.storage import SiteStore
from omabridge.ui import MainWindow
from test_browser import wait_for
from test_ui import MemoryVault


def call_cli(app, tmp_path, option, payload=None):
    env = {**os.environ, 'XDG_CONFIG_HOME': str(tmp_path)}
    process = subprocess.Popen([sys.executable, '-m', 'omabridge', option], env=env,
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if payload is not None:
        process.stdin.write(json.dumps(payload).encode() + b'\n')
    process.stdin.close()
    try:
        wait_for(app, lambda: process.poll() is not None, timeout=12)
        stdout = process.stdout.read().decode()
        stderr = process.stderr.read().decode()
        assert not stderr, stderr
        return process.returncode, json.loads(stdout)
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        process.stdout.close()
        process.stderr.close()


def test_live_bar_unlock_relock_and_site_launch_gate(app, tmp_path, monkeypatch):
    directory = tmp_path / 'omabridge'
    store, vault = SiteStore(directory), MemoryVault()
    site = Site('Demo office', 'https://citrix.test')
    store.save([site])
    AppLockStore(directory).configure('1234', 'pin')
    window = MainWindow(store, vault)
    server = start_server(window)
    try:
        assert not window.isVisible()
        _, state = call_cli(app, tmp_path, '--bar-state')
        assert state == {'language': 'en', 'locked': True, 'sites': []}
        _, state = call_cli(app, tmp_path, '--unlock-stdin', {'secret': 'wrong'})
        assert state['locked'] and not state['sites'] and 'Incorrect' in state['error']
        assert window.locked and not vault.threads
        _, state = call_cli(app, tmp_path, '--unlock-stdin', {'secret': '1234'})
        assert not state['locked'] and state['sites'][0]['id'] == site.id
        assert not window.locked and not window.isVisible() and not vault.threads
        _, state = call_cli(app, tmp_path, '--bar-state')
        assert not state['locked'] and state['sites'][0]['name'] == site.name
        assert 'url' not in state['sites'][0] and 'secret' not in state
        opened = []
        monkeypatch.setattr(window, 'connect_site', lambda: opened.append(window.current_site().id))
        window.open_site_id(site.id)
        assert opened == [site.id]
        window.lock_app()
        _, state = call_cli(app, tmp_path, '--bar-state')
        assert state['locked'] and not state['sites']
        window.open_site_id(site.id)
        assert opened == [site.id]  # A stale bar entry cannot bypass the re-lock.
        server.close()
        _, state = call_cli(app, tmp_path, '--bar-state')
        assert state['locked'] and not state['sites']  # No stale unlocked file/cache.
    finally:
        server.close()
        window.close()
        window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_background_app_accepts_cli_unlock_without_opening_portal(app, tmp_path):
    directory = tmp_path / 'omabridge'
    SiteStore(directory).save([Site('Demo', 'https://citrix.test')])
    AppLockStore(directory).configure('1234', 'pin')
    env = {**os.environ, 'XDG_CONFIG_HOME': str(tmp_path)}
    process = subprocess.Popen([sys.executable, '-m', 'omabridge', '--background'], env=env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    from omabridge.bar_ipc import server_name
    from PySide6.QtNetwork import QLocalSocket
    probe = QLocalSocket()
    def ready():
        probe.abort()
        probe.connectToServer(server_name(directory))
        return probe.waitForConnected(50)
    try:
        wait_for(app, ready)
        probe.abort()
        _, state = call_cli(app, tmp_path, '--unlock-stdin', {'secret': '1234'})
        assert not state['locked'] and state['sites'][0]['name'] == 'Demo'
        assert process.poll() is None
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_malformed_stdin_never_starts_app(app, monkeypatch):
    from omabridge import bar_ipc
    def unexpected(*args, **kwargs):
        pytest.fail('Invalid input must not reach IPC or launch an app')
    monkeypatch.setattr(bar_ipc, 'request', unexpected)
    for raw in [b'{\n', b'null\n', b'{"secret":false}\n', b'x' * (bar_ipc.MAX_REQUEST + 1)]:
        with pytest.raises(ValueError, match='Invalid bar request'):
            unlock_from_stdin(io.BytesIO(raw))


def test_bar_unlock_is_serialized_with_other_operations(app, tmp_path):
    AppLockStore(tmp_path).configure('1234', 'pin')
    window = MainWindow(SiteStore(tmp_path), MemoryVault())
    window.mutating = True
    replies = []
    window.unlock_with_secret('1234', replies.append)
    assert replies and 'wait' in replies[0]
    assert window.locked and not window.jobs
    window.mutating = False
    window.close()
    window.deleteLater()
