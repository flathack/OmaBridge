"""Live bar state and unlock requests over a user-only local socket.

Lock secrets travel via stdin and IPC, never argv, environment or a state file.
The running MainWindow remains the authority for successful authentication.
"""
import hashlib
import json
import os
import time

from PySide6.QtCore import QCoreApplication, QProcess, QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from .i18n import language, tr
from .storage import config_directory
from pathlib import Path

MAX_REQUEST = 256 * 1024
MAX_RESPONSE = 8 * 1024 * 1024


def server_name(directory=None):
    config = str((directory or config_directory()).resolve())
    suffix = hashlib.sha256(config.encode()).hexdigest()[:16]
    return f'omabridge-bar-{os.getuid()}-{suffix}'


def launcher_name():
    # Keep the installed default endpoint; isolate alternate XDG configurations.
    if config_directory().resolve() == (Path.home() / '.config/omabridge').resolve():
        return f'omabridge-{os.getuid()}'
    return server_name().replace('omabridge-bar-', 'omabridge-')


def window_state(window):
    return {'language': language(), 'locked': window.locked,
            'sites': [] if window.locked else [
                {'id': site.id, 'name': site.name, 'mode': site.mode} for site in window.sites]}


def start_server(window):
    server = QLocalServer(window)
    server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
    name = server_name(window.store.directory)
    # Main's singleton lock is held before calling this function.
    QLocalServer.removeServer(name)
    if not server.listen(name):
        raise OSError(tr('Could not start OmaBridge IPC.'))
    connections = set()
    def incoming():
        while server.hasPendingConnections():
            socket = server.nextPendingConnection()
            connections.add(socket)
            pending = [False]
            def reply(error=None, socket=socket):
                if socket not in connections:
                    return
                state = window_state(window)
                if error:
                    state['error'] = str(error)
                socket.write(json.dumps(state, ensure_ascii=False).encode() + b'\n')
                socket.disconnectFromServer()
            def read(socket=socket, reply=reply, pending=pending):
                if pending[0]:
                    return
                if socket.bytesAvailable() > MAX_REQUEST:
                    socket.abort()
                    return
                if not socket.canReadLine():
                    return
                pending[0] = True  # One request per connection; no queued password guesses.
                try:
                    message = json.loads(bytes(socket.readLine(MAX_REQUEST)))
                    command = message.get('command')
                    if command == 'state':
                        reply()
                    elif command == 'unlock' and isinstance(message.get('secret'), str):
                        window.unlock_with_secret(message.pop('secret'), reply)
                    else:
                        raise ValueError
                except (ValueError, TypeError, AttributeError):
                    reply(tr('Invalid bar request.'))
            socket.readyRead.connect(read)
            socket.disconnected.connect(lambda socket=socket: (connections.discard(socket), socket.deleteLater()))
            timeout = QTimer(socket)
            timeout.setSingleShot(True)
            timeout.timeout.connect(socket.abort)
            timeout.start(10000)
            read()
    server.newConnection.connect(incoming)
    return server


def request(message, directory=None, connect_timeout=0):
    # CLI callers do not need QApplication or Qt WebEngine.
    application = QCoreApplication.instance() or QCoreApplication([])
    socket = QLocalSocket()
    deadline = time.monotonic() + connect_timeout
    while True:
        socket.connectToServer(server_name(directory))
        if socket.waitForConnected(100):
            break
        socket.abort()
        if time.monotonic() >= deadline:
            return None
        time.sleep(.05)
    payload = json.dumps(message, ensure_ascii=False).encode() + b'\n'
    if len(payload) > MAX_REQUEST:
        socket.abort()
        raise ValueError(tr('Invalid bar request.'))
    socket.write(payload)
    if not socket.waitForBytesWritten(1000):
        socket.abort()
        raise ValueError(tr('OmaBridge did not respond. Reopen the app and try again.'))
    deadline = time.monotonic() + 8
    while not socket.canReadLine():
        remaining = int((deadline - time.monotonic()) * 1000)
        if socket.bytesAvailable() > MAX_RESPONSE or remaining <= 0 or not socket.waitForReadyRead(remaining):
            socket.abort()
            raise ValueError(tr('OmaBridge did not respond. Reopen the app and try again.'))
    if socket.bytesAvailable() > MAX_RESPONSE:
        socket.abort()
        raise ValueError(tr('Invalid bar response.'))
    data = json.loads(bytes(socket.readLine(MAX_RESPONSE)))
    socket.disconnectFromServer()
    if not isinstance(data, dict) or type(data.get('locked')) is not bool or not isinstance(data.get('sites'), list):
        raise ValueError(tr('Invalid bar response.'))
    return data


def start_background():
    import sys
    process = QProcess()
    process.setProgram(sys.executable)
    process.setArguments(['-m', 'omabridge', '--background'])
    # Detached children must not keep the bar helper's pipes open. Otherwise
    # StdioCollector waits for the entire app to exit before delivering its JSON.
    process.setStandardInputFile(QProcess.nullDevice())
    process.setStandardOutputFile(QProcess.nullDevice())
    process.setStandardErrorFile(QProcess.nullDevice())
    return process.startDetached()


def unlock_from_stdin(stream):
    application = QCoreApplication.instance() or QCoreApplication([])
    raw = stream.readline(MAX_REQUEST + 1)
    try:
        if len(raw) > MAX_REQUEST:
            raise ValueError
        message = json.loads(raw)
        if not isinstance(message, dict) or not isinstance(message.get('secret'), str):
            raise ValueError
    except (ValueError, TypeError):
        raise ValueError(tr('Invalid bar request.')) from None
    command = {'command': 'unlock', 'secret': message.pop('secret')}
    result = request(command)
    if result is None:
        # Start a hidden app only on an explicit unlock attempt, never on polling.
        if not start_background():
            raise OSError(tr('OmaBridge did not respond. Reopen the app and try again.'))
        result = request(command, connect_timeout=5)
    if result is None:
        raise ValueError(tr('OmaBridge did not respond. Reopen the app and try again.'))
    return result
