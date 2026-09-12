# OmaBridge

[English](usage.md) | **Deutsch**

[![CI](https://github.com/flathack/OmaBridge/actions/workflows/ci.yml/badge.svg)](https://github.com/flathack/OmaBridge/actions/workflows/ci.yml)

Citrix StoreFront aus der **Omarchy-Bar** öffnen: Site auswählen, mit Benutzername,
Passwort und TOTP anmelden, anschließend eine veröffentlichte App oder einen
virtuellen Desktop im Citrix-Portal starten.

![OmaBridge mit Site- und Sitzungs-Tabs (Vorschau)](tabs.png)

## Funktionen

- Mehrere Sites hinzufügen, bearbeiten und entfernen; direkte Auswahl im Bar-Popup.
- Benutzername, Passwort und TOTP-Schlüssel im Linux-Schlüsselbund (Secret Service).
- Automatische Anmeldung für erkannte StoreFront-Formulare, auch in mehreren Schritten.
- Pro Site **Citrix Workspace** oder **Browser / HTML5 in OmaBridge** auswählen.
- Eigene, nicht auf Datenträger gespeicherte Browser-Sitzung je Site; HTML5-Popups
  öffnen als zusätzliche Tabs und verwenden dieselbe Sitzung. Bereits geöffnete
  Sites bleiben beim Wechsel erhalten.
- Nur eine 42 Pixel hohe obere Leiste: Navigation, Tabs, Hinzufügen, Info und Menü.
  Portal und VM nutzen die gesamte übrige Fläche, ohne Seitenleiste, Innenränder oder Statusleiste.
- Formularfelder und Client-Auswahl bei angepassten Portalen über CSS-Selektoren konfigurieren.
- Ein laufendes OmaBridge-Fenster wird bei weiteren Bar-Klicks wiederverwendet.

## Voraussetzungen

- Omarchy mit der **Quickshell-Bar** und `omarchy plugin` (kein Waybar-Plugin).
- Python **3.11+**, pip und venv. Installation lädt PySide6 einschließlich Qt WebEngine.
- Ein laufender, entsperrbarer **Secret Service**, z. B. GNOME Keyring.
- Für den nativen Modus: Citrix Workspace für Linux mit `wfica` im PATH oder
  `/opt/Citrix/ICAClient/wfica`.
- Für HTML5: ein StoreFront-Portal mit serverseitig aktiviertem Browser-Client und
  passender HDX-/WebSocket-Konfiguration.
- Gültige HTTPS-Zertifikate und eine korrekt synchronisierte Systemzeit für TOTP.

## Installation

Repository klonen und installieren:

```bash
git clone https://github.com/flathack/OmaBridge.git
cd OmaBridge
./scripts/install.sh
```

Das Skript installiert die App in `~/.local/share/omabridge/venv`, einen Launcher in
`~/.local/bin/omabridge`, einen Desktop-Eintrag und das Plugin `local.omabridge` in
`~/.config/omarchy/plugins/`. Es sichert eine vorhandene `shell.json`, aktiviert das
Widget und platziert es rechts in der Bar. Es verändert keine Omarchy-Systemdateien.
XDG_CONFIG_HOME und XDG_DATA_HOME werden berücksichtigt.

Eine erneute Ausführung aktualisiert App und Widget. Der Schlüsselbund und die
gespeicherten Sites bleiben erhalten. `omarchy plugin add` allein installiert die
Python-App nicht; für die vollständige Installation das Skript verwenden.

## Sprache

Standard ist Englisch. Unter **⋮ → Settings → Language → Deutsch** stellst du
die App auf Deutsch. Die Auswahl steht in `~/.config/omabridge/settings.json`
und gilt sofort; das Bar-Menü übernimmt sie beim nächsten Öffnen. Bestehende
Sitzungen bleiben erhalten. Die Sprache des Citrix-Portals wird dort eingestellt.

## Erste Verbindung

1. In der Bar auf **Citrix → Sites verwalten** klicken und in OmaBridge oben **+** wählen.
2. Name und die vollständige **Receiver-for-Web-URL** eintragen, beispielsweise
   `https://citrix.firma.de/Citrix/StoreWeb/`. Keine URL mit Sitzungsticket speichern.
3. Benutzername, Passwort und **TOTP-Schlüssel** eintragen. Unterstützt werden
   Base32-Schlüssel und `otpauth://totp/...`-Links; kein einzelner sechsstelliger Code.
   Ein QR-Code muss als otpauth-Link bzw. Schlüssel vorliegen; Bildimport ist nicht enthalten.
4. Startmodus auswählen und speichern.
5. Im Bar-Menü die Site wählen. OmaBridge öffnet das Portal und meldet sich an.
6. Im Portal die gewünschte **App oder den Desktop** auswählen.

Bei der Client-Auswahl erkennt OmaBridge gängige englische und deutsche Schaltflächen
wie „Use web browser“, „Webbrowser verwenden“ und „Already installed“. Wenn das Portal
andere Schaltflächen verwendet, dort einmal den gewünschten Client wählen oder unter
**Anmeldeformular anpassen** einen Selektor hinterlegen. Der Startmodus ist eine
gespeicherte Auswahl mit automatischer Bedienung erkannter Portal-Schaltflächen;
er erzwingt keine serverseitig gesperrte Funktion und überschreibt nicht jede vorhandene
Portal-Präferenz. Ein späterer Wechsel kann eine zusätzliche Auswahl im Portal erfordern.

**Browser** bezeichnet den integrierten Chromium-Browser von OmaBridge, nicht einen
externen Firefox-/Chrome-Prozess. Dadurch bleiben Anmeldung und HTML5-Sitzung im selben
isolierten Kontext. Browser-Modus startet niemals versehentlich eine native ICA-Sitzung.

Die obere Leiste bleibt immer sichtbar. **⋮** enthält Site-Einstellungen, Startmodus,
Anmeldung und Vollbild; **ⓘ** zeigt Status und Portal-Adresse. **F11** schaltet Vollbild,
**Ctrl+Tab** wechselt Tabs, **Ctrl+W** schließt den aktuellen Tab. Geschlossene Sites
bleiben gespeichert und lassen sich unter **⋮ → Gespeicherte Sites** wieder öffnen.
HTML5-Apps und Desktops starten in eigenen Tabs; das Schließen des zugehörigen Site-Tabs
schließt auch diese Sitzungs-Tabs. Native Workspace-Fenster bleiben unabhängig.

## Angepasste Anmeldung und Fehler

Die Standard-Erkennung berücksichtigt unter anderem `#username`, `#password`, `#otp`,
`#passwd1`, die üblichen `name`-Attribute und `autocomplete`-Angaben. Individuelle
Portale lassen sich unter **⋮ → Site bearbeiten → Anmeldeformular anpassen** konfigurieren:

| Feld | Beispiel für einen CSS-Selektor |
| --- | --- |
| Benutzername | `#username` |
| Passwort | `#password` |
| TOTP | `#verificationCode` |
| Anmelde-Button | `#loginBtn` |
| Browser-Auswahl | `#useHtml5` (nur falls dieses Element im Portal existiert) |

Bei einer zweistufigen Anmeldung wartet OmaBridge nach Benutzername/Passwort auf das
nachgeladene Code-Formular und erzeugt den TOTP erst dafür neu. Auch Citrix-nFactor-
Formulare mit `input#response` vom Typ `password` und der Beschriftung „Kennwort“
werden über ihren sichtbaren Hinweis wie „Enter Your Microsoft verification code“
erkannt. Fehlt dieser eindeutige Hinweis, wird ein generisches Passwortfeld nicht
als TOTP-Feld behandelt. Ein später erscheinender Senden-Button wird weiter beobachtet.

OmaBridge füllt nur sichtbare, eindeutige Eingabefelder im Hauptdokument auf der exakt
gespeicherten HTTPS-Origin aus. Bei Weiterleitung auf einen anderen Host oder Port,
einer Anmeldung in einem iframe, unbekannten Feldern oder einem Passwortwechsel erfolgt
keine automatische Übergabe. Dann direkt im Portal fortfahren. Die aktuelle Portal-Adresse
wird unter **ⓘ** angezeigt, ohne Query-Parameter und Fragmente.

Jede Feldkombination wird pro Verbindungsversuch höchstens einmal abgeschickt,
insgesamt maximal drei Schritte. Nach jedem gesendeten Schritt bleiben weitere
90 Sekunden für das nächste Formular. Bei einer Fehlermeldung
zuerst Zugangsdaten prüfen. **Anmeldung erneut** erlaubt ausdrücklich einen weiteren
Versuch; **Automatik pausieren** stoppt weitere automatische Schritte. TOTP-Codes mit
weniger als fünf Sekunden Restlaufzeit werden nicht verwendet.

Falls der Schlüsselbund nicht erreichbar ist, wird ein Fehler angezeigt. OmaBridge
weicht nicht auf Klartextdateien aus. Wenn `wfica` fehlt, Workspace installieren oder
den Browser-Modus wählen. Wenn das Portal im Browser-Modus dennoch eine ICA-Datei liefert,
weist OmaBridge auf die nötige HTML5-Auswahl im Portal hin.

## Datenschutz und Sitzungen

- `~/.config/omabridge/sites.json`: Site-ID, Name, URL, Startmodus und Formular-Einstellungen;
  atomisch geschrieben, Verzeichnis mit Modus `0700`, Datei mit `0600`.
- Secret Service: Benutzername, Passwort und TOTP gemeinsam pro Site-ID. Kein
  Klartext-Fallback. Zugangsdaten liegen während der Nutzung auch im Prozessspeicher.
- Das Bar-Plugin erhält ausschließlich Site-ID, Anzeigename und Startmodus. Es hat
  keine eigene Zugangsdaten-Schnittstelle. Andere Prozesse unter demselben Linux-Benutzer
  sind keine isolierte Sicherheitsgrenze.
- Automatisierung läuft im isolierten JavaScript-Kontext. Die Portal-Felder erhalten
  die zur Anmeldung benötigten Werte; der TOTP-Schlüssel wird nie in das Portal injiziert.
- ICA-Downloads werden nur von der gespeicherten Portal-Origin angenommen, geprüft
  und mit zufälligem Dateinamen in einem privaten temporären Verzeichnis gespeichert.
  Workspace erhält ausschließlich den Dateipfad als Argument, keine Shell-Befehle.
  `RemoveICAFile=yes`, Prozess-Ende, Fünf-Minuten-Frist und App-Ende räumen Tickets auf.
- Chromium-Sandbox und Zertifikatsprüfung bleiben eingeschaltet. Portal-Konsolenlogs
  werden unterdrückt. Es gibt keine Telemetrie oder Fernspeicherung durch OmaBridge.
- **Tab schließen** auf einem Site-Tab verwirft den lokalen Kontext. Das ist kein serverseitiges Logoff;
  bei Bedarf vorher im Citrix-Portal abmelden. Native Workspace-Sitzungen laufen separat
  weiter; integrierte HTML5-Tabs schließen zusammen mit ihrer Portal-Sitzung.

## Entwicklung und Prüfung

Beiträge: [CONTRIBUTING.md](../CONTRIBUTING.md). Änderungen:
[CHANGELOG.md](../CHANGELOG.md). Vorbereitung einer Veröffentlichung:
[docs/releasing.md](releasing.md).

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
./scripts/run.sh
.venv/bin/python -m pytest -q
bash scripts/check-plugin.sh
.venv/bin/python scripts/preview.py
```

Die Tests prüfen TOTP anhand RFC-6238-Vektoren, private/atomische Speicherung,
Schlüsselbund-Fehler, CRUD samt Rollback, Chromium-Anmeldeformulare, Origin-Prüfungen,
Wiederholungsbegrenzung, Client-Auswahl und die ICA-Übergabe. Formular- und Downloadtests
verwenden lokale Fixtures; sie sind **kein Nachweis einer echten Citrix-Verbindung**.

Die erste Version wurde noch nicht gegen ein reales Kunden-StoreFront getestet.
Portal-Erkennung, Client-Auswahl und HDX-Kompatibilität müssen mit der konkreten
Installation verifiziert werden. Es gibt keinen eigenen StoreFront-API-Katalog:
App- und Desktop-Auswahl bleiben im Originalportal. SAML-Automatisierung, Push-MFA,
Client-Zertifikate und ein externer Browser mit Sitzungsübertragung sind nicht implementiert.

Technische Referenzen: [Citrix StoreFront Web API](https://developer-docs.citrix.com/en-us/storefront/storefront-web-api/getting-started.html),
[Citrix Browser-Zugriff](https://docs.citrix.com/en-us/storefront/current-release/get-started/user-access-options.html),
[Qt WebEngine Profile](https://doc.qt.io/qtforpython-6/PySide6/QtWebEngineCore/QWebEngineProfile.html).

## Entfernen

`omarchy plugin disable local.omabridge` nimmt das Widget aus der Bar. App-Dateien,
Launcher und Desktop-Eintrag können danach entfernt werden. Um die zugehörigen
Zugangsdaten mitzulentfernen, zuerst die Sites in OmaBridge löschen; das Deaktivieren
des Widgets löscht absichtlich keine Zugangsdaten.
