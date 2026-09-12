import os
import socket
import stat
import tempfile
from pathlib import Path

import pytest
from PySide6.QtNetwork import QLocalServer

from omabridge import ipc_security
from omabridge.bar_ipc import request


@pytest.fixture
def runtime(monkeypatch):
    # Keep Unix socket paths below Linux's 108-byte limit.
    with tempfile.TemporaryDirectory(prefix='omabridge-ipc-') as directory:
        monkeypatch.setenv('XDG_RUNTIME_DIR', directory)
        yield Path(directory)


def test_endpoints_are_private_and_config_isolated(runtime):
    first = Path(ipc_security.endpoint('bar', Path('/demo/first')))
    second = Path(ipc_security.endpoint('bar', Path('/demo/second')))
    assert first != second
    assert first.parent == runtime / 'omabridge'
    assert stat.S_IMODE(first.parent.stat().st_mode) == 0o700
    assert Path(ipc_security.endpoint('launcher')).parent == first.parent


@pytest.mark.parametrize('unsafe', ['permissions', 'symlink'])
def test_untrusted_runtime_directories_are_rejected(runtime, unsafe):
    if unsafe == 'permissions':
        runtime.chmod(0o777)
    else:
        target = runtime / 'elsewhere'
        target.mkdir(mode=0o700)
        (runtime / 'omabridge').symlink_to(target)
    with pytest.raises((ValueError, OSError)):
        ipc_security.endpoint('bar')


def test_public_socket_cannot_receive_unlock_secret(app, runtime):
    name = ipc_security.endpoint('bar')
    with socket.socket(socket.AF_UNIX) as impostor:
        impostor.bind(name)
        os.chmod(name, 0o666)
        impostor.listen()
        impostor.settimeout(.05)
        with pytest.raises(ValueError, match='Untrusted local IPC endpoint'):
            request({'command': 'unlock', 'secret': 'demo-pin-only'})
        with pytest.raises(TimeoutError):
            impostor.accept()


def test_wrong_peer_uid_receives_no_unlock_bytes(app, runtime, monkeypatch):
    server = QLocalServer()
    server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
    assert server.listen(ipc_security.endpoint('bar'))
    # Simulate a foreign UID even if path ownership checks succeeded. Normal
    # CLI integration tests exercise SO_PEERCRED against a real same-user peer.
    monkeypatch.setattr(ipc_security, 'peer_uid', lambda connection: os.getuid() + 1)
    try:
        with pytest.raises(ValueError, match='Untrusted local IPC peer'):
            request({'command': 'unlock', 'secret': 'demo-pin-only'})
        server.waitForNewConnection(100)
        connection = server.nextPendingConnection()
        assert connection is not None
        connection.waitForReadyRead(100)
        assert bytes(connection.readAll()) == b''
        connection.deleteLater()
    finally:
        server.close()
