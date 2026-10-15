"""Comunicação com o Cube Baby pela porta MIDI do ALSA (python-rtmidi)."""
from __future__ import annotations

import queue
import threading
import time

import rtmidi

from . import protocol as p
from .i18n import T

PORT_HINT = "USB2.0 Device"


class DeviceError(Exception):
    pass


class NoResponse(DeviceError):
    """O pedal não respondeu: normalmente cabo desconectado ou outro programa usando a porta."""


def find_port(midi: rtmidi.MidiIn | rtmidi.MidiOut, hint: str = PORT_HINT) -> int | None:
    for i, name in enumerate(midi.get_ports()):
        if hint in name and "WINE" not in name:
            return i
    return None


class CubeBaby:
    """Conexão com o pedal: envia quadros e espera a resposta correspondente."""

    def __init__(self, hint: str = PORT_HINT):
        self._out = rtmidi.MidiOut(name="CubeBaby Linux")
        self._in = rtmidi.MidiIn(name="CubeBaby Linux")
        self._in.ignore_types(sysex=False)
        oi, ii = find_port(self._out, hint), find_port(self._in, hint)
        if oi is None or ii is None:
            raise DeviceError(T("Pedal não encontrado. Ele está conectado no USB?"))
        self._out.open_port(oi)
        self._in.open_port(ii)
        self._rx: queue.Queue[p.Frame] = queue.Queue()
        self._lock = threading.Lock()
        self._in.set_callback(self._on_midi)
        # Começa com o menor bloco (seguro para qualquer chip) até ler o id real.
        self.block = 0x80
        self.chip_id, self.ir_base = self._flash_info()
        self.block = p.block_size(self.chip_id)

    def _flash_info(self) -> tuple[int, int]:
        raw = self.read(0, p.FLASH_INFO_ADDR, 20)
        chip_id = int.from_bytes(raw[4:8], "little")
        ir_base = int.from_bytes(raw[16:20], "little")
        return chip_id, ir_base

    def close(self):
        self._in.cancel_callback()
        self._in.close_port()
        self._out.close_port()

    def _on_midi(self, event, _data=None):
        msg, _dt = event
        if msg and msg[0] == 0xF0:
            try:
                self._rx.put(p.parse_sysex(bytes(msg)))
            except p.ProtocolError:
                pass

    def transact(self, sysex: bytes, expect_cmd: int, timeout: float = 2.0) -> p.Frame:
        with self._lock:
            while not self._rx.empty():
                self._rx.get_nowait()
            self._out.send_message(list(sysex))
            deadline = time.monotonic() + timeout
            while (left := deadline - time.monotonic()) > 0:
                try:
                    frame = self._rx.get(timeout=left)
                except queue.Empty:
                    break
                if frame.cmd == expect_cmd:
                    return frame
            raise NoResponse(T("Sem resposta do pedal (comando {cmd:02X})", cmd=expect_cmd))

    # --- comandos ---------------------------------------------------------

    def info(self) -> bytes:
        return self.transact(p.build_frame(p.CMD_INFO), p.CMD_INFO).data

    def status(self) -> bytes:
        return self.transact(p.build_frame(p.CMD_STATUS), p.CMD_STATUS).data

    def read(self, bank: int, addr: int, length: int) -> bytes:
        out = bytearray()
        while length > 0:
            n = min(length, self.block - 15)
            fr = self.transact(p.read_frame(bank, addr, n), p.CMD_READ)
            hdr, payload = fr.data[:8], fr.data[8:]
            if hdr != p.mem_header(bank, addr, n) or len(payload) != n:
                raise DeviceError(T("Resposta de leitura inesperada"))
            out += payload
            addr += n
            length -= n
        return bytes(out)

    def write(self, bank: int, addr: int, data: bytes) -> None:
        for off in range(0, len(data), self.block):
            chunk = data[off:off + self.block]
            fr = self.transact(p.write_frame(bank, addr + off, chunk), p.CMD_ACK)
            if fr.data[:1] != b"\x00":
                raise DeviceError(T("Pedal recusou a gravação (status {status})", status=fr.data.hex()))
