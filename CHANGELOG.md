# Changelog

Alle nennenswerten Änderungen an diesem Projekt werden in dieser Datei
dokumentiert.

Das Format orientiert sich an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/),
und das Projekt folgt der [Semantischen Versionierung](https://semver.org/lang/de/).

## [Unveröffentlicht]
### Hinzugefügt
- **Update-Funktion:** Der Client prüft über die GitHub-API, ob ein neueres
  Release verfügbar ist, und kann die neue `LogWatch.exe` herunterladen und
  installieren (unter Windows: Austausch der laufenden EXE + Neustart). Neue
  Einstellungsgruppe „Updates" mit der Option **„Beim Start nach Updates
  suchen"**, einem Button **„Nach Updates suchen"** und der Anzeige der aktuellen
  Version. Prüfung und Download laufen im Hintergrund (kein Blockieren der UI).
- **Optionales GitHub-Token (PAT):** In der Update-Gruppe kann ein persönliches
  Zugriffs-Token hinterlegt werden (maskiertes Feld). Es wird **verschlüsselt**
  in der Konfiguration gespeichert und bei vorhandenem Wert als
  `Authorization: Bearer`-Header gesendet. Dadurch funktioniert die
  Update-Prüfung sowohl für das aktuell öffentliche Repo als auch nahtlos
  weiter, falls das Repo später auf privat gestellt wird. Das Token erscheint
  niemals im Klartext in Logs oder Fehlermeldungen.
- **Automatisierte Doku-Pflege:** Release-Skript `scripts/release.py`, das beim
  Release den Abschnitt „Unveröffentlicht" des CHANGELOG in einen neuen
  Versionsabschnitt überführt, `VERSION` setzt und (mit `--push`) Tag/Build auslöst.
- **CI-Prüfung `Doku-Check`** (GitHub Actions): schlägt fehl, wenn Code geändert
  wurde, ohne den CHANGELOG zu pflegen.
- **Automatisierte Abhängigkeits-Pflege (Dependabot):** `.github/dependabot.yml`
  prüft wöchentlich sowohl die Python-Pakete (`requirements.txt`) als auch die
  GitHub-Actions und schlägt Aktualisierungen als **gesammelte Pull-Requests**
  vor. Zusammengeführt wird nichts automatisch – die Kontrolle bleibt bei dir.
  Sicherheits-Updates für bekannte Schwachstellen werden zusätzlich automatisch
  als PR eröffnet. (Behebt u. a. die „Node 20"-Deprecation-Warnung der Actions.)
- **Sicherheits-Audit `Security-Audit`** (GitHub Actions,
  `.github/workflows/security-audit.yml`): prüft die Abhängigkeiten bei jedem
  Push/PR und wöchentlich mit `pip-audit` auf bekannte Sicherheitslücken.

### Geändert
- Abhängigkeiten aktualisiert (Dependabot): `PySide6` (>=6.12.0), `cryptography`
  (>=50.0.2) und `requests` (>=2.34.2). Tests und Sicherheits-Audit grün.

## [0.2.0] – 2026-11-19
### Hinzugefügt
- Auslesen der **TeamViewer-ID** (aus der Windows-Registry) und Mitsenden in der
  Alarm-E-Mail (Betreff und Text).
- Ermittlung einer stabilen **Hardware-ID** (Fingerprint des PCs) zur
  Wiedererkennung der Maschine.
- Neues Feld **Maschinen-ID** (vom Betreiber vergeben) sowie **Firma/Kunde**.
- **Upload an das zentrale Dashboard**: Bei einem erkannten Fehler wird
  zusätzlich zur E-Mail ein Bericht (Maschinen-ID, Hardware-ID, TeamViewer-ID,
  Firma, Hostname, Fehlerzeilen, Zeitstempel) samt Logdatei an die
  Dashboard-API hochgeladen. Robust gegen Netzwerkfehler; der E-Mail-Versand
  bleibt davon unberührt. Upload in der UI an-/abschaltbar.
- Neue UI-Felder für Maschinen-ID, Firma/Kunde, Dashboard-URL, Upload-Token
  und Upload an/aus; Konfiguration abwärtskompatibel erweitert (alte Profile
  laden weiter, Export/Import angepasst).

### Hinweise
- Der **E-Mail-Versand bleibt** vollständig erhalten; das Dashboard ist eine
  zusätzliche Meldewege-Option.

## [0.1.0] – 2026-11-19
### Hinzugefügt
- Überwachung einer konfigurierbaren Logdatei in einstellbarem Intervall
  (Standard 30 s); es werden nur neu hinzugekommene Zeilen verarbeitet
  (Offset wird gemerkt).
- Robuste Erkennung von Logrotation/Trunkierung (Dateigröße, Inode/Device,
  Fingerprint des Dateianfangs – auch bei Inode-Recycling).
- Zwei Fehlermodi, in der UI umschaltbar:
  - **Alle Fehler** anhand generischer Stichwörter
    (`ERROR`, `FEHLER`, `Exception`, `FATAL`, konfigurierbar, case-insensitive).
  - **Nur bestimmte Fehler** über eigene Muster bzw. komplette Logzeilen.
- E-Mail-Alarm per SMTP: Logdatei als Anhang, auslösende Fehlerzeile(n) im Text.
- Anti-Spam/Throttling über konfigurierbaren Cooldown (Standard 300 s) mit
  Sammeln der Fehler während der Sperrzeit.
- Bis zu 5 Empfänger mit E-Mail, Firma, Maschine, Aktiv-Schalter; Firma/Maschine
  in Betreff und Text.
- SMTP-Einstellungen in der UI (Host, Port, Benutzer, Passwort maskiert,
  STARTTLS/SSL, Absender); nur Platzhalter-Defaults, keine echten Zugangsdaten.
- System-Tray (Schließen minimiert in den Tray; Menü Öffnen / Jetzt prüfen /
  Beenden).
- Autostart mit Windows (pro Benutzer, Registry-Run-Key, kein Admin nötig).
- Verschlüsselte Konfiguration (Fernet; optional Master-Passwort via PBKDF2);
  keine Klartext-/INI-Datei.
- Export/Import der Konfiguration als portable, verschlüsselte Datei zum
  Ausrollen auf mehrere PCs.
- App-eigenes Logging (`logwatch_app.log`) zur Nachverfolgung von Versandfehlern.
- Unit-Tests der Kernlogik inkl. End-to-End-SMTP-Test.
- PyInstaller-Spec, `build_windows.bat` und GitHub-Actions-Workflows für Tests
  und Windows-Release.

[Unveröffentlicht]: https://github.com/Obi811/Logwatch/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/Obi811/Logwatch/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Obi811/Logwatch/releases/tag/v0.1.0
