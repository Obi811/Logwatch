# Release-Anleitung

Diese Anleitung beschreibt, wie du eine neue Version von **LogWatch**
veröffentlichst. Die Windows-`.exe` wird dabei automatisch von GitHub Actions
auf einem Windows-Runner gebaut und an das Release angehängt.

## Voraussetzungen (einmalig)
1. Repository auf GitHub vorhanden (z.B. `https://github.com/USERNAME/Logwatch`).
2. Dieses Projekt ist in das Repo gepusht (siehe unten „Erstes Hochladen").
3. In den Repo-Einstellungen unter **Settings → Actions → General →
   Workflow permissions** muss **„Read and write permissions"** aktiv sein,
   damit die Action das Release anlegen darf. (Der Workflow fordert
   `contents: write` ohnehin an.)

## Erstes Hochladen des Codes
```bash
cd logwatch-client
git init                     # falls noch nicht geschehen
git add -A
git commit -m "Initialer Commit: LogWatch"
git branch -M main
git remote add origin https://github.com/USERNAME/Logwatch.git
git push -u origin main
```
> `USERNAME` durch deinen GitHub-Benutzer/Org ersetzen. Passe die Links in
> `CHANGELOG.md` entsprechend an.

## Neues Release erstellen
1. **Version festlegen:** Datei `VERSION` aktualisieren (z.B. `0.2.0`) und im
   `CHANGELOG.md` einen neuen Abschnitt für die Version ergänzen.
2. **Commit & Push:**
   ```bash
   git add VERSION CHANGELOG.md
   git commit -m "Release vorbereiten: v0.2.0"
   git push
   ```
3. **Tag setzen und pushen** (löst den Build + Release automatisch aus):
   ```bash
   git tag v0.2.0
   git push origin v0.2.0
   ```
4. GitHub Actions baut nun die EXE (Reiter **Actions** im Repo) und legt unter
   **Releases** ein neues Release `v0.2.0` mit `LogWatch.exe` an.

> Der Tag **muss** mit `v` beginnen (z.B. `v0.2.0`), damit der Release-Workflow
> greift.

## Build manuell testen (ohne Release)
Im Reiter **Actions → Release (Windows-Build) → Run workflow** lässt sich der
Build manuell starten. Die EXE liegt danach als **Artefakt** am Workflow-Lauf
(kein Release).

## Lokaler Build auf Windows (ohne GitHub)
Siehe `README.md`, Abschnitt „Build-Anleitung für Windows", bzw.:
```bat
build_windows.bat
```
Ergebnis: `dist\LogWatch.exe`.
