"""Linux IPC paths and peer checks shared by launcher and bar."""
import hashlib
import os
import socket
import stat
import struct
import pwd
import tempfile
from pathlib import Path

from .i18n import tr
from .storage import config_directory


def _private_directory(path):
    if not path.is_absolute():
        raise ValueError(tr('IPC runtime directory must be absolute and private.'))
    # Never follow a substituted directory symlink or repair untrusted permissions.
    path.mkdir(mode=0o700, exist_ok=True)
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise ValueError(tr('IPC runtime directory must be absolute and private.'))
    finally:
        os.close(fd)
    return path


def runtime_base():
    configured = os.environ.get('XDG_RUNTIME_DIR')
    base = Path(configured) if configured else Path(tempfile.gettempdir()) / ('runtime-' + pwd.getpwuid(os.getuid()).pw_name)
    return _private_directory(base)


def _suffix(directory=None):
    config = str((directory or config_directory()).resolve())
    return hashlib.sha256(config.encode()).hexdigest()[:16]


def endpoint(kind, directory=None):
    private = _private_directory(runtime_base() / 'omabridge')
    path = private / f'{kind}-{_suffix(directory)}.sock'
    if len(os.fsencode(path)) > 107:
        raise ValueError(tr('IPC runtime path is too long.'))
    return str(path)


def instance_lock_path():
    # Retain the previous lock filename only, inside the checked runtime directory,
    # so an older running app prevents a second instance during an upgrade.
    if config_directory().resolve() == (Path.home() / '.config/omabridge').resolve():
        name = f'omabridge-{os.getuid()}'
    else:
        name = f'omabridge-{os.getuid()}-{_suffix()}'
    return str(runtime_base() / (name + '.lock'))


def check_endpoint(path):
    try:
        info = Path(path).lstat()
    except FileNotFoundError:
        return
    if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise ValueError(tr('Untrusted local IPC endpoint.'))


def peer_uid(connection):
    # A duplicate descriptor lets Python inspect the peer without owning Qt's fd.
    with socket.socket(fileno=os.dup(connection.socketDescriptor())) as peer:
        credentials = peer.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize('3i'))
    return struct.unpack('3i', credentials)[1]


def require_same_user(connection):
    try:
        trusted = peer_uid(connection) == os.getuid()
    except (OSError, ValueError, AttributeError):
        trusted = False
    if not trusted:
        connection.abort()
        raise ValueError(tr('Untrusted local IPC peer.'))
