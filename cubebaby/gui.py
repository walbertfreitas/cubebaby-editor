"""Interface do editor nativo do Cube Baby AC."""
from __future__ import annotations

import math
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
(QApplication, QButtonGroup, QCheckBox, QComboBox, QDial, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
 QLabel, QMainWindow, QMessageBox, QProgressBar, QPushButton, QSlider, QSpinBox, QVBoxLayout,
 QWidget) = (W.QApplication, W.QButtonGroup, W.QCheckBox, W.QComboBox, W.QDial, W.QFileDialog, W.QFrame,
             W.QGridLayout, W.QHBoxLayout, W.QLabel, W.QMainWindow, W.QMessageBox, W.QProgressBar,
             W.QPushButton, W.QSlider, W.QSpinBox, W.QVBoxLayout, W.QWidget)
YES = QMessageBox.StandardButton.Yes

from . import i18n, ir
from .device import CubeBaby, NoResponse
from .i18n import T
from .model import PARAMS, SWITCHES, CubeBabyAC, Presets
from .worker import DeviceWorker

# Paleta monocromática
BG = "#0a0a0a"        # fundo da janela
SURFACE = "#141414"   # cartões
RAISED = "#1f1f1f"    # campos e botões
LINE = "#2a2a2a"      # contornos e trilhos
TEXT = "#f2f2f2"
MUTED = "#8a8a8a"
FAINT = "#4a4a4a"     # desativado
APP_NAME = "Cube Baby Editor"
DATA_DIR = os.path.join(os.path.expanduser("~"), ".local", "share", "cubebaby-editor")
BACKUP_DIR = os.path.join(DATA_DIR, "backups")
FACTORY_IR_FILE = os.path.join(DATA_DIR, "factory", "BCIF.bin")
DEFAULT_CUBESUITE = os.path.expanduser("~")

STYLE = f"""
QWidget {{ background: {BG}; color: {TEXT}; font-family: "Inter"; font-size: 10pt; }}
QLabel, QCheckBox, QSlider {{ background: transparent; }}
QLabel:disabled, QCheckBox:disabled {{ color: {FAINT}; }}
QFrame#card {{ background: {SURFACE}; border-radius: 14px; }}
QFrame#preview {{ background: {BG}; border-radius: 10px; }}
QLabel#section {{ color: {MUTED}; font-size: 8pt; font-weight: 600; }}
QLabel#title {{ font-size: 13pt; font-weight: 600; }}
QLabel#param {{ color: {MUTED}; font-size: 9pt; }}
QLabel#hint, QLabel#status {{ color: {MUTED}; }}
QPushButton {{ border: 1px solid {LINE}; border-radius: 8px; padding: 7px 14px; background: {RAISED}; }}
QPushButton:hover {{ background: #2a2a2a; border-color: #3a3a3a; }}
QPushButton:pressed {{ background: #333333; }}
QPushButton:disabled {{ color: {FAINT}; background: {SURFACE}; border-color: {RAISED}; }}
QPushButton#primary {{ background: {TEXT}; color: {BG}; border: none; font-weight: 600; padding: 9px 14px; }}
QPushButton#primary:hover {{ background: #ffffff; }}
QPushButton#primary:pressed {{ background: #cfcfcf; }}
QPushButton#primary:disabled {{ background: {RAISED}; color: {FAINT}; }}
QFrame#segbar {{ background: {RAISED}; border-radius: 8px; }}
QPushButton#seg {{ border: none; border-radius: 6px; padding: 4px 0; min-width: 34px; background: transparent;
    color: {MUTED}; font-weight: 600; }}
QPushButton#seg:hover {{ color: {TEXT}; }}
QPushButton#seg:checked {{ background: {TEXT}; color: {BG}; }}
QPushButton#seg:disabled {{ color: {FAINT}; }}
QPushButton#seg:checked:disabled {{ background: {LINE}; color: {MUTED}; }}
QSlider::groove:horizontal {{ height: 2px; background: {LINE}; border-radius: 1px; }}
QSlider::sub-page:horizontal {{ background: {TEXT}; border-radius: 1px; }}
QSlider::handle:horizontal {{ background: {TEXT}; width: 12px; margin: -5px 0; border-radius: 6px; }}
QSlider::sub-page:horizontal:disabled {{ background: {FAINT}; }}
QSlider::handle:horizontal:disabled {{ background: {FAINT}; }}
QSpinBox, QComboBox {{ border: 1px solid {LINE}; border-radius: 6px; padding: 3px 6px; background: {RAISED}; }}
QSpinBox:focus, QComboBox:focus {{ border-color: #5a5a5a; }}
QSpinBox {{ padding-right: 18px; min-width: 38px; }}
QSpinBox:disabled, QComboBox:disabled {{ color: {FAINT}; background: {SURFACE}; border-color: {RAISED}; }}
QSpinBox::up-button, QSpinBox::down-button {{ subcontrol-origin: border; width: 16px; background: transparent;
    border: none; }}
QSpinBox::up-button {{ subcontrol-position: top right; }}
QSpinBox::down-button {{ subcontrol-position: bottom right; }}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {{ background: #2e2e2e; }}
QComboBox::drop-down {{ border: none; width: 18px; }}
QComboBox QAbstractItemView {{ background: {RAISED}; border: 1px solid {LINE}; outline: none;
    selection-background-color: {TEXT}; selection-color: {BG}; }}
QProgressBar {{ border: none; border-radius: 2px; background: {LINE}; max-height: 4px; }}
QProgressBar::chunk {{ background: {TEXT}; border-radius: 2px; }}
QToolTip {{ background: {RAISED}; color: {TEXT}; border: 1px solid {LINE}; padding: 4px; }}
@ARROWS@
"""


def _arrow_png(path: str, up: bool, color: str) -> str:
    """Desenha uma seta (chevron) em PNG para os campos numéricos e listas."""
    pix = QtGui.QPixmap(10, 6)
    pix.fill(QColor(0, 0, 0, 0))
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color), 1.6)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    pts = [QtCore.QPointF(1.5, 5), QtCore.QPointF(5, 1.5), QtCore.QPointF(8.5, 5)] if up else \
          [QtCore.QPointF(1.5, 1), QtCore.QPointF(5, 4.5), QtCore.QPointF(8.5, 1)]
    p.drawPolyline(QtGui.QPolygonF(pts))
    p.end()
    pix.save(path, "PNG")
    return path


def _check_png(path: str) -> str:
    """Marca de seleção preta, desenhada sobre o fundo branco da caixa marcada."""
    pix = QtGui.QPixmap(14, 14)
    pix.fill(QColor(0, 0, 0, 0))
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(BG), 2)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.drawPolyline(QtGui.QPolygonF([QtCore.QPointF(3, 7.5), QtCore.QPointF(6, 10.5), QtCore.QPointF(11, 4)]))
    p.end()
    pix.save(path, "PNG")
    return path


def app_style() -> str:
    """Folha de estilo completa; as setas são geradas na hora (precisa de um QApplication ativo)."""
    folder = os.path.join(os.path.expanduser("~"), ".cache", "cubebaby-editor")
    os.makedirs(folder, exist_ok=True)
    rules = []
    for name, up in (("up", True), ("down", False)):
        on = _arrow_png(os.path.join(folder, f"chevron-{name}.png"), up, TEXT)
        off = _arrow_png(os.path.join(folder, f"chevron-{name}-off.png"), up, FAINT)
        rules.append(f"QSpinBox::{name}-arrow {{ image: url({on}); width: 10px; height: 6px; }}")
        rules.append(f"QSpinBox::{name}-arrow:disabled, QSpinBox::{name}-arrow:off {{ image: url({off}); }}")
        if not up:
            muted = _arrow_png(os.path.join(folder, "chevron-down-muted.png"), up, MUTED)
            rules.append(f"QComboBox::down-arrow {{ image: url({muted}); width: 10px; height: 6px; }}")
            rules.append(f"QComboBox::down-arrow:disabled {{ image: url({off}); }}")
    check = _check_png(os.path.join(folder, "check-mono.png"))
    rules.append(f"QCheckBox::indicator {{ width: 14px; height: 14px; border: 1px solid #5a5a5a; border-radius: 4px; "
                 f"background: transparent; }}")
    rules.append(f"QCheckBox::indicator:checked {{ background: {TEXT}; border-color: {TEXT}; image: url({check}); }}")
    rules.append(f"QCheckBox::indicator:disabled {{ border-color: {LINE}; background: transparent; }}")
    return STYLE.replace("@ARROWS@", "\n".join(rules))


def card(title_label: QLabel) -> tuple[QFrame, QVBoxLayout]:
    """Cartão sem borda com um título pequeno em maiúsculas."""
    frame = QFrame(objectName="card")
    v = QVBoxLayout(frame)
    v.setContentsMargins(18, 16, 18, 18)
    v.setSpacing(12)
    v.addWidget(title_label)
    return frame, v


class SectionLabel(QLabel):
    """Título de seção: maiúsculas e letras espaçadas."""

    def __init__(self):
        super().__init__(objectName="section")
        font = self.font()
        font.setLetterSpacing(QtGui.QFont.SpacingType.AbsoluteSpacing, 1.4)
        self.setFont(font)

    def setText(self, text):
        super().setText(text.upper())


class Toggle(QCheckBox):
    """Chave liga/desliga: texto à esquerda e a chave à direita; a linha inteira é clicável."""

    def __init__(self, text="", divider=False, **kw):
        super().__init__(text, **kw)
        self.divider = divider
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def sizeHint(self):
        return QtCore.QSize(160, 40 if self.divider else 28)

    def hitButton(self, pos):
        return self.rect().contains(pos)

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        enabled, on = self.isEnabled(), self.isChecked()
        if self.divider:
            p.setPen(QPen(QColor(LINE), 1))
            p.drawLine(0, 0, w, 0)
        cy = (h + (6 if self.divider else 0)) / 2
        font = self.font()
        font.setWeight(QtGui.QFont.Weight.DemiBold if self.divider else QtGui.QFont.Weight.Normal)
        p.setFont(font)
        p.setPen(QColor(TEXT if enabled and (on or not self.divider) else MUTED if enabled else FAINT))
        p.drawText(QtCore.QRectF(0, cy - 10, w - 50, 20),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.text())
        track = QtCore.QRectF(w - 36, cy - 10, 36, 20)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor((TEXT if on else LINE) if enabled else RAISED))
        p.drawRoundedRect(track, 10, 10)
        knob_x = track.right() - 18 if on else track.left() + 2
        p.setBrush(QColor((BG if on else MUTED) if enabled else FAINT))
        p.drawEllipse(QtCore.QRectF(knob_x, cy - 8, 16, 16))


class Knob(QDial):
    """Botão giratório minimalista: arco de 270° com o valor em branco e um traço indicador."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = min(self.width(), self.height()) - 8
        rect = QtCore.QRectF((self.width() - side) / 2, (self.height() - side) / 2, side, side)
        span = self.maximum() - self.minimum()
        frac = (self.value() - self.minimum()) / span if span else 0
        pen = QPen(QColor(LINE), 3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawArc(rect, 225 * 16, -270 * 16)
        if frac > 0:
            pen.setColor(QColor(TEXT if self.isEnabled() else FAINT))
            p.setPen(pen)
            p.drawArc(rect, 225 * 16, int(-270 * 16 * frac))
        inner = rect.adjusted(9, 9, -9, -9)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(RAISED))
        p.drawEllipse(inner)
        angle = math.radians(225 - 270 * frac)
        c, r = inner.center(), inner.width() / 2
        pen = QPen(QColor(TEXT if self.isEnabled() else FAINT), 2.4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawLine(QtCore.QPointF(c.x() + math.cos(angle) * r * 0.35, c.y() - math.sin(angle) * r * 0.35),
                   QtCore.QPointF(c.x() + math.cos(angle) * r * 0.78, c.y() - math.sin(angle) * r * 0.78))


class IrPreview(QFrame):
    """Desenha a forma de onda das 512 amostras do IR."""

    def __init__(self):
        super().__init__(objectName="preview")
        self.samples: list[float] = []
        self.setMinimumSize(260, 130)

    def set_samples(self, samples):
        self.samples = list(samples)
        self.update()

    def paintEvent(self, ev):
        super().paintEvent(ev)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        mid = h / 2
        p.setPen(QPen(QColor(LINE), 1))
        p.drawLine(12, int(mid), w - 12, int(mid))
        if not self.samples:
            p.setPen(QColor(FAINT))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, T("Nenhum IR carregado"))
            return
        peak = max(1e-9, max(abs(s) for s in self.samples))
        path = QPainterPath()
        n = len(self.samples)
        for i, s in enumerate(self.samples):
            x = 12 + (w - 24) * i / (n - 1)
            y = mid - (h / 2 - 12) * s / peak
            path.moveTo(x, y) if i == 0 else path.lineTo(x, y)
        p.setPen(QPen(QColor(TEXT), 1.2))
        p.drawPath(path)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.settings = QSettings("cubebaby-editor", "cubebaby-editor")
        i18n.set_language(self.settings.value("language", i18n.default_language()))
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
        self._texts: list = []        # funções que reaplicam os textos fixos no idioma atual
        self._last_msg = ("Procurando o pedal…", {})

        self._build_ui()
        self._set_connected(False)
        self._retranslate()

        self.live_timer = QTimer(self, singleShot=True, interval=40, timeout=self._flush_live)
        self.reconnect_timer = QTimer(self, interval=3000, timeout=self._connect)
        self._connect()

    # ----- idioma ------------------------------------------------------------

    def _tr(self, widget, setter: str, text: str):
        """Registra um texto fixo para ser retraduzido quando o idioma mudar."""
        self._texts.append(lambda: getattr(widget, setter)(T(text)))
        return widget

    def _retranslate(self):
        for apply in self._texts:
            apply()
        self.dial_label.setText(T("Distance: {v}%", v=self.dial.value()))
        self._set_dirty(self.dirty)
        self._set_connected(self.ac is not None)
        for off, btn in self.switch_buttons.items():
            self._apply_switch_state(off, btn)
        self._refresh_ir()
        self.preview.update()
        self._msg(self._last_msg[0], **self._last_msg[1])

    def _on_language(self, index):
        code = self.lang_combo.itemData(index)
        i18n.set_language(code)
        self.settings.setValue("language", code)
        self._retranslate()

    # ----- interface -------------------------------------------------------

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(20, 16, 20, 14)
        outer.setSpacing(14)

        header = QHBoxLayout()
        header.addWidget(QLabel(APP_NAME, objectName="title"))
        header.addStretch(1)
        self.conn_dot = QLabel("●")
        self.conn_label = QLabel(objectName="hint")
        header.addWidget(self.conn_dot)
        header.addWidget(self.conn_label)
        outer.addLayout(header)

        cols = QHBoxLayout()
        cols.setSpacing(14)
        outer.addLayout(cols, 1)
        cols.addLayout(self._build_ir_column(), 1)
        cols.addWidget(self._build_preset_group(), 1)

        bottom = QHBoxLayout()
        self.status = QLabel(objectName="status")
        self.progress = QProgressBar(maximumWidth=180, visible=False, textVisible=False)
        self.lang_combo = QComboBox()
        for code, name in i18n.LANGS.items():
            self.lang_combo.addItem(name, code)
        self.lang_combo.setCurrentIndex(list(i18n.LANGS).index(i18n.language()))
        self.lang_combo.currentIndexChanged.connect(self._on_language)
        bottom.addWidget(self.status, 1)
        bottom.addWidget(self.progress)
        bottom.addSpacing(12)
        bottom.addWidget(self._tr(QLabel(objectName="hint"), "setText", "Idioma:"))
        bottom.addWidget(self.lang_combo)
        outer.addLayout(bottom)

    def _build_ir_column(self):
        col = QVBoxLayout()
        col.setSpacing(14)
        box, v = card(self._tr(SectionLabel(), "setText", "Importar IR"))
        self.preview = IrPreview()
        self.btn_open = self._tr(QPushButton(clicked=self._open_wav), "setText", "Abrir arquivo WAV…")
        self.ir_info = QLabel("", objectName="hint", wordWrap=True)
        self.chk_48k = self._tr(QCheckBox(checked=self.settings.value("to_48k", True, type=bool)),
                                "setText", "Converter para 48 kHz")
        self.chk_minphase = self._tr(QCheckBox(checked=self.settings.value("min_phase", True, type=bool)),
                                     "setText", "Otimizar para 512 amostras (fase mínima)")
        self._tr(self.chk_minphase, "setToolTip",
                 "Concentra a energia do IR no início, para que o corte em 512 amostras (limite do pedal) "
                 "preserve melhor o timbre, sobretudo os graves.")
        for chk in (self.chk_48k, self.chk_minphase):
            chk.toggled.connect(self._refresh_ir)
        self.dial = Knob(minimum=0, maximum=100, value=50)
        self.dial.setFixedSize(64, 64)
        self.dial_label = QLabel()
        self.dial.valueChanged.connect(lambda val: self.dial_label.setText(T("Distance: {v}%", v=val)))
        self.slot_combo = QComboBox()
        self.slot_combo.addItems([str(i) for i in range(1, ir.SLOT_COUNT + 1)])
        self.btn_import = self._tr(QPushButton(clicked=self._import_ir, enabled=False, objectName="primary"),
                                   "setText", "Gravar IR no pedal")

        v.addWidget(self.preview, 1)
        v.addWidget(self.btn_open)
        v.addWidget(self.ir_info)
        v.addWidget(self.chk_48k)
        v.addWidget(self.chk_minphase)
        row = QHBoxLayout()
        row.setSpacing(12)
        row.addWidget(self.dial)
        row.addWidget(self.dial_label)
        row.addStretch(1)
        row.addWidget(self._tr(QLabel(), "setText", "Gravar no slot:"))
        row.addWidget(self.slot_combo)
        v.addLayout(row)
        v.addWidget(self.btn_import)
        col.addWidget(box, 1)

        tools, t = card(self._tr(SectionLabel(), "setText", "Ferramentas"))
        grid = QGridLayout()
        grid.setSpacing(8)
        self.btn_backup = self._tr(QPushButton(clicked=self._backup_irs), "setText", "Fazer backup dos IRs…")
        self.btn_restore = self._tr(QPushButton(clicked=self._restore_irs), "setText", "Restaurar backup de IRs…")
        self.btn_factory_ir = self._tr(QPushButton(clicked=self._factory_ir), "setText", "IRs de fábrica")
        self.btn_factory_reset = self._tr(QPushButton(clicked=self._factory_reset), "setText", "Presets de fábrica")
        self.chk_loopback = Toggle("USB Loopback")
        self.chk_loopback.toggled.connect(self._on_loopback)
        grid.addWidget(self.btn_backup, 0, 0)
        grid.addWidget(self.btn_restore, 0, 1)
        grid.addWidget(self.btn_factory_ir, 1, 0)
        grid.addWidget(self.btn_factory_reset, 1, 1)
        t.addLayout(grid)
        t.addWidget(self.chk_loopback)
        col.addWidget(tools)
        self.device_widgets = [self.btn_backup, self.btn_restore, self.btn_factory_ir,
                               self.btn_factory_reset, self.chk_loopback]
        return col

    def _build_preset_group(self):
        title = self._tr(SectionLabel(), "setText", "Preset")
        box, v = card(title)
        v.removeWidget(title)
        top = QHBoxLayout()
        top.addWidget(title)
        top.addStretch(1)
        segbar = QFrame(objectName="segbar")
        seg = QHBoxLayout(segbar)
        seg.setContentsMargins(3, 3, 3, 3)
        seg.setSpacing(2)
        self.preset_buttons = QButtonGroup(self)
        for i, name in enumerate("ABC"):
            btn = QPushButton(name, checkable=True, checked=i == 0, objectName="seg")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.preset_buttons.addButton(btn, i)
            seg.addWidget(btn)
        self.preset_buttons.idClicked.connect(lambda _i: self._show_preset())
        top.addWidget(segbar)
        v.addLayout(top)

        self.sliders: dict[str, tuple[QSlider, QSpinBox, int]] = {}
        self.switch_buttons: dict[int, Toggle] = {}
        switch_before = {params[0]: (name, off) for name, off, params in SWITCHES}
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(6)
        grid.setColumnMinimumWidth(0, 64)
        row = 0
        for name, offset, maximum in PARAMS:
            if name in switch_before:
                sname, soff = switch_before[name]
                btn = Toggle(checked=True, divider=True)
                btn.toggled.connect(partial(self._on_switch, soff, sname))
                self.switch_buttons[soff] = btn
                grid.addWidget(btn, row, 0, 1, 3)
                row += 1
            label = QLabel(name, objectName="param")  # nomes iguais aos impressos no pedal; não traduzir
            slider = QSlider(Qt.Orientation.Horizontal, minimum=0, maximum=maximum)
            slider.setCursor(Qt.CursorShape.PointingHandCursor)
            spin = QSpinBox(minimum=0, maximum=maximum, alignment=Qt.AlignmentFlag.AlignRight)
            slider.valueChanged.connect(spin.setValue)
            spin.valueChanged.connect(slider.setValue)
            spin.valueChanged.connect(partial(self._on_param, offset))
            grid.addWidget(label, row, 0)
            grid.addWidget(slider, row, 1)
            grid.addWidget(spin, row, 2)
            self.sliders[name] = (slider, spin, offset)
            row += 1
        v.addLayout(grid)
        v.addStretch(1)
        self.btn_save = QPushButton(clicked=self._save_presets, objectName="primary")
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
        self._msg("Conectado: Cube Baby AC (chip 0x{chip:04X}).", chip=self.ac.dev.chip_id)
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
            self._msg("Backup inicial do pedal salvo em {path}", path=path)
            QMessageBox.information(
                self, APP_NAME,
                T("Primeira conexão: os 8 IRs e os 3 presets que estavam no pedal foram salvos em\n{dir}\n\n"
                  "Para voltar a eles, use \"Restaurar backup de IRs…\".", dir=BACKUP_DIR))
        self.worker.submit(job, done, self._error, label="Primeira conexão: fazendo backup dos IRs do pedal…")

    def _on_connect_failed(self, err):
        self._set_connected(False)
        self._msg("{msg} Tentando de novo…", msg=str(err))
        if not self.reconnect_timer.isActive():
            self.reconnect_timer.start()

    def _lost_connection(self, err):
        if self.ac:
            try:
                self.ac.dev.close()
            except Exception:  # noqa: BLE001
                pass
        self.ac = None
        self._on_connect_failed(T("Conexão perdida: {msg}.", msg=str(err)))

    def _set_connected(self, ok: bool):
        self.conn_dot.setStyleSheet(f"color: {TEXT if ok else FAINT}; font-size: 8pt;")
        self.conn_label.setText(T("Conectado" if ok else "Desconectado"))
        self.preset_box.setEnabled(ok)
        for w in self.device_widgets:
            w.setEnabled(ok)
        self.btn_import.setEnabled(ok and self.ir_samples is not None)

    # ----- presets -----------------------------------------------------------

    def _slot(self) -> int:
        return self.preset_buttons.checkedId()

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
        btn.setText(T(sname))
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
        self.btn_save.setText(T("Salvar presets no pedal") + (" *" if dirty else ""))

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
                           lambda _r: self._msg("USB Loopback ligado." if on else "USB Loopback desligado."),
                           self._error)

    # ----- IRs -----------------------------------------------------------------

    def _open_wav(self):
        path, _ = QFileDialog.getOpenFileName(self, T("Abrir IR (WAV)"), self.settings.value("last_dir", ""),
                                              T("Arquivos WAV (*.wav)"))
        if not path:
            return
        self.settings.setValue("last_dir", os.path.dirname(path))
        try:
            samples, info = ir.read_wav(path)
        except (ir.WavError, OSError, ValueError) as e:
            self._error(e)
            return
        self.wav = (os.path.basename(path), samples, info)
        self._refresh_ir()
        self.btn_import.setEnabled(self.ac is not None)

    def _refresh_ir(self):
        self.settings.setValue("to_48k", self.chk_48k.isChecked())
        self.settings.setValue("min_phase", self.chk_minphase.isChecked())
        if not self.wav:
            return
        name, samples, info = self.wav
        prepared = ir.prepare(samples, info.sample_rate, self.chk_48k.isChecked(), self.chk_minphase.isChecked())
        self.ir_samples = prepared.samples
        self.preview.set_samples(prepared.samples)
        lines = [name, T("{ch} canal(is), {rate} Hz, {bits} bits {kind}, {frames} amostras", ch=info.channels,
                         rate=info.sample_rate, bits=info.bits, kind="float" if info.fmt == 3 else "PCM",
                         frames=info.frames)]
        if info.sample_rate != ir.DEVICE_RATE:
            lines.append(T("Convertido de {rate} para 48000 Hz.", rate=info.sample_rate) if prepared.resampled
                         else T("⚠ Sem conversão: o pedal toca a 48000 Hz, o timbre fica alterado."))
        lines.append(T("O pedal guarda {kept:.1f} ms de {total:.1f} ms; {pct:.1f}% da energia do IR coube.",
                       kept=ir.IR_SAMPLES / 48, total=prepared.length_ms, pct=100 * prepared.energy_kept))
        self.ir_info.setText("\n".join(lines))

    def _import_ir(self):
        slot = self.slot_combo.currentIndex()
        if not self._confirm("Gravar IR", "O IR atual do slot {n} será substituído.\n"
                                          "Uma cópia de segurança dele será salva antes. Continuar?", n=slot + 1):
            return
        record = ir.build_record(self.ir_samples, self.dial.value())
        ac = self.ac

        def job():
            old = ac.dev.read(0, ac.ir_base + slot * ir.SLOT_SIZE, ir.SLOT_SIZE)
            backup = self._save_backup(old, f"slot{slot + 1}")
            ac.write_ir_slot(slot, record)
            return backup
        self.worker.submit(job, lambda b: self._msg("IR gravado no slot {n}. Backup do anterior: {path}",
                                                    n=slot + 1, path=b),
                           self._error, label=T("Gravando IR no slot {n}…", n=slot + 1))

    def _backup_irs(self):
        default = os.path.join(BACKUP_DIR, time.strftime("irs-%Y%m%d-%H%M%S.bin"))
        os.makedirs(BACKUP_DIR, exist_ok=True)
        path, _ = QFileDialog.getSaveFileName(self, T("Salvar backup dos IRs"), default, T("Backup de IRs (*.bin)"))
        if not path:
            return
        ac = self.ac

        def job():
            data = ac.read_ir_area(self.worker.report_progress)
            with open(path, "wb") as f:
                f.write(data)
            return path
        self.worker.submit(job, lambda p: self._msg("Backup salvo em {path}", path=p), self._error,
                           label="Lendo os 8 IRs do pedal…")

    def _restore_irs(self):
        path, _ = QFileDialog.getOpenFileName(self, T("Restaurar backup de IRs"), BACKUP_DIR,
                                              T("Backup de IRs (*.bin)"))
        if not path:
            return
        if os.path.getsize(path) == ir.SLOT_SIZE:
            self._restore_slot(path)
        else:
            self._write_ir_image(path, "Restaurar backup",
                                 T("Os 8 IRs do pedal serão substituídos pelo conteúdo de\n{path}\n\nContinuar?",
                                   path=path))

    def _restore_slot(self, path):
        """Backup de um slot só (criado automaticamente antes de gravar um IR)."""
        with open(path, "rb") as f:
            data = f.read()
        match = re.search(r"slot(\d)", os.path.basename(path))
        slot = int(match.group(1)) - 1 if match else self.slot_combo.currentIndex()
        if not 0 <= slot < ir.SLOT_COUNT:
            self._error(T("Não foi possível identificar o slot deste backup."))
            return
        where = T("identificado pelo nome do arquivo" if match else "escolhido em 'Gravar no slot'")
        if not self._confirm("Restaurar slot", "Este é o backup de um único IR.\nEle será gravado no slot "
                                               "{n} ({where}).\n\nContinuar?", n=slot + 1, where=where):
            return
        ac = self.ac

        def job():
            old = ac.dev.read(0, ac.ir_base + slot * ir.SLOT_SIZE, ir.SLOT_SIZE)
            backup = self._save_backup(old, f"slot{slot + 1}")
            ac.write_ir_slot(slot, data)
            return backup
        self.worker.submit(job, lambda b: self._msg("Slot {n} restaurado. Backup do anterior: {path}",
                                                    n=slot + 1, path=b),
                           self._error, label=T("Restaurando o slot {n}…", n=slot + 1))

    def _factory_ir(self):
        path = FACTORY_IR_FILE
        if not os.path.exists(path):
            folder = self.settings.value("cubesuite_dir", DEFAULT_CUBESUITE)
            found = os.path.join(folder, "bin", "BCIF.bin")
            if not os.path.exists(found):
                found, _ = QFileDialog.getOpenFileName(self, T("Localize o BCIF.bin (pasta bin do CubeSuite)"),
                                                       folder, "BCIF.bin (BCIF.bin)")
                if not found:
                    return
            if os.path.getsize(found) != ir.SLOT_COUNT * ir.SLOT_SIZE:
                self._error(T("Este BCIF.bin tem tamanho inesperado; o certo é 32768 bytes."))
                return
            # Guarda uma cópia na pasta do app: depois disso a pasta do CubeSuite não é mais necessária.
            os.makedirs(os.path.dirname(FACTORY_IR_FILE), exist_ok=True)
            shutil.copyfile(found, FACTORY_IR_FILE)
            self._msg("IRs de fábrica copiados para {path}", path=FACTORY_IR_FILE)
        self._write_ir_image(path, "IRs de fábrica",
                             T("Os 8 IRs do pedal serão substituídos pelos IRs de fábrica.\n"
                               "IRs personalizados serão perdidos, mas um backup completo é feito antes.\n\n"
                               "Continuar?"))

    def _write_ir_image(self, path, title, question):
        try:
            with open(path, "rb") as f:
                image = f.read()
        except OSError as e:
            self._error(e)
            return
        if len(image) != ir.SLOT_COUNT * ir.SLOT_SIZE:
            self._error(T("Arquivo com tamanho inesperado ({size} bytes). Um backup completo tem 32768 bytes "
                          "(8 IRs) e o de um slot, 4096.", size=len(image)))
            return
        if QMessageBox.question(self, T(title), question) != YES:
            return
        ac = self.ac

        def job():
            backup = self._save_backup(ac.read_ir_area(self.worker.report_progress), "completo")
            ac.write_ir_area(image, self.worker.report_progress)
            return backup
        self.worker.submit(job, lambda b: self._msg("IRs gravados e conferidos. Backup anterior: {path}", path=b),
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

    def _confirm(self, title, text, **kw) -> bool:
        return QMessageBox.question(self, T(title), T(text, **kw)) == YES

    def _error(self, err):
        msg = str(err)
        self._msg("Erro: {msg}", msg=msg)
        QMessageBox.warning(self, APP_NAME, msg)
        if isinstance(err, NoResponse):
            self._lost_connection(err)

    def _msg(self, text, **kw):
        """Mostra uma mensagem na barra de baixo (texto em pt; é traduzido e lembrado para trocas de idioma)."""
        self._last_msg = (text, kw)
        self.status.setText(T(text, **kw))

    def closeEvent(self, ev):
        if self.dirty and QMessageBox.question(
                self, APP_NAME, T("Há alterações nos presets que não foram salvas no pedal (elas valem até "
                                  "desligar o pedal). Sair mesmo assim?")) != YES:
            ev.ignore()
            return
        self.live_timer.stop()
        self._flush_live()
        self.worker.stop()
        if self.ac:
            self.ac.dev.close()
        ev.accept()


def main():
    # No Wayland o Qt desenha uma barra de título própria, fora do tema do sistema; pelo XWayland quem
    # desenha é o GNOME, igual às outras janelas. Um QT_QPA_PLATFORM definido pelo usuário tem prioridade.
    if os.environ.get("XDG_SESSION_TYPE") == "wayland" and os.environ.get("DISPLAY"):
        os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
    # No X11 o GNOME liga a janela ao .desktop (e ao ícone) pelo WM_CLASS, que o Qt tira do argv[0].
    app = QApplication(["cubebaby-editor"] + sys.argv[1:])
    app.setApplicationName(APP_NAME)
    app.setDesktopFileName("cubebaby-editor")
    app.setStyleSheet(app_style())
    icon = os.path.join(os.path.dirname(__file__), "icon.svg")
    if os.path.exists(icon):
        app.setWindowIcon(QIcon(icon))
    win = MainWindow()
    win.resize(1000, 700)
    win.show()
    sys.exit(app.exec())
