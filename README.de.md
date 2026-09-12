# OmaBridge

[English](README.md) | **Deutsch**

Mit diesem Plugin kannst du dich über die Omarchy-Bar **automatisiert auf
Citrix-Remote-Seiten einloggen**. Speichere mehrere Sites mit Benutzername,
Passwort und TOTP-Schlüssel, wähle eine Site aus und starte eine App oder einen
virtuellen Desktop mit **Citrix Workspace** oder im **integrierten HTML5-Browser**.

![OmaBridge-Vorschau](docs/tabs.png)

- Zugangsdaten im Linux-Schlüsselbund (Secret Service).
- Mehrstufige Anmeldung mit TOTP-Abfrage nach Benutzername und Passwort.
- Eine kompakte obere Leiste mit Navigation und Tabs; der Rest bleibt frei.

## Installation

Benötigt werden Omarchys **Quickshell-Bar**, Python 3.11+, pip/venv und ein
funktionierender Secret Service wie GNOME Keyring. Native Sitzungen benötigen
Citrix Workspace (`wfica`), Browser-Sitzungen serverseitig aktiviertes HTML5.

```bash
git clone https://github.com/flathack/OmaBridge.git
cd OmaBridge
./scripts/install.sh
```

Der Installer richtet App und Bar-Widget unter deinem Benutzerkonto ein.
Erneutes Ausführen aktualisiert beides. `omarchy plugin add` allein installiert die Python-App nicht.

## Verwendung

**Citrix → Manage sites** (deutsch: **Sites verwalten**) und anschließend **+** wählen. HTTPS-Portal-URL,
Zugangsdaten und **TOTP-Schlüssel** eintragen (Base32 oder `otpauth://`-Link,
kein Einmalcode). Workspace oder Browser auswählen, speichern und die Site
in der Bar öffnen. App oder Desktop im Citrix-Portal auswählen.
Standard ist Englisch. Unter **⋮ → Settings → Language → Deutsch** wechselst du
sofort auf Deutsch. Die Auswahl bleibt gespeichert; Sitzungen bleiben geöffnet.

## Entfernen

`omarchy plugin disable local.omabridge` deaktiviert das Widget.
Zum Löschen der Zugangsdaten vorher die Sites in OmaBridge entfernen.
[Weitere Schritte](docs/usage.de.md#entfernen).

## Weitere Informationen

[Anleitung](docs/usage.de.md) · [Entwicklung](CONTRIBUTING.md) ·
[Änderungen](CHANGELOG.md) · [Security-Review](docs/security-review.md)

Entwicklungsversion: Die Kompatibilität muss mit deiner Citrix-Umgebung geprüft werden.
Die beiden Code-Befunde sind in 0.3.0 behoben. Marketplace-Freigabe und Lizenz stehen noch aus.
