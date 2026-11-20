# LogWatch – Logüberwachung mit E-Mail-Alarm (Windows-Desktop-Client)

LogWatch überwacht eine Logdatei, erkennt Fehlereinträge und verschickt bei
einem Fehler die Logdatei automatisch per E-Mail an bis zu 5 Empfänger. Das
Programm läuft im Hintergrund mit System-Tray-Icon und kann automatisch mit
Windows starten.

---

## 1. Was die Software macht

- **Logdatei überwachen:** Eine konfigurierbare Logdatei wird in einem
  einstellbaren Intervall (Standard: 30 s) neu ausgelesen. Es werden nur die
  **neu hinzugekommenen Zeilen** seit der letzten Prüfung verarbeitet (die
  Leseposition/der Offset wird gemerkt).
- **Logrotation/Trunkierung:** Wird die Datei rotiert (ersetzt), geleert oder
  gekürzt, erkennt LogWatch das zuverlässig (über Dateigröße, Inode/Device und
  einen Fingerprint des Dateianfangs) und liest sauber ab Dateianfang weiter.
- **Zwei Fehlermodi (in der UI umschaltbar):**
  1. **Alle Fehler:** generische Fehler anhand von Standard-Stichwörtern
     (`ERROR`, `FEHLER`, `Exception`, `FATAL` – konfigurierbar, case-insensitive).
  2. **Nur bestimmte Fehler:** Du trägst eigene Muster **oder komplette
     Logzeilen** ein (eine pro Zeile). Nur dazu passende Zeilen lösen eine
     Meldung aus. Die Erkennung ist ein case-insensitiver Teilstring-Vergleich:
     Eine eingetragene Zeile „trifft", sobald sie als Textabschnitt in einer
     neuen Logzeile vorkommt.
     > **Tipp:** Wenn deine Logzeilen am Anfang einen wechselnden Zeitstempel
     > haben, trage den **stabilen Teil** der Zeile ein (die eigentliche
     > Fehlermeldung), nicht den Zeitstempel – sonst passt die Zeile wegen der
     > wechselnden Uhrzeit nie wieder.
- **E-Mail-Alarm:** Bei einem Fehler wird die Logdatei als **Anhang** versendet;
  die auslösende(n) Fehlerzeile(n) stehen zusätzlich im **E-Mail-Text**.
- **Anti-Spam / Throttling:** Nach einer gesendeten Mail gilt ein
  **Cooldown** (Standard 300 s). In dieser Zeit auftretende Fehler werden
  **gesammelt** und mit der nächsten Mail nach Ablauf des Cooldowns gebündelt
  verschickt – so entstehen keine hunderten Einzelmails.
- **Bis zu 5 Empfänger** mit je **E-Mail-Adresse, Firma, Maschine** und
  Aktiv-Schalter. Firma/Maschine erscheinen in **Betreff und E-Mail-Text**,
  damit sofort klar ist, von welcher Maschine/Firma der Fehler stammt.
- **Autostart mit Windows** (pro Benutzer, kein Admin nötig) per Checkbox.
- **System-Tray:** Fenster schließen minimiert in den Tray; Rechtsklick-Menü
  mit **Öffnen / Jetzt prüfen / Beenden**.
- **Verschlüsselte Konfiguration:** Die Einstellungen werden **nicht im
  Klartext** gespeichert (siehe Abschnitt 6).
- **Export/Import:** Eine einmal erstellte Konfiguration (inkl. deiner
  Fehlerzeilen-Liste) lässt sich als portable, verschlüsselte Datei exportieren
  und auf **beliebig vielen weiteren PCs** importieren.

---

## 2. Technische Architektur

Die **Kernlogik ist strikt vom UI getrennt** und damit ohne GUI testbar:

| Datei                     | Aufgabe                                                        |
|---------------------------|---------------------------------------------------------------|
| `logwatch/config.py`      | Konfiguration (Datenmodell, Laden/Speichern, Export/Import)   |
| `logwatch/crypto.py`      | Verschlüsselung der Konfiguration (Fernet, optional PBKDF2)   |
| `logwatch/log_reader.py`  | Inkrementelles Lesen, Offset, Rotations-/Trunkierungserkennung |
| `logwatch/detector.py`    | Fehlererkennung (beide Modi)                                   |
| `logwatch/mailer.py`      | E-Mail-Aufbau (Betreff/Text/Anhang) + SMTP-Versand            |
| `logwatch/monitor.py`     | Orchestrierung: lesen → erkennen → senden (mit Cooldown)      |
| `logwatch/autostart.py`   | Windows-Autostart (Registry-Run-Key, pro Benutzer)            |
| `logwatch/app_logging.py` | App-eigenes Logging (eigene Logdatei)                         |
| `logwatch/worker.py`      | Hintergrund-Thread für die Überwachung (QThread)              |
| `logwatch/ui.py`          | PySide6-GUI inkl. System-Tray                                 |
| `main.py`                 | Einstiegspunkt                                                 |

**Warum PySide6?** PySide6 bringt mit `QSystemTrayIcon` nativen Tray-Support
mit, ist gut mit PyInstaller paketierbar und braucht keine zusätzliche
Tray-Bibliothek (wie z.B. Tkinter + `pystray`). Dadurch ist das Projekt
einfacher und robuster zu paketieren.

---

## 3. Build-Anleitung für Windows (Schritt für Schritt)

> Diese Software läuft auf **Windows**. Die `.exe` muss **auf einem
> Windows-PC** gebaut werden (auf Linux/Mac kann keine Windows-.exe erzeugt
> werden).

1. **Python installieren** (3.10 oder neuer) von <https://www.python.org/downloads/>.
   Bei der Installation **„Add Python to PATH"** anhaken.
2. **Projekt entpacken/kopieren**, z.B. nach `C:\LogWatch`.
3. **Eingabeaufforderung (cmd)** im Projektordner öffnen.
4. **Automatisch bauen** – einfach das mitgelieferte Skript starten:
   ```bat
   build_windows.bat
   ```
   Das Skript legt eine virtuelle Umgebung an, installiert die
   Abhängigkeiten, führt die Tests aus und baut die EXE.
5. **Fertig:** Die Datei liegt unter **`dist\LogWatch.exe`**.

### Alternativ: manuell bauen
```bat
python -m venv .venv
.venv\Scripts\activate.bat
pip install -r requirements.txt
pip install pyinstaller
pyinstaller logwatch.spec --noconfirm
```
Ergebnis: `dist\LogWatch.exe`.

### Ohne Build einfach starten (zum Testen)
```bat
pip install -r requirements.txt
python main.py
```

---

## 4. Installation & Autostart

- **Installation:** Es ist keine klassische Installation nötig. Kopiere
  `LogWatch.exe` an einen festen Ort, z.B. `C:\Program Files\LogWatch\` oder
  `C:\LogWatch\`.
- **Autostart:** In der App die Checkbox **„Mit Windows starten"** aktivieren
  und **Speichern** klicken. LogWatch trägt sich dann im Registry-Run-Key
  `HKEY_CURRENT_USER\...\Run` ein (pro Benutzer, **kein Admin nötig**). Beim
  nächsten Login startet LogWatch automatisch. Checkbox deaktivieren + Speichern
  entfernt den Eintrag wieder.
- **Hintergrund/Tray:** Das Schließen des Fensters (X) beendet LogWatch **nicht**,
  sondern minimiert es in den System-Tray (Symbol unten rechts). Über
  Rechtsklick auf das Tray-Icon: **Öffnen / Jetzt prüfen / Beenden**.
- **Config/Logs:** Konfiguration und App-Logdatei liegen unter
  `%APPDATA%\LogWatch\` (`config.dat`, `logwatch_app.log`).

---

## 5. SMTP-Daten eintragen (Sende-Postfach)

In der App unter **„SMTP-Einstellungen"**:

| Feld        | Beschreibung                                                   |
|-------------|---------------------------------------------------------------|
| Host        | SMTP-Server des Sende-Postfachs, z.B. `smtp.office365.com`     |
| Port        | z.B. `587` (STARTTLS) oder `465` (SSL/TLS)                     |
| Benutzer    | Login des Sende-Postfachs (meist die E-Mail-Adresse)          |
| Passwort    | Passwort / App-Passwort (wird **nicht im Klartext** angezeigt) |
| Absender    | Absenderadresse (i.d.R. = Benutzer)                           |
| Sicherheit  | STARTTLS (587), SSL/TLS (465) oder keine                       |

> **Wichtig:** Hier muss das von **euch bereitgestellte Sende-Postfach**
> eingetragen werden. In der Auslieferung stehen nur **Platzhalter**
> (`smtp.example.com` usw.) – es sind **keine echten Zugangsdaten** hinterlegt.

Mit **„Test-E-Mail senden"** kannst du die Einstellungen prüfen, bevor du die
Überwachung startest.

### Hinweis zu Gmail / Office365 (App-Passwörter)
- **Gmail:** Normales Kontopasswort funktioniert i.d.R. **nicht**. Du brauchst
  ein **App-Passwort** (erfordert aktivierte 2-Faktor-Authentifizierung):
  Google-Konto → Sicherheit → App-Passwörter. Host `smtp.gmail.com`, Port `587`
  (STARTTLS) oder `465` (SSL).
- **Office365 / Outlook:** Host `smtp.office365.com`, Port `587` (STARTTLS).
  Je nach Organisationsrichtlinie ist ebenfalls ein **App-Passwort** bzw. die
  Freigabe von „SMTP AUTH" durch den Administrator nötig.

---

## 6. Verschlüsselung der Konfiguration

Die Konfiguration wird **verschlüsselt** gespeichert (`config.dat`, kein
Klartext, keine `.ini`). Verwendet wird `cryptography`/Fernet (AES-128-CBC +
HMAC).

- **Ohne Master-Passwort:** Es wird ein in der App eingebetteter Schlüssel
  verwendet. Das verhindert beiläufiges Mitlesen der Datei, ist aber
  naturgemäß **schwächer**, weil der Schlüssel in der Anwendung steckt.
- **Mit Master-Passwort (empfohlen):** Unter „Optionen" → **„Master-Passwort
  setzen/ändern…"** ein Passwort vergeben und **Speichern**. Der Schlüssel wird
  dann per **PBKDF2-HMAC-SHA256** aus dem Passwort abgeleitet. Die Datei ist
  anschließend nur mit diesem Passwort entschlüsselbar; beim Start fragt
  LogWatch danach.

---

## 7. Konfiguration auf mehrere PCs ausrollen

1. Auf einem PC alles einrichten (Fehlermodus, Fehlerzeilen, SMTP, Empfänger …).
2. **„Konfiguration exportieren…"** → es entsteht eine portable, verschlüsselte
   Datei (`logwatch_profil.dat`). Optional mit Master-Passwort schützen.
3. Diese Datei auf die anderen PCs kopieren.
4. Dort LogWatch starten → **„Konfiguration importieren…"** → Datei wählen
   (ggf. Master-Passwort eingeben).
5. **Firma/Maschine pro PC anpassen** (damit in der Mail die richtige Maschine
   steht) und **Speichern**.

So erstellst du die (Fehler-)Konfiguration **einmal** und spielst sie auf allen
Maschinen ein.

---

## 8. Tests (Kernlogik)

Die plattformunabhängige Kernlogik ist mit Unit-Tests abgedeckt
(Fehlererkennung in beiden Modi, inkrementelles Lesen mit Offset, Logrotation,
Config-Roundtrip & Verschlüsselung, E-Mail-Message-Aufbau mit Anhang,
Throttling/Cooldown).

```bash
pip install pytest
python -m pytest -q
```

---

## 8a. Zentrales Dashboard (optionaler Upload)

Zusätzlich zum E-Mail-Versand kann der Client jeden erkannten Fehler an ein
zentrales Web-Dashboard melden (eigenes Projekt `logwatch-dashboard`). Der
E-Mail-Versand bleibt davon unberührt – beides läuft parallel.

- **Aktivierung in der GUI:** Gruppe „Zentrales Dashboard“ → Haken setzen,
  Dashboard-URL (z.B. `https://logwatch-dash.abacusai.cloud`) und das
  **Upload-Token** eintragen (muss mit dem Token des Dashboards übereinstimmen).
- **Maschinen-Identität:** Gruppe „Maschinen-Identität“ → `Maschinen-ID` und
  `Firma/Kunde` setzen. Die Maschinen-ID identifiziert das Gerät im Dashboard.
- **Automatisch ermittelt:** TeamViewer-ID (für die Fernwartung) und ein
  Hardware-Fingerprint (für die Kopier-Erkennung im Dashboard). Die TeamViewer-ID
  erscheint zusätzlich im Betreff und Text der Benachrichtigungs-E-Mail.
- **Robustheit:** Schlägt der Upload fehl (offline, Timeout, Serverfehler), wird
  das nur protokolliert – die App läuft weiter und die E-Mail wird trotzdem
  versendet.

**Upload-API-Vertrag** (Feldnamen müssen zum Dashboard passen):

```
POST {dashboard-url}/api/v1/reports
Header:  X-Upload-Token: <Token>
Body:    multipart/form-data
  - Feld  "payload"  : JSON (machine_id, company, hardware_id, teamviewer_id,
                       hostname, timestamp, error_count, error_lines[], log_filename)
  - Datei "logfile"  : die Logdatei (optional)
```

Details siehe `README.md` im Projekt `logwatch-dashboard`.

---

## 9. Releases & Lizenz

- **Release erstellen (mit automatischem Windows-Build):** siehe
  [`RELEASE.md`](RELEASE.md). Kurzfassung: `VERSION` + `CHANGELOG.md`
  aktualisieren, Tag `vX.Y.Z` pushen → GitHub Actions baut die `LogWatch.exe`
  und legt automatisch ein Release mit der EXE als Download an.
- **Änderungen:** siehe [`CHANGELOG.md`](CHANGELOG.md).
- **Lizenz:** MIT, siehe [`LICENSE`](LICENSE).
- **CI:** Bei jedem Push/PR laufen die Unit-Tests automatisch
  (`.github/workflows/tests.yml`), ein Sicherheits-Audit der Abhängigkeiten
  (`.github/workflows/security-audit.yml`) und der Doku-Check.

---

## 10. Hinweise / Grenzen

- Die GUI, der Autostart (Registry) und das finale PyInstaller-Build sind nur
  unter **Windows** lauffähig/testbar. Die Kernlogik wurde plattformunabhängig
  getestet.
- Die eingebettete Verschlüsselung (ohne Master-Passwort) schützt vor
  beiläufigem Mitlesen, nicht gegen gezielte Angreifer mit Zugriff auf die
  Anwendung. Für echten Schutz ein **Master-Passwort** verwenden.

## Projektpflege

- **Versionen/Änderungen:** siehe [`CHANGELOG.md`](CHANGELOG.md).
- **Offene Aufgaben/Ideen:** siehe [`TODO.md`](TODO.md).

Konvention: Bei jeder Änderung werden `CHANGELOG.md`, `TODO.md` und diese
`README.md` mitgepflegt.

### Automatisierte Doku-Pflege

- **Während der Entwicklung:** Änderungen einfach unter der Überschrift
  `## [Unveröffentlicht]` in `CHANGELOG.md` sammeln.
- **Release erstellen:** `python scripts/release.py X.Y.Z --push`
  - verschiebt den Block „Unveröffentlicht" in einen neuen Versionsabschnitt
    `## [X.Y.Z] – <Datum>`, aktualisiert `VERSION` und die Vergleichs-Links,
  - committet, setzt den Tag `vX.Y.Z` und pusht ihn → GitHub Actions baut
    automatisch die `LogWatch.exe` und legt das Release an.
  - Ohne `--push` werden nur die Doku-Dateien lokal aktualisiert.
- **CI-Prüfung `Doku-Check`:** schlägt fehl, wenn Code geändert wurde, ohne den
  `CHANGELOG.md` zu pflegen – so bleibt die Dokumentation verlässlich aktuell.

### Automatisierte Abhängigkeits- und Sicherheits-Pflege

- **Dependabot (`.github/dependabot.yml`):** prüft wöchentlich die
  Python-Pakete (`requirements.txt`) und die GitHub-Actions und schlägt
  Aktualisierungen als **gesammelte Pull-Requests** vor. Es wird nichts
  automatisch zusammengeführt – jeder Update-PR wird von dir geprüft und
  bestätigt. Bekannte Sicherheitslücken werden zusätzlich automatisch als
  PR gemeldet. Der Actions-Teil hält die Workflows aktuell (behebt u. a. die
  „Node 20"-Deprecation-Warnung).
- **Sicherheits-Audit (`.github/workflows/security-audit.yml`):** prüft die
  Abhängigkeiten bei jedem Push/PR und zusätzlich wöchentlich mit `pip-audit`
  auf bekannte Schwachstellen.
- **Tipp:** Die Tests als verpflichtende Merge-Bedingung lassen sich einmalig in
  GitHub aktivieren: *Settings → Branches → Add branch ruleset/Protection rule*
  für `main`, dort „Require status checks to pass" setzen und die Checks
  `Tests`, `Security-Audit` und `Doku-Check` auswählen. Dann kann ein PR nur
  gemergt werden, wenn alle Prüfungen grün sind.
