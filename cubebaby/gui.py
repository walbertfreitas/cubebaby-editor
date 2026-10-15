"""Interface do editor nativo do Cube Baby AC."""
from __future__ import annotations

import os
import re
import shutil
import sys
import time
from functools import partial

from .qt import QtCore, QtGui, QtWidgets

QSettings, Qt, QTimer = QtCore.QSettings, QtCore.Qt, QtCore.QTimer
QColor, QIcon, QPainter, QPainterPath, QPen = (QtGui.QColor, QtGui.QIcon, QtGui.QPainter,
                                               QtGui.QPainterPath, QtGui.QPen)
W = QtWidgets
(QApplication, QCheckBox, QComboBox, QDial, QFileDialog, QFrame, QGridLayout, QGroupBox, QHBoxLayout,
 QLabel, QMainWindow, QMessageBox, QProgressBar, QPushButton, QSlider, QSpinBox, QVBoxLayout,
 QWidget) = (W.QApplication, W.QCheckBox, W.QComboBox, W.QDial, W.QFileDialog, W.QFrame, W.QGridLayout,
             W.QGroupBox, W.QHBoxLayout, W.QLabel, W.QMainWindow, W.QMessageBox, W.QProgressBar,
             W.QPushButton, W.QSlider, W.QSpinBox, W.QVBoxLayout, W.QWidget)
YES = QMessageBox.StandardButton.Yes

from . import ir
from .device import CubeBaby
from .model import PARAMS, SWITCHES, CubeBabyAC, Presets
from .worker import DeviceWorker

ACCENT = "#33EAB8"
APP_NAME = "Cube Baby Editor"
DATA_DIR = os.path.join(os.path.expanduser("~"), ".local", "share", "cubebaby-editor")
BACKUP_DIR = os.path.join(DATA_DIR, "backups")
FACTORY_IR_FILE = os.path.join(DATA_DIR, "factory", "BCIF.bin")
DEFAULT_CUBESUITE = os.path.expanduser("~")

STYLE = f"""
QWidget {{ background: #0b0f0e; color: #d6f5ec; font-size: 10pt; }}
QGroupBox {{ border: 1px solid {ACCENT}; border-radius: 10px; margin-top: 14px; padding: 10px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 4px; color: {ACCENT}; }}
QPushButton {{ border: 1px solid {ACCENT}; border-radius: 8px; padding: 6px 12px; background: #10231e; }}
QPushButton:hover {{ background: #173a31; }}
QPushButton:disabled {{ color: #5d7a72; border-color: #2c4a42; }}
QPushButton:checked {{ background: {ACCENT}; color: #0b0f0e; }}
QSlider::groove:horizontal {{ height: 4px; background: #2a3a36; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: #e8f5f1; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {ACCENT}; width: 14px; margin: -6px 0; border-radius: 7px; }}
QSlider:disabled::handle:horizontal {{ background: #3b524c; }}
QSpinBox, QComboBox {{ border: 1px solid {ACCENT}; border-radius: 4px; padding: 2px 4px; background: #0f1a17; }}
QProgressBar {{ border: 1px solid {ACCENT}; border-radius: 4px; text-align: center; }}
QProgressBar::chunk {{ background: {ACCENT}; }}
QLabel#hint {{ color: #8fb5aa; }}
"""


class IrPreview(QFrame):
    """Desenha a forma de onda das 512 amostras do IR."""

    def __init__(self):
        super().__init__()
        self.samples: list[float] = []
        self.setMinimumSize(260, 140)
        self.setStyleSheet(f"border: 1px solid {ACCENT}; border-radius: 10px;")

    def set_samples(self, samples):
        self.samples = list(samples)
        self.update()

    def paintEvent(self, ev):
        super().paintEvent(ev)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        mid = h / 2
        p.setPen(QPen(QColor("#2a3a36"), 1))
        p.drawLine(8, int(mid), w - 8, int(mid))
        if not self.samples:
            p.setPen(QColor("#5d7a72"))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Nenhum IR carregado")
            return
        peak = max(1e-9, max(abs(s) for s in self.samples))
        path = QPainterPath()
        n = len(self.samples)
        for i, s in enumerate(self.samples):
            x = 8 + (w - 16) * i / (n - 1)
            y = mid - (h / 2 - 10) * s / peak
            path.moveTo(x, y) if i == 0 else path.lineTo(x, y)
        p.setPen(QPen(QColor(ACCENT), 1.4))
        p.drawPath(path)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.settings = QSettings("cubebaby-editor", "cubebaby-editor")
        self.worker = DeviceWorker(self)
        self.worker.busy.connect(self._on_busy)
        self.worker.progress.connect(self._on_progress)
        self.worker.start()

        self.ac: CubeBabyAC | None = None
        self.presets: Presets | None = None
        self.dirty = False
        self.loading = False
        self.ir_samples: list[float] | None = None
        self.wav = None  # (nome, amostras do 1º canal, WavInfo) do último WAV aberto
        self.pending_live: dict[tuple[int, int], int] = {}

        self._build_ui()
        self._set_connected(False)

        self.live_timer = QTimer(self, singleShot=True, interval=40, timeout=self._flush_live)
        self.reconnect_timer = QTimer(self, interval=3000, timeout=self._connect)
        self._connect()

    # ----- interface -------------------------------------------------------

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        cols = QHBoxLayout()
        outer.addLayout(cols)
        cols.addLayout(self._build_ir_column(), 1)
        cols.addWidget(self._build_preset_group(), 1)

        bottom = QHBoxLayout()
        self.status = QLabel("Procurando o pedal…")
        self.progress = QProgressBar(maximumWidth=220, visible=False)
        bottom.addWidget(self.status, 1)
        bottom.addWidget(self.progress)
        outer.addLayout(bottom)

    def _build_ir_column(self):
        col = QVBoxLayout()
        box = QGroupBox("Importar IR")
        g = QGridLayout(box)
        self.btn_open = QPushButton("Abrir arquivo WAV…", clicked=self._open_wav)
        self.ir_info = QLabel("", objectName="hint", wordWrap=True)
        self.dial = QDial(minimum=0, maximum=100, value=50, notchesVisible=True)
        self.dial.setFixedSize(80, 80)
        self.dial_label = QLabel("Distance: 50%")
        self.dial.valueChanged.connect(lambda v: self.dial_label.setText(f"Distance: {v}%"))
        self.slot_combo = QComboBox()
        self.slot_combo.addItems([str(i) for i in range(1, ir.SLOT_COUNT + 1)])
        self.btn_import = QPushButton("Gravar IR no pedal", clicked=self._import_ir, enabled=False)
        self.preview = IrPreview()

        self.chk_48k = QCheckBox("Converter para 48 kHz", checked=self.settings.value("to_48k", True, type=bool))
        self.chk_minphase = QCheckBox("Otimizar para 512 amostras (fase mínima)",
                                      checked=self.settings.value("min_phase", True, type=bool))
        self.chk_minphase.setToolTip("Concentra a energia do IR no início, para que o corte em 512 amostras "
                                     "(limite do pedal) preserve melhor o timbre, sobretudo os graves.")
        for chk in (self.chk_48k, self.chk_minphase):
            chk.toggled.connect(self._refresh_ir)

        g.addWidget(self.btn_open, 0, 0, 1, 2)
        g.addWidget(self.ir_info, 1, 0, 1, 2)
        g.addWidget(self.chk_48k, 2, 0, 1, 2)
        g.addWidget(self.chk_minphase, 3, 0, 1, 2)
        g.addWidget(self.dial_label, 4, 0)
        g.addWidget(self.dial, 4, 1, Qt.AlignmentFlag.AlignLeft)
        g.addWidget(QLabel("Gravar no slot:"), 5, 0)
        g.addWidget(self.slot_combo, 5, 1)
        g.addWidget(self.btn_import, 6, 0, 1, 2)
        g.addWidget(self.preview, 0, 2, 7, 1)
        col.addWidget(box)

        tools = QGroupBox("Ferramentas")
        t = QGridLayout(tools)
        self.btn_backup = QPushButton("Fazer backup dos IRs…", clicked=self._backup_irs)
        self.btn_restore = QPushButton("Restaurar backup de IRs…", clicked=self._restore_irs)
        self.btn_factory_ir = QPushButton("IRs de fábrica", clicked=self._factory_ir)
        self.btn_factory_reset = QPushButton("Presets de fábrica", clicked=self._factory_reset)
        self.chk_loopback = QCheckBox("USB Loopback")
        self.chk_loopback.toggled.connect(self._on_loopback)
        t.addWidget(self.btn_backup, 0, 0)
        t.addWidget(self.btn_restore, 0, 1)
        t.addWidget(self.btn_factory_ir, 1, 0)
        t.addWidget(self.btn_factory_reset, 1, 1)
        t.addWidget(self.chk_loopback, 2, 0, 1, 2)
        col.addWidget(tools)
        col.addStretch(1)
        self.device_widgets = [self.btn_backup, self.btn_restore, self.btn_factory_ir,
                               self.btn_factory_reset, self.chk_loopback]
        return col

    def _build_preset_group(self):
        box = QGroupBox("Preset")
        v = QVBoxLayout(box)
        top = QHBoxLayout()
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(["A", "B", "C"])
        self.preset_combo.currentIndexChanged.connect(self._show_preset)
        top.addWidget(QLabel("Editar preset:"))
        top.addWidget(self.preset_combo)
        top.addStretch(1)
        v.addLayout(top)

        self.sliders: dict[str, tuple[QSlider, QSpinBox, int]] = {}
        self.switch_buttons: dict[int, QPushButton] = {}
        switch_before = {params[0]: (name, off) for name, off, params in SWITCHES}
        grid = QGridLayout()
        row = 0
        for name, offset, maximum in PARAMS:
            if name in switch_before:
                sname, soff = switch_before[name]
                btn = QPushButton(f"{sname}: ligado", checkable=True)
                btn.toggled.connect(partial(self._on_switch, soff, sname))
                self.switch_buttons[soff] = btn
                grid.addWidget(btn, row, 0, 1, 3)
                row += 1
            label = QLabel(name)
            slider = QSlider(Qt.Orientation.Horizontal, minimum=0, maximum=maximum)
            spin = QSpinBox(minimum=0, maximum=maximum)
            slider.valueChanged.connect(spin.setValue)
            spin.valueChanged.connect(slider.setValue)
            spin.valueChanged.connect(partial(self._on_param, offset))
            grid.addWidget(label, row, 0)
            grid.addWidget(slider, row, 1)
            grid.addWidget(spin, row, 2)
            self.sliders[name] = (slider, spin, offset)
            row += 1
        v.addLayout(grid)
        self.btn_save = QPushButton("Salvar presets no pedal", clicked=self._save_presets)
        v.addWidget(self.btn_save)
        self.preset_box = box
        return box

    # ----- conexão ---------------------------------------------------------

    def _connect(self):
        def job():
            dev = CubeBaby()
            try:
                ac = CubeBabyAC(dev)
                return ac, ac.read_presets(), ac.get_loopback()
            except Exception:
                dev.close()
                raise
        self.worker.submit(job, self._on_connected, self._on_connect_failed)

    def _on_connected(self, res):
        self.ac, self.presets, loopback = res
        self.reconnect_timer.stop()
        self._set_connected(True)
        self.loading = True
        self.chk_loopback.setChecked(loopback)
        self.loading = False
        self._show_preset()
        self._msg(f"Conectado: Cube Baby AC (chip 0x{self.ac.dev.chip_id:04X}).")
        if not self.settings.value("first_backup_done", False, type=bool):
            self._first_backup()

    def _first_backup(self):
        """Uma única vez: guarda os IRs e presets que vieram no pedal (para quem não mexeu, são os de fábrica)."""
        ac, presets = self.ac, bytes(self.presets.raw)

        def job():
            irs = ac.read_ir_area(self.worker.report_progress)
            stamp = time.strftime("%Y%m%d-%H%M%S")
            os.makedirs(BACKUP_DIR, exist_ok=True)
            ir_path = os.path.join(BACKUP_DIR, f"irs-primeira-conexao-{stamp}.bin")
            with open(ir_path, "wb") as f:
                f.write(irs)
            with open(os.path.join(BACKUP_DIR, f"presets-primeira-conexao-{stamp}.bin"), "wb") as f:
                f.write(presets)
            return ir_path

        def done(path):
            self.settings.setValue("first_backup_done", True)
            self._msg(f"Backup inicial do pedal salvo em {path}")
            QMessageBox.information(
                self, APP_NAME,
                "Primeira conexão: os 8 IRs e os 3 presets que estavam no pedal foram salvos em\n"
                f"{BACKUP_DIR}\n\nPara voltar a eles, use \"Restaurar backup de IRs…\".")
        self.worker.submit(job, done, self._error, label="Primeira conexão: fazendo backup dos IRs do pedal…")

    def _on_connect_failed(self, msg):
        self._set_connected(False)
        self._msg(f"{msg} Tentando de novo…")
        if not self.reconnect_timer.isActive():
            self.reconnect_timer.start()

    def _lost_connection(self, msg):
        if self.ac:
            try:
                self.ac.dev.close()
            except Exception:  # noqa: BLE001
                pass
        self.ac = None
        self._on_connect_failed(f"Conexão perdida: {msg}.")

    def _set_connected(self, ok: bool):
        self.preset_box.setEnabled(ok)
        for w in self.device_widgets:
            w.setEnabled(ok)
        self.btn_import.setEnabled(ok and self.ir_samples is not None)

    # ----- presets -----------------------------------------------------------

    def _slot(self) -> int:
        return self.preset_combo.currentIndex()

    def _show_preset(self):
        if not self.presets:
            return
        self.loading = True
        slot = self._slot()
        for _name, (_slider, spin, offset) in self.sliders.items():
            spin.setValue(self.presets.get(slot, offset))
        for off, btn in self.switch_buttons.items():
            btn.setChecked(bool(self.presets.get(slot, off)))
            self._apply_switch_state(off, btn)
        self.loading = False

    def _apply_switch_state(self, offset, btn):
        sname, _off, params = next(s for s in SWITCHES if s[1] == offset)
        on = btn.isChecked()
        btn.setText(f"{sname}: {'ligado' if on else 'desligado'}")
        for p in params:
            slider, spin, _ = self.sliders[p]
            slider.setEnabled(on)
            spin.setEnabled(on)

    def _on_param(self, offset, value):
        if self.loading or not self.presets:
            return
        self._queue_live(offset, value)

    def _on_switch(self, offset, _name, checked):
        self._apply_switch_state(offset, self.switch_buttons[offset])
        if self.loading or not self.presets:
            return
        self._queue_live(offset, 1 if checked else 0)

    def _queue_live(self, offset, value):
        slot = self._slot()
        self.presets.set(slot, offset, value)
        self.pending_live[(slot, offset)] = value
        self._set_dirty(True)
        self.live_timer.start()

    def _flush_live(self):
        if not self.ac or not self.pending_live:
            return
        items, self.pending_live = list(self.pending_live.items()), {}
        ac = self.ac
        self.worker.submit(lambda: [ac.set_live(s, o, v) for (s, o), v in items],
                           on_error=self._lost_connection)

    def _set_dirty(self, dirty):
        self.dirty = dirty
        self.btn_save.setText("Salvar presets no pedal" + (" *" if dirty else ""))

    def _save_presets(self):
        ac, presets = self.ac, Presets(bytearray(self.presets.raw))
        self.worker.submit(lambda: ac.save_presets(presets),
                           lambda _r: (self._set_dirty(False), self._msg("Presets salvos e conferidos no pedal.")),
                           self._error, label="Salvando presets…")

    def _factory_reset(self):
        if not self._confirm("Presets de fábrica",
                             "Os presets A, B e C do pedal serão substituídos pelos valores de fábrica.\n"
                             "Os IRs não são alterados. Continuar?"):
            return
        ac = self.ac

        def done(presets):
            self.presets = presets
            self._set_dirty(False)
            self._show_preset()
            self._msg("Presets de fábrica restaurados.")
        self.worker.submit(ac.factory_reset, done, self._error, label="Restaurando presets de fábrica…")

    def _on_loopback(self, on):
        if self.loading or not self.ac:
            return
        ac = self.ac
        self.worker.submit(lambda: ac.set_loopback(on),
                           lambda _r: self._msg(f"USB Loopback {'ligado' if on else 'desligado'}."),
                           self._error)

    # ----- IRs -----------------------------------------------------------------

    def _open_wav(self):
        path, _ = QFileDialog.getOpenFileName(self, "Abrir IR (WAV)", self.settings.value("last_dir", ""),
                                              "Arquivos WAV (*.wav)")
        if not path:
            return
        self.settings.setValue("last_dir", os.path.dirname(path))
        try:
            samples, info = ir.read_wav(path)
        except (ir.WavError, OSError, ValueError) as e:
            self._error(str(e))
            return
        self.wav = (os.path.basename(path), samples, info)
        self._refresh_ir()
        self.btn_import.setEnabled(self.ac is not None)

    def _refresh_ir(self):
        self.settings.setValue("to_48k", self.chk_48k.isChecked())
        self.settings.setValue("min_phase", self.chk_minphase.isChecked())
        if not getattr(self, "wav", None):
            return
        name, samples, info = self.wav
        prepared = ir.prepare(samples, info.sample_rate, self.chk_48k.isChecked(), self.chk_minphase.isChecked())
        self.ir_samples = prepared.samples
        self.preview.set_samples(prepared.samples)
        kind = "float" if info.fmt == 3 else "PCM"
        lines = [name, f"{info.channels} canal(is), {info.sample_rate} Hz, {info.bits} bits {kind}, "
                       f"{info.frames} amostras"]
        if info.sample_rate != ir.DEVICE_RATE:
            lines.append(f"Convertido de {info.sample_rate} para 48000 Hz." if prepared.resampled else
                         f"⚠ Sem conversão: o pedal toca a 48000 Hz, o timbre fica alterado.")
        lines.append(f"O pedal guarda {ir.IR_SAMPLES / 48:.1f} ms de {prepared.length_ms:.1f} ms; "
                     f"{100 * prepared.energy_kept:.1f}% da energia do IR coube.")
        self.ir_info.setText("\n".join(lines))

    def _import_ir(self):
        slot = self.slot_combo.currentIndex()
        if not self._confirm("Gravar IR", f"O IR atual do slot {slot + 1} será substituído.\n"
                                          "Uma cópia de segurança dele será salva antes. Continuar?"):
            return
        record = ir.build_record(self.ir_samples, self.dial.value())
        ac = self.ac

        def job():
            old = ac.dev.read(0, ac.ir_base + slot * ir.SLOT_SIZE, ir.SLOT_SIZE)
            backup = self._save_backup(old, f"slot{slot + 1}")
            ac.write_ir_slot(slot, record)
            return backup
        self.worker.submit(job, lambda b: self._msg(f"IR gravado no slot {slot + 1}. Backup do anterior: {b}"),
                           self._error, label=f"Gravando IR no slot {slot + 1}…")

    def _backup_irs(self):
        default = os.path.join(BACKUP_DIR, time.strftime("irs-%Y%m%d-%H%M%S.bin"))
        os.makedirs(BACKUP_DIR, exist_ok=True)
        path, _ = QFileDialog.getSaveFileName(self, "Salvar backup dos IRs", default, "Backup de IRs (*.bin)")
        if not path:
            return
        ac = self.ac

        def job():
            data = ac.read_ir_area(self.worker.report_progress)
            with open(path, "wb") as f:
                f.write(data)
            return path
        self.worker.submit(job, lambda p: self._msg(f"Backup salvo em {p}"), self._error,
                           label="Lendo os 8 IRs do pedal…")

    def _restore_irs(self):
        path, _ = QFileDialog.getOpenFileName(self, "Restaurar backup de IRs", BACKUP_DIR, "Backup de IRs (*.bin)")
        if not path:
            return
        if os.path.getsize(path) == ir.SLOT_SIZE:
            self._restore_slot(path)
        else:
            self._write_ir_image(path, "Restaurar backup",
                                 f"Os 8 IRs do pedal serão substituídos pelo conteúdo de\n{path}\n\nContinuar?")

    def _restore_slot(self, path):
        """Backup de um slot só (criado automaticamente antes de gravar um IR)."""
        with open(path, "rb") as f:
            data = f.read()
        match = re.search(r"slot(\d)", os.path.basename(path))
        slot = int(match.group(1)) - 1 if match else self.slot_combo.currentIndex()
        if not 0 <= slot < ir.SLOT_COUNT:
            self._error("Não foi possível identificar o slot deste backup.")
            return
        where = "identificado pelo nome do arquivo" if match else "escolhido em 'Gravar no slot'"
        if not self._confirm("Restaurar slot", f"Este é o backup de um único IR.\nEle será gravado no slot "
                                               f"{slot + 1} ({where}).\n\nContinuar?"):
            return
        ac = self.ac

        def job():
            old = ac.dev.read(0, ac.ir_base + slot * ir.SLOT_SIZE, ir.SLOT_SIZE)
            backup = self._save_backup(old, f"slot{slot + 1}")
            ac.write_ir_slot(slot, data)
            return backup
        self.worker.submit(job, lambda b: self._msg(f"Slot {slot + 1} restaurado. Backup do anterior: {b}"),
                           self._error, label=f"Restaurando o slot {slot + 1}…")

    def _factory_ir(self):
        path = FACTORY_IR_FILE
        if not os.path.exists(path):
            folder = self.settings.value("cubesuite_dir", DEFAULT_CUBESUITE)
            found = os.path.join(folder, "bin", "BCIF.bin")
            if not os.path.exists(found):
                found, _ = QFileDialog.getOpenFileName(self, "Localize o BCIF.bin (pasta bin do CubeSuite)",
                                                       folder, "BCIF.bin (BCIF.bin)")
                if not found:
                    return
            if os.path.getsize(found) != ir.SLOT_COUNT * ir.SLOT_SIZE:
                self._error("Este BCIF.bin tem tamanho inesperado; o certo é 32768 bytes.")
                return
            # Guarda uma cópia na pasta do app: depois disso a pasta do CubeSuite não é mais necessária.
            os.makedirs(os.path.dirname(FACTORY_IR_FILE), exist_ok=True)
            shutil.copyfile(found, FACTORY_IR_FILE)
            self._msg(f"IRs de fábrica copiados para {FACTORY_IR_FILE}")
        self._write_ir_image(path, "IRs de fábrica",
                             "Os 8 IRs do pedal serão substituídos pelos IRs de fábrica.\n"
                             "IRs personalizados serão perdidos, mas um backup completo é feito antes.\n\nContinuar?")

    def _write_ir_image(self, path, title, question):
        try:
            with open(path, "rb") as f:
                image = f.read()
        except OSError as e:
            self._error(str(e))
            return
        if len(image) != ir.SLOT_COUNT * ir.SLOT_SIZE:
            self._error(f"Arquivo com tamanho inesperado ({len(image)} bytes). Um backup completo tem "
                        f"32768 bytes (8 IRs) e o de um slot, 4096.")
            return
        if not self._confirm(title, question):
            return
        ac = self.ac

        def job():
            backup = self._save_backup(ac.read_ir_area(self.worker.report_progress), "completo")
            ac.write_ir_area(image, self.worker.report_progress)
            return backup
        self.worker.submit(job, lambda b: self._msg(f"IRs gravados e conferidos. Backup anterior: {b}"),
                           self._error, label="Gravando IRs (backup + gravação + conferência)…")

    @staticmethod
    def _save_backup(data: bytes, tag: str) -> str:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        path = os.path.join(BACKUP_DIR, time.strftime(f"irs-{tag}-%Y%m%d-%H%M%S.bin"))
        with open(path, "wb") as f:
            f.write(data)
        return path

    # ----- utilidades ------------------------------------------------------------

    def _on_busy(self, label):
        working = bool(label)
        self.centralWidget().setEnabled(not working)
        self.progress.setVisible(working)
        self.progress.setRange(0, 0)
        if working:
            self._msg(label)

    def _on_progress(self, cur, total):
        self.progress.setRange(0, total)
        self.progress.setValue(cur)

    def _confirm(self, title, text) -> bool:
        return QMessageBox.question(self, title, text) == YES

    def _error(self, msg):
        self._msg(f"Erro: {msg}")
        QMessageBox.warning(self, APP_NAME, msg)
        if "Sem resposta" in msg:
            self._lost_connection(msg)

    def _msg(self, text):
        self.status.setText(text)

    def closeEvent(self, ev):
        if self.dirty and QMessageBox.question(
                self, APP_NAME, "Há alterações nos presets que não foram salvas no pedal "
                                "(elas valem até desligar o pedal). Sair mesmo assim?") != YES:
            ev.ignore()
            return
        self.live_timer.stop()
        self._flush_live()
        self.worker.stop()
        if self.ac:
            self.ac.dev.close()
        ev.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setDesktopFileName("cubebaby-editor")
    app.setStyleSheet(STYLE)
    icon = os.path.join(os.path.dirname(__file__), "icon.svg")
    if os.path.exists(icon):
        app.setWindowIcon(QIcon(icon))
    win = MainWindow()
    win.resize(980, 640)
    win.show()
    sys.exit(app.exec())
