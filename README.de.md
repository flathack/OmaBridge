# OmaBridge

[English](README.md) | **Deutsch**

Mit diesem Plugin kannst du dich über die Omarchy-Bar **automatisiert auf
Citrix-Remote-Seiten einloggen**. Speichere mehrere Sites mit Benutzername,
Passwort und optionalem TOTP-Schlüssel, wähle eine Site aus und starte eine App oder einen
virtuellen Desktop mit **Citrix Workspace** oder im **integrierten HTML5-Browser**.

![OmaBridge-Demo: Desktop-Auswahl und Sitzungsstart](preview.png)

*Kombinierte Demo-Abbildung mit fiktiven Namen und Branding.*

- Zugangsdaten im Linux-Schlüsselbund (Secret Service).
- Mehrstufige Anmeldung mit TOTP-Abfrage nach Benutzername und Passwort.
- Eine kompakte obere Leiste mit Navigation und Tabs; der Rest bleibt frei.

- Farben folgen dem Omarchy-Theme live, auch in geöffneten Dialogen.
- Optionale App-Sperre per PIN oder Passwort mit frei wählbarer Länge (Einstellungen).

## Installation

Benötigt werden Omarchys **Quickshell-Bar**, CPython 3.11–3.14, pip/venv und ein
funktionierender Secret Service wie GNOME Keyring. Native Sitzungen benötigen
Citrix Workspace (`wfica`), Browser-Sitzungen serverseitig aktiviertes HTML5.

```bash
git clone https://github.com/flathack/OmaBridge.git
cd OmaBridge
./scripts/install.sh
```

Der Installer richtet App und Bar-Widget unter deinem Benutzerkonto ein.
Erneutes Ausführen aktualisiert beides. Abhängigkeiten sind festgelegt und SHA-256-geprüft.
Nur erkannte, unveränderte OmaBridge-Dateien werden ersetzt; bei Konflikten bricht die Installation ab.

Das Bar-Widget kannst du auch direkt über Omarchy hinzufügen und aktivieren:

```bash
omarchy plugin add https://github.com/flathack/OmaBridge.git --enable
```

Dieser Befehl installiert nur das Widget. Für die Python-App ist weiterhin der Installer oben nötig.

## Verwendung

**Citrix → Manage sites** (deutsch: **Sites verwalten**) und anschließend **+** wählen. HTTPS-Portal-URL,
Zugangsdaten eintragen. **TOTP-Speicherung ist optional und standardmäßig aus**.
Codes manuell im Portal eingeben oder einen Base32-Schlüssel bzw. `otpauth://`-Link
speichern. Das gemeinsame Speichern mit dem Passwort ist unsicher und liegt in
deiner Verantwortung; die App zeigt dazu eine Warnung.
Workspace oder Browser auswählen, speichern und die Site
in der Bar öffnen. App oder Desktop im Citrix-Portal auswählen.
Standard ist Englisch. Unter **⋮ → Settings → Language → Deutsch** wechselst du
sofort auf Deutsch. Die Auswahl bleibt gespeichert; Sitzungen bleiben geöffnet.

## Entfernen

`omarchy plugin disable io.github.flathack.omabridge` deaktiviert das Widget.
Zum Löschen der Zugangsdaten vorher die Sites in OmaBridge entfernen.
[Weitere Schritte](docs/usage.de.md#entfernen).

## Weitere Informationen

[Anleitung](docs/usage.de.md) · [Entwicklung](CONTRIBUTING.md) ·
[Änderungen](CHANGELOG.md) · [Security-Review](docs/security-review.md)

Entwicklungsversion: Die Kompatibilität muss mit deiner Citrix-Umgebung geprüft werden.
Die gemeldeten Code-Befunde sind bis einschließlich 0.4.3 behoben. Die Marketplace-Freigabe steht noch aus.

Lizenziert unter der [MIT-Lizenz](LICENSE).
