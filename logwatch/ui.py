"""PySide6-GUI für LogWatch (Deutsch), inkl. System-Tray.

Warum PySide6: bringt mit ``QSystemTrayIcon`` nativen Tray-Support mit, ist gut
mit PyInstaller paketierbar und benötigt keine zusätzlichen Tray-Bibliotheken.
"""
from __future__ import annotations

import os
import sys

from PySide6.QtCore import Qt, QTimer, QThread, Signal
from PySide6.QtGui import QAction, QIcon, QPixmap, QPainter, QColor, QBrush
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QSpinBox, QRadioButton, QButtonGroup,
    QPlainTextEdit, QCheckBox, QComboBox, QFileDialog, QGroupBox, QTableWidget,
    QTableWidgetItem, QMessageBox, QInputDialog, QSystemTrayIcon, QMenu,
    QProgressDialog,
)

from . import autostart, config as cfgmod, crypto, updater
from .app_logging import setup_logging, get_logger
from .config import Config, Recipient, SMTPSettings, DEFAULT_KEYWORDS
from .mailer import build_test_message, send_message
from .worker import MonitorWorker


def make_icon(color: str = "#2d7d46") -> QIcon:
    """Erzeugt ein einfaches Tray-/Fenster-Icon ohne externe Datei."""
    pix = QPixmap(64, 64)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QBrush(QColor(color)))
    p.setPen(Qt.NoPen)
    p.drawEllipse(6, 6, 52, 52)
    p.setPen(QColor("white"))
    f = p.font()
    f.setBold(True)
    f.setPointSize(26)
    p.setFont(f)
    p.drawText(pix.rect(), Qt.AlignCenter, "LW")
    p.end()
    return QIcon(pix)


class UpdateCheckWorker(QThread):
    """Prüft im Hintergrund auf Updates (blockiert die UI nicht)."""
    finished_check = Signal(object)  # updater.UpdateCheckResult

    def __init__(self, local_version: str, token: str | None):
        super().__init__()
        self._local_version = local_version
        self._token = token or None

    def run(self) -> None:
        try:
            result = updater.check_for_update(self._local_version, token=self._token)
        except Exception as exc:  # noqa: BLE001 - Prüfung darf nie crashen
            result = updater.UpdateCheckResult(
                ok=False, local_version=self._local_version,
                error=f"Unerwarteter Fehler bei der Update-Prüfung: {exc}")
        self.finished_check.emit(result)


class UpdateDownloadWorker(QThread):
    """Lädt die neue EXE im Hintergrund herunter und meldet den Fortschritt."""
    progress = Signal(int, int)       # (gelesen, gesamt)
    finished_dl = Signal(object)      # str (Pfad) bei Erfolg, sonst Exception/str

    def __init__(self, release, token: str | None):
        super().__init__()
        self._release = release
        self._token = token or None

    def run(self) -> None:
        try:
            path = updater.download_update(
                self._release, token=self._token,
                progress_callback=lambda r, t: self.progress.emit(int(r), int(t)))
            self.finished_dl.emit(path)
        except Exception as exc:  # noqa: BLE001
            self.finished_dl.emit(exc)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LogWatch – Logüberwachung")
        self.setWindowIcon(make_icon())
        self.resize(760, 820)

        setup_logging()
        self.log = get_logger()
        self.master_password: str | None = None
        self.worker: MonitorWorker | None = None
        self._allow_close = False

        # Update-Hintergrund-Worker (Referenzen halten, damit sie nicht wegräumt werden)
        self._update_check_worker: UpdateCheckWorker | None = None
        self._update_dl_worker: UpdateDownloadWorker | None = None
        self._update_progress: QProgressDialog | None = None

        self.config = self._load_config_with_prompt()

        self._build_ui()
        self._config_to_ui(self.config)
        self._build_tray()
        self.append_status("LogWatch gestartet. Konfiguration geladen.")

        # Automatische Update-Prüfung beim Start (nicht blockierend, Fehler werden
        # nur protokolliert). Leicht verzögert, damit die UI zuerst erscheint.
        if self.config.update_check_on_start:
            QTimer.singleShot(1500, lambda: self._start_update_check(manual=False))

    # ------------------------------------------------------------------ laden
    def _load_config_with_prompt(self) -> Config:
        path = cfgmod.get_config_path()
        if not os.path.isfile(path):
            return Config()
        protected = cfgmod.config_file_is_password_protected(path)
        if not protected:
            try:
                return cfgmod.load_config(path)
            except crypto.DecryptionError:
                QMessageBox.warning(self, "LogWatch",
                                    "Konfiguration konnte nicht gelesen werden. Es werden Standardwerte verwendet.")
                return Config()
        # Passwortgeschützt -> abfragen
        while True:
            pw, ok = QInputDialog.getText(self, "Master-Passwort",
                                          "Die Konfiguration ist verschlüsselt. Bitte Master-Passwort eingeben:",
                                          QLineEdit.Password)
            if not ok:
                return Config()
            try:
                c = cfgmod.load_config(path, master_password=pw)
                self.master_password = pw
                return c
            except crypto.DecryptionError:
                QMessageBox.warning(self, "LogWatch", "Falsches Passwort. Bitte erneut versuchen.")

    # -------------------------------------------------------------------- UI
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        # --- Logdatei & Intervall ---
        g_log = QGroupBox("Überwachung")
        gl = QGridLayout(g_log)
        self.ed_logpath = QLineEdit()
        btn_browse = QPushButton("Durchsuchen…")
        btn_browse.clicked.connect(self._browse_log)
        gl.addWidget(QLabel("Logdatei:"), 0, 0)
        gl.addWidget(self.ed_logpath, 0, 1)
        gl.addWidget(btn_browse, 0, 2)
        self.sp_interval = QSpinBox()
        self.sp_interval.setRange(1, 86400)
        self.sp_interval.setSuffix(" s")
        gl.addWidget(QLabel("Prüf-Intervall:"), 1, 0)
        gl.addWidget(self.sp_interval, 1, 1)
        self.sp_cooldown = QSpinBox()
        self.sp_cooldown.setRange(0, 86400)
        self.sp_cooldown.setSuffix(" s")
        gl.addWidget(QLabel("Cooldown (Anti-Spam):"), 2, 0)
        gl.addWidget(self.sp_cooldown, 2, 1)
        gl.addWidget(QLabel("Nach einer Mail werden Fehler gesammelt und erst nach Ablauf gesendet."), 2, 2)
        root.addWidget(g_log)

        # --- Maschinen-Identität ---
        g_id = QGroupBox("Maschinen-Identität (für E-Mail & Dashboard)")
        il = QGridLayout(g_id)
        self.ed_machine_id = QLineEdit()
        self.ed_company = QLineEdit()
        il.addWidget(QLabel("Maschinen-ID:"), 0, 0)
        il.addWidget(self.ed_machine_id, 0, 1)
        il.addWidget(QLabel("(vom Betreiber vergeben, eindeutig)"), 0, 2)
        il.addWidget(QLabel("Firma/Kunde:"), 1, 0)
        il.addWidget(self.ed_company, 1, 1)
        root.addWidget(g_id)

        # --- Zentrales Dashboard (Upload) ---
        g_dash = QGroupBox("Zentrales Dashboard (optionaler Upload zusätzlich zur E-Mail)")
        dl = QGridLayout(g_dash)
        self.chk_upload = QCheckBox("Fehlerberichte an Dashboard senden")
        self.ed_dash_url = QLineEdit()
        self.ed_dash_url.setPlaceholderText("https://logwatch-xxxx.abacusai.cloud")
        self.ed_dash_token = QLineEdit()
        self.ed_dash_token.setEchoMode(QLineEdit.Password)
        dl.addWidget(self.chk_upload, 0, 0, 1, 2)
        dl.addWidget(QLabel("Dashboard-URL:"), 1, 0)
        dl.addWidget(self.ed_dash_url, 1, 1)
        dl.addWidget(QLabel("Upload-Token:"), 2, 0)
        dl.addWidget(self.ed_dash_token, 2, 1)
        root.addWidget(g_dash)

        # --- Fehlermodus ---
        g_mode = QGroupBox("Fehlererkennung")
        ml = QVBoxLayout(g_mode)
        self.rb_all = QRadioButton("Alle Fehler (generische Stichwörter)")
        self.rb_specific = QRadioButton("Nur bestimmte Fehler (eigene Zeilen/Muster)")
        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.rb_all)
        self.mode_group.addButton(self.rb_specific)
        ml.addWidget(self.rb_all)
        ml.addWidget(QLabel("Standard-Stichwörter (eine pro Zeile), case-insensitive:"))
        self.ed_all_kw = QPlainTextEdit()
        self.ed_all_kw.setFixedHeight(70)
        ml.addWidget(self.ed_all_kw)
        ml.addWidget(self.rb_specific)
        ml.addWidget(QLabel("Eigene Fehlerzeilen/Muster (eine pro Zeile). "
                            "Tipp: den stabilen Teil der Logzeile eintragen, nicht den Zeitstempel:"))
        self.ed_specific = QPlainTextEdit()
        self.ed_specific.setFixedHeight(90)
        ml.addWidget(self.ed_specific)
        root.addWidget(g_mode)

        # --- Empfänger ---
        g_rcpt = QGroupBox("E-Mail-Empfänger (max. 5) – Firma/Maschine erscheinen in Betreff & Text")
        rl = QVBoxLayout(g_rcpt)
        self.tbl = QTableWidget(Config.MAX_RECIPIENTS, 4)
        self.tbl.setHorizontalHeaderLabels(["E-Mail-Adresse", "Firma", "Maschine", "Aktiv"])
        self.tbl.horizontalHeader().setStretchLastSection(False)
        self.tbl.setColumnWidth(0, 240)
        self.tbl.setColumnWidth(1, 160)
        self.tbl.setColumnWidth(2, 160)
        for row in range(Config.MAX_RECIPIENTS):
            for col in range(3):
                self.tbl.setItem(row, col, QTableWidgetItem(""))
            chk = QCheckBox()
            chk.setChecked(True)
            w = QWidget()
            lay = QHBoxLayout(w)
            lay.addWidget(chk)
            lay.setAlignment(Qt.AlignCenter)
            lay.setContentsMargins(0, 0, 0, 0)
            self.tbl.setCellWidget(row, 3, w)
        self.tbl.setFixedHeight(200)
        rl.addWidget(self.tbl)
        root.addWidget(g_rcpt)

        # --- SMTP ---
        g_smtp = QGroupBox("SMTP-Einstellungen (Sende-Postfach)")
        sl = QGridLayout(g_smtp)
        self.ed_host = QLineEdit()
        self.sp_port = QSpinBox(); self.sp_port.setRange(1, 65535)
        self.ed_user = QLineEdit()
        self.ed_pass = QLineEdit(); self.ed_pass.setEchoMode(QLineEdit.Password)
        self.ed_from = QLineEdit()
        self.cmb_sec = QComboBox()
        self.cmb_sec.addItems(["STARTTLS (587)", "SSL/TLS (465)", "Keine (unverschlüsselt)"])
        sl.addWidget(QLabel("Host:"), 0, 0); sl.addWidget(self.ed_host, 0, 1)
        sl.addWidget(QLabel("Port:"), 0, 2); sl.addWidget(self.sp_port, 0, 3)
        sl.addWidget(QLabel("Benutzer:"), 1, 0); sl.addWidget(self.ed_user, 1, 1)
        sl.addWidget(QLabel("Passwort:"), 1, 2); sl.addWidget(self.ed_pass, 1, 3)
        sl.addWidget(QLabel("Absender:"), 2, 0); sl.addWidget(self.ed_from, 2, 1)
        sl.addWidget(QLabel("Sicherheit:"), 2, 2); sl.addWidget(self.cmb_sec, 2, 3)
        root.addWidget(g_smtp)

        # --- Optionen ---
        g_opt = QGroupBox("Optionen")
        ol = QHBoxLayout(g_opt)
        self.chk_autostart = QCheckBox("Mit Windows starten")
        self.btn_master = QPushButton("Master-Passwort setzen/ändern…")
        self.btn_master.clicked.connect(self._set_master_password)
        ol.addWidget(self.chk_autostart)
        ol.addWidget(self.btn_master)
        ol.addStretch(1)
        root.addWidget(g_opt)

        # --- Updates ---
        g_upd = QGroupBox("Updates")
        ul = QGridLayout(g_upd)
        self.chk_update_on_start = QCheckBox("Beim Start nach Updates suchen")
        self.ed_github_token = QLineEdit()
        self.ed_github_token.setEchoMode(QLineEdit.Password)  # maskiert wie Passwortfelder
        self.ed_github_token.setPlaceholderText("Nur für privates Repo nötig – optional")
        self.btn_check_update = QPushButton("Nach Updates suchen")
        self.btn_check_update.clicked.connect(lambda: self._start_update_check(manual=True))
        self.lbl_version = QLabel(f"Installierte Version: {updater.read_local_version()}")
        ul.addWidget(self.chk_update_on_start, 0, 0, 1, 2)
        ul.addWidget(QLabel("GitHub-Token (optional, für privates Repo):"), 1, 0)
        ul.addWidget(self.ed_github_token, 1, 1)
        ul.addWidget(self.lbl_version, 2, 0)
        ul.addWidget(self.btn_check_update, 2, 1)
        root.addWidget(g_upd)

        # --- Buttons ---
        btns = QHBoxLayout()
        self.btn_save = QPushButton("Speichern")
        self.btn_test = QPushButton("Test-E-Mail senden")
        self.btn_toggle = QPushButton("Überwachung starten")
        self.btn_export = QPushButton("Konfiguration exportieren…")
        self.btn_import = QPushButton("Konfiguration importieren…")
        self.btn_save.clicked.connect(self._save)
        self.btn_test.clicked.connect(self._send_test)
        self.btn_toggle.clicked.connect(self._toggle_monitor)
        self.btn_export.clicked.connect(self._export)
        self.btn_import.clicked.connect(self._import)
        for b in (self.btn_save, self.btn_test, self.btn_toggle, self.btn_export, self.btn_import):
            btns.addWidget(b)
        root.addLayout(btns)

        # --- Status ---
        g_stat = QGroupBox("Status / Ereignisse")
        stl = QVBoxLayout(g_stat)
        self.txt_status = QPlainTextEdit()
        self.txt_status.setReadOnly(True)
        stl.addWidget(self.txt_status)
        root.addWidget(g_stat)

    def _build_tray(self):
        self.tray = QSystemTrayIcon(make_icon(), self)
        self.tray.setToolTip("LogWatch")
        menu = QMenu()
        act_open = QAction("Öffnen", self)
        act_check = QAction("Jetzt prüfen", self)
        act_quit = QAction("Beenden", self)
        act_open.triggered.connect(self._restore_window)
        act_check.triggered.connect(self._check_now)
        act_quit.triggered.connect(self._quit_app)
        menu.addAction(act_open)
        menu.addAction(act_check)
        menu.addSeparator()
        menu.addAction(act_quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

    # --------------------------------------------------------------- mapping
    def _config_to_ui(self, c: Config):
        self.ed_logpath.setText(c.log_file_path)
        self.sp_interval.setValue(c.check_interval_seconds)
        self.sp_cooldown.setValue(c.cooldown_seconds)
        self.rb_all.setChecked(c.error_mode != "specific")
        self.rb_specific.setChecked(c.error_mode == "specific")
        self.ed_all_kw.setPlainText("\n".join(c.all_keywords or DEFAULT_KEYWORDS))
        self.ed_specific.setPlainText("\n".join(c.specific_keywords))
        for row in range(Config.MAX_RECIPIENTS):
            r = c.recipients[row] if row < len(c.recipients) else Recipient(active=False)
            self.tbl.item(row, 0).setText(r.email)
            self.tbl.item(row, 1).setText(r.company)
            self.tbl.item(row, 2).setText(r.machine)
            self._row_checkbox(row).setChecked(r.active)
        self.ed_host.setText(c.smtp.host)
        self.sp_port.setValue(c.smtp.port)
        self.ed_user.setText(c.smtp.username)
        self.ed_pass.setText(c.smtp.password)
        self.ed_from.setText(c.smtp.from_address)
        if c.smtp.use_ssl:
            self.cmb_sec.setCurrentIndex(1)
        elif c.smtp.use_tls:
            self.cmb_sec.setCurrentIndex(0)
        else:
            self.cmb_sec.setCurrentIndex(2)
        self.chk_autostart.setChecked(c.autostart)
        self.ed_machine_id.setText(c.machine_id)
        self.ed_company.setText(c.company)
        self.chk_upload.setChecked(c.dashboard.enabled)
        self.ed_dash_url.setText(c.dashboard.base_url)
        self.ed_dash_token.setText(c.dashboard.upload_token)
        self.chk_update_on_start.setChecked(c.update_check_on_start)
        self.ed_github_token.setText(c.github_pat)

    def _row_checkbox(self, row) -> QCheckBox:
        return self.tbl.cellWidget(row, 3).findChild(QCheckBox)

    def _ui_to_config(self) -> Config:
        c = self.config.copy()
        c.log_file_path = self.ed_logpath.text().strip()
        c.check_interval_seconds = self.sp_interval.value()
        c.cooldown_seconds = self.sp_cooldown.value()
        c.error_mode = "specific" if self.rb_specific.isChecked() else "all"
        c.all_keywords = [l.strip() for l in self.ed_all_kw.toPlainText().splitlines() if l.strip()] or list(DEFAULT_KEYWORDS)
        c.specific_keywords = [l.rstrip("\r\n") for l in self.ed_specific.toPlainText().splitlines() if l.strip()]
        recipients = []
        for row in range(Config.MAX_RECIPIENTS):
            email = self.tbl.item(row, 0).text().strip()
            company = self.tbl.item(row, 1).text().strip()
            machine = self.tbl.item(row, 2).text().strip()
            active = self._row_checkbox(row).isChecked()
            if email or company or machine:
                recipients.append(Recipient(email=email, company=company, machine=machine, active=active))
        c.recipients = recipients
        sec = self.cmb_sec.currentIndex()
        c.smtp = SMTPSettings(
            host=self.ed_host.text().strip(),
            port=self.sp_port.value(),
            username=self.ed_user.text().strip(),
            password=self.ed_pass.text(),
            use_tls=(sec == 0),
            use_ssl=(sec == 1),
            from_address=self.ed_from.text().strip(),
        )
        c.autostart = self.chk_autostart.isChecked()
        c.machine_id = self.ed_machine_id.text().strip()
        c.company = self.ed_company.text().strip()
        from .config import DashboardSettings
        c.dashboard = DashboardSettings(
            enabled=self.chk_upload.isChecked(),
            base_url=self.ed_dash_url.text().strip(),
            upload_token=self.ed_dash_token.text().strip(),
        )
        c.update_check_on_start = self.chk_update_on_start.isChecked()
        c.github_pat = self.ed_github_token.text().strip()
        return c

    # --------------------------------------------------------------- actions
    def _browse_log(self):
        path, _ = QFileDialog.getOpenFileName(self, "Logdatei wählen", "", "Logdateien (*.log *.txt);;Alle Dateien (*.*)")
        if path:
            self.ed_logpath.setText(path)

    def _save(self):
        self.config = self._ui_to_config()
        try:
            cfgmod.save_config(self.config, master_password=self.master_password)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "LogWatch", f"Speichern fehlgeschlagen: {exc}")
            return
        ok = autostart.apply(self.config.autostart)
        if not ok:
            self.append_status("Autostart konnte nicht gesetzt werden (fehlende Rechte?).")
        self.append_status("Konfiguration gespeichert (verschlüsselt).")
        QMessageBox.information(self, "LogWatch", "Konfiguration gespeichert.")

    def _send_test(self):
        c = self._ui_to_config()
        recipients = c.active_recipients()
        if not recipients:
            QMessageBox.warning(self, "LogWatch", "Keine aktiven Empfänger mit E-Mail-Adresse konfiguriert.")
            return
        try:
            msg = build_test_message(c, recipients)
            send_message(c.smtp, msg)
            self.append_status("Test-E-Mail erfolgreich versendet.")
            QMessageBox.information(self, "LogWatch", "Test-E-Mail wurde versendet.")
        except Exception as exc:  # noqa: BLE001
            self.append_status(f"Test-E-Mail fehlgeschlagen: {exc}")
            QMessageBox.critical(self, "LogWatch", f"Versand fehlgeschlagen:\n{exc}")

    def _toggle_monitor(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(3000)
            self.worker = None
            self.btn_toggle.setText("Überwachung starten")
            return
        self.config = self._ui_to_config()
        if not self.config.log_file_path or not os.path.isfile(self.config.log_file_path):
            QMessageBox.warning(self, "LogWatch", "Bitte zuerst eine gültige Logdatei wählen.")
            return
        self.worker = MonitorWorker(self.config)
        self.worker.log_message.connect(self.append_status)
        self.worker.status_changed.connect(self._on_status_changed)
        self.worker.start()
        self.btn_toggle.setText("Überwachung stoppen")

    def _on_status_changed(self, running: bool):
        self.btn_toggle.setText("Überwachung stoppen" if running else "Überwachung starten")

    def _check_now(self):
        if self.worker and self.worker.isRunning():
            self.worker.request_check_now()
            self.append_status("Manuelle Prüfung angefordert.")
        else:
            self.append_status("Überwachung läuft nicht – 'Überwachung starten' zuerst.")

    def _export(self):
        c = self._ui_to_config()
        path, _ = QFileDialog.getSaveFileName(self, "Konfiguration exportieren", "logwatch_profil.dat",
                                              "LogWatch-Profil (*.dat);;Alle Dateien (*.*)")
        if not path:
            return
        use_pw = QMessageBox.question(self, "Master-Passwort",
                                      "Export mit Master-Passwort schützen?\n(Empfohlen – dieselbe Passphrase wird zum Import benötigt.)")
        pw = None
        if use_pw == QMessageBox.Yes:
            pw, ok = QInputDialog.getText(self, "Master-Passwort", "Passwort für die Export-Datei:", QLineEdit.Password)
            if not ok or not pw:
                pw = None
        try:
            cfgmod.export_config(c, path, master_password=pw)
            self.append_status(f"Konfiguration exportiert: {path}")
            QMessageBox.information(self, "LogWatch", "Export erfolgreich. Diese Datei kannst du auf weiteren PCs importieren.")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "LogWatch", f"Export fehlgeschlagen: {exc}")

    def _import(self):
        path, _ = QFileDialog.getOpenFileName(self, "Konfiguration importieren", "",
                                              "LogWatch-Profil (*.dat);;Alle Dateien (*.*)")
        if not path:
            return
        pw = None
        try:
            with open(path, "rb") as f:
                protected = crypto.is_password_protected(f.read())
            if protected:
                pw, ok = QInputDialog.getText(self, "Master-Passwort", "Passwort der Import-Datei:", QLineEdit.Password)
                if not ok:
                    return
            c = cfgmod.import_config(path, master_password=pw)
            self.config = c
            self._config_to_ui(c)
            self.append_status(f"Konfiguration importiert: {path}")
            QMessageBox.information(self, "LogWatch", "Import erfolgreich. Bitte Firma/Maschine für diesen PC prüfen und anschließend 'Speichern'.")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "LogWatch", f"Import fehlgeschlagen: {exc}")

    def _set_master_password(self):
        pw, ok = QInputDialog.getText(self, "Master-Passwort",
                                      "Neues Master-Passwort (leer = kein Passwort, nur eingebetteter Schlüssel):",
                                      QLineEdit.Password)
        if not ok:
            return
        self.master_password = pw or None
        self.append_status("Master-Passwort gesetzt. Bitte 'Speichern', um es anzuwenden.")

    # --------------------------------------------------------------- updates
    def _start_update_check(self, manual: bool = False) -> None:
        """Startet die Update-Prüfung im Hintergrund (blockiert die UI nicht).

        ``manual=True``: vom Nutzer per Button ausgelöst → Ergebnis immer als Dialog.
        ``manual=False``: Auto-Check beim Start → nur bei verfügbarem Update ein
        dezenter Hinweis; Fehler werden still nur protokolliert.
        """
        if self._update_check_worker and self._update_check_worker.isRunning():
            if manual:
                self.append_status("Update-Prüfung läuft bereits …")
            return

        token = self.ed_github_token.text().strip() or None
        local_version = updater.read_local_version()
        if manual:
            self.btn_check_update.setEnabled(False)
            self.append_status("Suche nach Updates …")

        worker = UpdateCheckWorker(local_version, token)
        worker.finished_check.connect(lambda res: self._on_update_checked(res, manual))
        self._update_check_worker = worker
        worker.start()

    def _on_update_checked(self, result, manual: bool) -> None:
        if manual:
            self.btn_check_update.setEnabled(True)

        if not result.ok:
            # Fehler: im manuellen Fall anzeigen, beim Auto-Check nur loggen.
            self.append_status(f"Update-Prüfung fehlgeschlagen: {result.error}")
            if manual:
                QMessageBox.warning(self, "LogWatch", result.error)
            return

        if not result.update_available:
            self.append_status(f"Keine neuere Version verfügbar (installiert: {result.local_version}).")
            if manual:
                QMessageBox.information(
                    self, "LogWatch",
                    f"Du hast bereits die neueste Version ({result.local_version}).")
            return

        # Ein Update ist verfügbar.
        self.append_status(
            f"Update verfügbar: {result.remote_version} (installiert: {result.local_version}).")
        if not result.asset_available:
            msg = (f"Version {result.remote_version} ist verfügbar, enthält aber keine "
                   f"installierbare {updater.ASSET_NAME}. Bitte manuell von GitHub laden.")
            self.append_status(msg)
            if manual:
                QMessageBox.information(self, "LogWatch", msg)
            return

        self._prompt_update(result)

    def _prompt_update(self, result) -> None:
        notes = (result.release_notes or "").strip()
        if len(notes) > 1200:
            notes = notes[:1200] + "\n…"
        text = (f"Eine neue Version ist verfügbar.\n\n"
                f"Installiert: {result.local_version}\n"
                f"Neu: {result.remote_version}\n\n"
                f"Änderungen:\n{notes or '(keine Beschreibung)'}\n\n"
                f"Jetzt herunterladen und aktualisieren?")
        box = QMessageBox(self)
        box.setWindowTitle("LogWatch – Update verfügbar")
        box.setIcon(QMessageBox.Question)
        box.setText(text)
        btn_now = box.addButton("Jetzt aktualisieren", QMessageBox.AcceptRole)
        box.addButton("Später", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is btn_now:
            self._start_update_download(result.release)

    def _start_update_download(self, release) -> None:
        if not updater.is_windows():
            QMessageBox.information(
                self, "LogWatch",
                "Die automatische Installation ist nur unter Windows möglich. "
                "Bitte die neue LogWatch.exe manuell von der GitHub-Releases-Seite laden.")
            return
        token = self.ed_github_token.text().strip() or None

        self._update_progress = QProgressDialog("Lade Update herunter …", "Abbrechen", 0, 100, self)
        self._update_progress.setWindowTitle("LogWatch – Update")
        self._update_progress.setWindowModality(Qt.WindowModal)
        self._update_progress.setAutoClose(False)
        self._update_progress.setValue(0)

        worker = UpdateDownloadWorker(release, token)
        worker.progress.connect(self._on_update_progress)
        worker.finished_dl.connect(self._on_update_downloaded)
        self._update_dl_worker = worker
        self._update_progress.canceled.connect(self._cancel_update_download)
        worker.start()

    def _on_update_progress(self, read_bytes: int, total: int) -> None:
        if not self._update_progress:
            return
        if total > 0:
            self._update_progress.setValue(int(read_bytes * 100 / total))
        else:
            # Größe unbekannt → nur MB anzeigen
            self._update_progress.setLabelText(f"Lade Update herunter … ({read_bytes // (1024*1024)} MB)")

    def _cancel_update_download(self) -> None:
        # Hinweis: Der Download läuft robust zu Ende; wir brechen hier nur die Anzeige ab.
        self.append_status("Update-Download abgebrochen.")

    def _on_update_downloaded(self, result) -> None:
        if self._update_progress:
            self._update_progress.close()
            self._update_progress = None

        if isinstance(result, Exception):
            msg = str(result) or "Download fehlgeschlagen."
            self.append_status(f"Update-Download fehlgeschlagen: {msg}")
            QMessageBox.critical(self, "LogWatch", f"Update fehlgeschlagen:\n{msg}")
            return

        new_exe = result
        try:
            updater.install_and_restart(new_exe)
        except Exception as exc:  # noqa: BLE001
            self.append_status(f"Update-Installation fehlgeschlagen: {exc}")
            QMessageBox.critical(self, "LogWatch", f"Update-Installation fehlgeschlagen:\n{exc}")
            return

        self.append_status("Update wird installiert. Die Anwendung wird jetzt neu gestartet.")
        QMessageBox.information(
            self, "LogWatch",
            "Das Update wird installiert und LogWatch neu gestartet.")
        self._quit_app()

    # ----------------------------------------------------------------- tray
    def _tray_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger or reason == QSystemTrayIcon.DoubleClick:
            self._restore_window()

    def _restore_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _quit_app(self):
        self._allow_close = True
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(3000)
        self.tray.hide()
        QApplication.quit()

    def closeEvent(self, event):
        # Schließen minimiert in den Tray statt zu beenden.
        if self._allow_close:
            event.accept()
            return
        event.ignore()
        self.hide()
        self.tray.showMessage("LogWatch", "Läuft weiter im Hintergrund. Rechtsklick auf das Tray-Icon zum Beenden.",
                              QSystemTrayIcon.Information, 3000)

    def append_status(self, msg: str):
        from datetime import datetime
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.txt_status.appendPlainText(f"{ts}  {msg}")
        self.log.info(msg)


def run():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # wegen Tray-Betrieb
    win = MainWindow()
    # Beim Autostart ggf. minimiert starten
    if "--minimized" in sys.argv:
        win.hide()
    else:
        win.show()
    sys.exit(app.exec())
