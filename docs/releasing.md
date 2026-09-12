# Veröffentlichung vorbereiten

Repository: https://github.com/flathack/OmaBridge

Ein Push auf `main` führt Tests und Paketbau aus. Er veröffentlicht weder einen
GitHub-Release noch ein PyPI-Paket und trägt das Plugin in keinen Katalog ein.
Die CI-Artefakte sind Entwicklungs-Builds.

Vor dem ersten öffentlichen Release:

1. Projektlizenz festlegen und in `LICENSE` sowie den Paketmetadaten eintragen.
2. Installation aus einem frischen Checkout auf Omarchy prüfen. Der vollständige
   Einstieg ist `./scripts/install.sh`: `omarchy plugin add` installiert nur das
   Widget, nicht die erforderliche Python-App.
3. Anmeldung mit nachgelagertem TOTP, Workspace-Start und HTML5-VM auf einer echten
   Citrix-Installation prüfen, einschließlich Tab-Wechsel und Sitzungsende.
4. Plugin-ID festlegen. Der Entwicklungsstand verwendet `local.omabridge`.
   Ein Wechsel auf einen Herausgeber-Namensraum erfordert auch Anpassungen in
   Installer und Dokumentation sowie eine Migration der bestehenden Bar-Einträge.
5. Version in `pyproject.toml`, `src/omabridge/__init__.py` und `manifest.json`
   gemeinsam setzen; Changelog und Screenshots aktualisieren.
6. Tests, `bash scripts/check-plugin.sh` und Paketbau prüfen. Das Source-Archiv
   enthält auch QML-Widget, Manifest und Installer; ein Wheel allein enthält nur
   die Python-App. Installation aus dem entpackten Source-Archiv prüfen.
7. Nach erfolgreicher Prüfung einen Tag `v<VERSION>` anlegen und einen GitHub-Release
   mit Changelog, Source-Archiv und Prüfsummen erstellen. Bei noch ausstehender
   Praxiserprobung ausdrücklich als Vorabversion kennzeichnen.

Ein Omarchy-Katalogeintrag wird separat nach den dann geltenden Anforderungen
vorbereitet. Dieses Repository behauptet keine offizielle Aufnahme oder Freigabe
durch Omarchy oder Citrix.
