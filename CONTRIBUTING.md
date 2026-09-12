# Entwicklung

OmaBridge besteht aus einem QML-Bar-Widget und einer Python-/PySide6-App.
Für lokale Entwicklung gelten die Schritte unter „Entwicklung und Prüfung“ in
der README. Änderungen bitte als Pull Request mit kurzer Beschreibung und
passender Prüfung einreichen.

Vor einem Pull Request:

```bash
.venv/bin/python -m pytest -q
bash -n scripts/*.sh
bash scripts/check-plugin.sh  # benötigt eine installierte Omarchy Shell
git diff --check
```

Die GitHub-CI testet Python 3.11 und 3.14 auf Linux und baut Python-Pakete.
Sie ersetzt weder die Prüfung des QML-Widgets auf Omarchy noch einen echten
Citrix-/HDX-Verbindungstest.

Fehlerberichte bitte mit OmaBridge-Version, Startmodus und nachvollziehbaren
Schritten erstellen. Anmeldeformulare möglichst als anonymisierte lokale Fixture
beifügen. Keine Passwörter, TOTP-Schlüssel, Sitzungstickets, echten ICA-Dateien oder
unbereinigten Kunden-Screenshots in Issues, Testdaten oder Commits aufnehmen.
