import argparse
import json
import os
import sys

from .storage import SiteStore


def main():
    parser = argparse.ArgumentParser(description="OmaBridge · Citrix für Omarchy")
    parser.add_argument("--site", help="Gespeicherte Site-ID öffnen")
    parser.add_argument("--list-sites", action="store_true", help="Sites als JSON ausgeben (ohne Zugangsdaten)")
    args = parser.parse_args()
    if args.list_sites:
        try:
            print(json.dumps([{"id": s.id, "name": s.name, "mode": s.mode} for s in SiteStore().load()], ensure_ascii=False))
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
    server_name = f"omabridge-{os.getuid()}"
    client = QLocalSocket()
    client.connectToServer(server_name)
    if client.waitForConnected(500):
        client.write(json.dumps({"site": args.site}).encode() + b"\n")
        client.waitForBytesWritten(1000)
        client.disconnectFromServer()
        return 0
    from PySide6.QtCore import QLockFile, QStandardPaths
    lock = QLockFile(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.RuntimeLocation) + "/omabridge.lock")
    if not lock.tryLock(1000):
        print("OmaBridge startet bereits. Bitte erneut öffnen.", file=sys.stderr)
        return 1
    QLocalServer.removeServer(server_name)
    server = QLocalServer()
    server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
    if not server.listen(server_name):
        print("OmaBridge-IPC konnte nicht gestartet werden.", file=sys.stderr)
        return 1
    try:
        window = MainWindow()
    except (ValueError, OSError) as error:
        QMessageBox.critical(None, "OmaBridge", str(error))
        return 1
    connections = set()
    def incoming():
        while server.hasPendingConnections():
            socket = server.nextPendingConnection()
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
            QTimer.singleShot(3000, socket.abort)
            read()
    server.newConnection.connect(incoming)
    window.show()
    if args.site:
        QTimer.singleShot(0, lambda: window.open_site_id(args.site))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
