from .i18n import tr, set_language, language
from .preferences import PreferencesStore

import argparse
import json
import os
import sys

from .storage import SiteStore
from .app_lock import AppLockStore


def main():
    try:
        set_language(PreferencesStore().load())
    except (ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 1
    parser = argparse.ArgumentParser(description=tr("OmaBridge · Citrix for Omarchy"))
    parser.add_argument("--site", help=tr("Open a saved site ID"))
    parser.add_argument("--list-sites", action="store_true", help=tr("List sites as JSON (without credentials)"))
    parser.add_argument("--bar-state", action="store_true", help=tr("Bar language and sites as JSON (without credentials)"))
    parser.add_argument("--background", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--unlock-stdin", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.unlock_stdin:
        from .bar_ipc import unlock_from_stdin
        try:
            print(json.dumps(unlock_from_stdin(sys.stdin.buffer), ensure_ascii=False))
        except (ValueError, OSError) as error:
            print(json.dumps({"language": language(), "locked": True, "sites": [], "error": str(error)}, ensure_ascii=False))
            return 1
        return 0
    if args.list_sites or args.bar_state:
        try:
            if args.bar_state:
                from .bar_ipc import request
                state = request({"command": "state"})
                if state is not None:
                    print(json.dumps(state, ensure_ascii=False))
                    return 0
            locked = bool(AppLockStore().load())
            sites = [] if locked else [{"id": s.id, "name": s.name, "mode": s.mode} for s in SiteStore().load()]
            print(json.dumps({"language": language(), "locked": locked, "sites": sites} if args.bar_state else sites, ensure_ascii=False))
        except (ValueError, OSError) as error:
            print(str(error), file=sys.stderr)
            return 1
        return 0
    from PySide6.QtCore import QCoreApplication, QTimer
    from PySide6.QtNetwork import QLocalServer, QLocalSocket
    from PySide6.QtWidgets import QApplication, QMessageBox
    from .ui import MainWindow

    # Every file we create, including Chromium temporary data, is user-private.
    os.umask(0o077)
    QCoreApplication.setApplicationName("omabridge")
    QCoreApplication.setOrganizationName("OmaBridge")
    app = QApplication(sys.argv[:1])
    app.setDesktopFileName("omabridge")
    from .bar_ipc import launcher_name
    from .ipc_security import check_endpoint, require_same_user, instance_lock_path
    try:
        server_name = launcher_name()
        check_endpoint(server_name)
        lock_path = instance_lock_path()
    except (ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 1
    client = QLocalSocket()
    client.connectToServer(server_name)
    if client.waitForConnected(500):
        try:
            require_same_user(client)
        except ValueError as error:
            print(str(error), file=sys.stderr)
            return 1
        client.write(json.dumps({"site": args.site, "background": args.background}).encode() + b"\n")
        client.waitForBytesWritten(1000)
        client.disconnectFromServer()
        return 0
    from PySide6.QtCore import QLockFile
    lock = QLockFile(lock_path)
    if not lock.tryLock(1000):
        print(tr("OmaBridge is already starting. Please try opening it again."), file=sys.stderr)
        return 1
    QLocalServer.removeServer(server_name)
    server = QLocalServer()
    server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
    if not server.listen(server_name):
        print(tr("Could not start OmaBridge IPC."), file=sys.stderr)
        return 1
    try:
        window = MainWindow()
        from .bar_ipc import start_server
        bar_server = start_server(window)
    except (ValueError, OSError) as error:
        QMessageBox.critical(None, "OmaBridge", str(error))
        return 1
    connections = set()
    def incoming():
        while server.hasPendingConnections():
            socket = server.nextPendingConnection()
            try:
                require_same_user(socket)
            except ValueError:
                socket.deleteLater()
                continue
            connections.add(socket)
            def read(socket=socket):
                if socket.bytesAvailable() > 4096:
                    socket.abort()
                    return
                if not socket.canReadLine():
                    return
                try:
                    message = json.loads(bytes(socket.readLine(4096)))
                    site_id = message.get("site")
                    if not message.get("background"):
                        window.showNormal()
                        window.raise_()
                        window.activateWindow()
                    if isinstance(site_id, str):
                        window.open_site_id(site_id)
                except (ValueError, TypeError, AttributeError, OSError):
                    pass
                socket.disconnectFromServer()
            socket.readyRead.connect(read)
            socket.disconnected.connect(lambda socket=socket: (connections.discard(socket), socket.deleteLater()))
            timeout = QTimer(socket)
            timeout.setSingleShot(True)
            timeout.timeout.connect(socket.abort)
            timeout.start(3000)
            read()
    server.newConnection.connect(incoming)
    if not args.background:
        window.show()
    if args.site:
        QTimer.singleShot(0, lambda: window.open_site_id(args.site))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
