# Änderungen

## 0.4.2 — 2026-09-12

- Stabile Bar-Anzeige beim Polling: kein sekündlicher Wechsel zu „Laden“ und kein springendes Eingabefeld.
- Unveränderte Site-Listen werden nicht mehr bei jeder Abfrage neu aufgebaut.
- Hintergrundstart hält die Antwort-Pipe des Entsperrhelfers nicht mehr offen.
- Socket-Timeouts werden beim Schließen der Verbindung mit aufgeräumt.

## 0.4.1 — 2026-09-12

- PIN-/Passworteingabe direkt im Bar-Popup; danach Sites sofort auswählen und starten.
- Bar berücksichtigt den tatsächlichen Sperrstatus statt nur die eingerichtete Sperre.
- Hintergrundstart beim Entsperren; Site-Liste verschwindet nach Sperren oder Beenden.
- Geheimnisse ausschließlich über stdin und lokalen Benutzer-Socket, nicht über argv.

## 0.4.0 — 2026-09-12

- App-Farben folgen dem Omarchy-Theme und aktualisieren sich live, auch in Dialogen.
- Optionale App-Sperre per PIN oder Passwort mit frei wählbarer Länge.
- Sperren über Menü oder Ctrl+Shift+L; lokale Browser-Sitzungen werden geschlossen.
- Gesalzener scrypt-Hash, Wartezeiten bei Fehlversuchen und Schutz vor Zugriff über Bar/IPC.
- Sperre ändern oder deaktivieren nur mit bisheriger PIN bzw. bisherigem Passwort.

## 0.3.1 — 2026-09-12

- Gemeinsame Demo-Abbildung mit fiktiven Namen und Branding in beiden READMEs.
- TOTP-Speicherung ausdrücklich optional und bei neuen Sites deaktiviert.
- Sichtbare Warnung zum Risiko und zur Eigenverantwortung bei TOTP-Eingabe.
- Manuelle Code-Eingabe ohne Überschreiben oder automatisches Absenden.

## 0.3.0 — 2026-09-12

- Englisch als Standardsprache; Deutsch unter Settings → Language auswählbar.
- Sprachwechsel ohne Sitzungsverlust, dauerhaft gespeichert und auch im Bar-Menü.
- Passwortwechsel-Formulare werden vor jeder automatischen Eingabe blockiert.
- ICA-Downloads starten keinen Client mehr nach Wechsel zum Browser-Modus oder Sitzungsende.

## 0.2.0 — 2026-09-12

- OmaBridge als Omarchy-Quickshell-Bar-Widget mit mehreren Citrix-Sites.
- Zugangsdaten und TOTP-Schlüssel im Linux-Schlüsselbund.
- Mehrstufige Formular-Anmeldung einschließlich nachgelagerter TOTP-Abfrage.
- Start über Citrix Workspace oder den integrierten HTML5-Browser.
- Eine kompakte obere Leiste mit Navigation, Site- und Sitzungs-Tabs.
- Getrennte Browser-Kontexte je Site; HTML5-Tabs teilen den jeweiligen Kontext.
- 64 lokale Tests für Anmeldung, Speicherung, Oberfläche und ICA-Übergabe.

Dies ist der erste versionierte Entwicklungsstand. Die Kompatibilität mit einer
konkreten Citrix-Installation muss vor einer stabilen Veröffentlichung geprüft werden.
