"""Operações de alto nível do Cube Baby AC (presets, IRs, loopback).

Mapa de memória (ver PROTOCOLO.md):
  banco 5, addr 0            48 bytes = presets A/B/C (16 bytes cada) — permanente
  banco 5, 0x80000000 + n    mesmo byte, aplicado ao vivo
  banco 0, 0x3000            USB loopback (0/1)
  banco 0, ir_base + i*4K    IR i (0..7), apagar setor de 4 KB antes de gravar
"""
from __future__ import annotations

from dataclasses import dataclass

from . import ir
from . import protocol as p
from .device import CubeBaby, DeviceError
from .i18n import T

PRESET_BANK = 5
PRESET_SIZE = 16
PRESET_COUNT = 3
LOOPBACK_ADDR = 0x3000
FLASH_BANK = 0
SECTOR = 0x1000

# Ordem de exibição igual ao CubeSuite: (nome, offset, máximo)
PARAMS = [
    ("VOLUME", 0x05, 127),
    ("IR CAB", 0x09, 8),
    ("TIME", 0x03, 127),
    ("SPACE", 0x07, 31),
    ("MOD", 0x04, 15),
    ("ANTI FB", 0x06, 8),
    ("COMP", 0x08, 8),
    ("BASS", 0x02, 127),
    ("MID", 0x01, 127),
    ("TREB", 0x00, 127),
]
# Liga/desliga de cada seção: (nome, offset, parâmetros controlados)
SWITCHES = [
    ("IR", 0x0A, ["IR CAB"]),
    ("Ambiente", 0x0B, ["TIME", "SPACE", "MOD"]),
    ("Tonalidade", 0x0C, ["ANTI FB", "COMP", "BASS", "MID", "TREB"]),
]

# Presets padrão de fábrica (tabela em 0x584738 do CubeSuite, usada pelo Factory Reset)
FACTORY_PRESETS = bytes.fromhex(
    "09 04 32 50 07 64 04 0d 00 01 01 01 01 00 00 00"
    "08 06 60 00 05 64 04 0e 00 02 01 01 01 00 00 00"
    "1d 18 3f 00 07 64 04 0f 00 00 01 01 01 00 00 00"
)


@dataclass
class Presets:
    raw: bytearray

    def get(self, slot: int, offset: int) -> int:
        return self.raw[slot * PRESET_SIZE + offset]

    def set(self, slot: int, offset: int, value: int) -> None:
        self.raw[slot * PRESET_SIZE + offset] = value


class CubeBabyAC:
    def __init__(self, dev: CubeBaby):
        self.dev = dev
        if dev.chip_id != 0x4FCE:
            raise DeviceError(T("Modelo não suportado (id 0x{chip:04X}); este app é para o Cube Baby AC.", chip=dev.chip_id))
        self.ir_base = dev.ir_base
        self.ir_end = self.ir_base + ir.SLOT_COUNT * ir.SLOT_SIZE

    # --- presets ------------------------------------------------------------

    def read_presets(self) -> Presets:
        return Presets(bytearray(self.dev.read(PRESET_BANK, 0, PRESET_SIZE * PRESET_COUNT)))

    def set_live(self, slot: int, offset: int, value: int) -> None:
        self.dev.write(PRESET_BANK, p.LIVE + slot * PRESET_SIZE + offset, bytes([value]))

    def save_presets(self, presets: Presets) -> None:
        self._write_verified(PRESET_BANK, 0, bytes(presets.raw))

    def factory_reset(self) -> Presets:
        self._write_verified(PRESET_BANK, 0, FACTORY_PRESETS)
        return self.read_presets()

    # --- loopback -------------------------------------------------------------

    def get_loopback(self) -> bool:
        return self.dev.read(FLASH_BANK, LOOPBACK_ADDR, 1)[0] != 0

    def set_loopback(self, on: bool) -> None:
        self.dev.write(FLASH_BANK, LOOPBACK_ADDR, bytes([1 if on else 0]))

    # --- IRs --------------------------------------------------------------------

    def read_ir_area(self, progress=None) -> bytes:
        out = bytearray()
        for i in range(ir.SLOT_COUNT):
            out += self.dev.read(FLASH_BANK, self.ir_base + i * ir.SLOT_SIZE, ir.SLOT_SIZE)
            if progress:
                progress(i + 1, ir.SLOT_COUNT)
        return bytes(out)

    def write_ir_slot(self, slot: int, record: bytes) -> None:
        if not 0 <= slot < ir.SLOT_COUNT or len(record) > ir.SLOT_SIZE:
            raise ValueError("slot ou tamanho de IR inválido")
        addr = self.ir_base + slot * ir.SLOT_SIZE
        self._erase(addr)
        self._write_verified(FLASH_BANK, addr, record)

    def write_ir_area(self, image: bytes, progress=None) -> None:
        """Grava os 8 slots de uma vez (Factory IR ou restauração de backup)."""
        if len(image) != ir.SLOT_COUNT * ir.SLOT_SIZE:
            raise ValueError("imagem de IR deve ter 32 KB")
        for i in range(ir.SLOT_COUNT):
            slot = image[i * ir.SLOT_SIZE:(i + 1) * ir.SLOT_SIZE]
            used = slot.rstrip(b"\xFF") or slot[:1]
            addr = self.ir_base + i * ir.SLOT_SIZE
            self._erase(addr)
            self._write_verified(FLASH_BANK, addr, used)
            if progress:
                progress(i + 1, ir.SLOT_COUNT)

    # --- internos -----------------------------------------------------------------

    def _check_flash_range(self, addr: int, length: int) -> None:
        # Trava de segurança: o banco 0 também guarda o firmware. Só a área de IRs pode ser apagada/gravada.
        if not (self.ir_base <= addr and addr + length <= self.ir_end):
            raise DeviceError(T("Bloqueado: 0x{addr:X}+{length} fora da área de IRs.", addr=addr, length=length))

    def _erase(self, addr: int) -> None:
        self._check_flash_range(addr, SECTOR)
        if addr % SECTOR:
            raise DeviceError(T("Endereço de apagamento não alinhado ao setor"))
        fr = self.dev.transact(p.build_frame(p.CMD_ERASE, bytes([FLASH_BANK]) + addr.to_bytes(4, "little")),
                               p.CMD_ACK, timeout=30.0)
        if fr.data[:1] != b"\x00":
            raise DeviceError(T("Falha ao apagar setor 0x{addr:X}", addr=addr))

    def _write_verified(self, bank: int, addr: int, data: bytes) -> None:
        if bank == FLASH_BANK and addr != LOOPBACK_ADDR:
            self._check_flash_range(addr, len(data))
        self.dev.write(bank, addr, data)
        if self.dev.read(bank, addr, len(data)) != data:
            raise DeviceError(T("A verificação falhou: o que foi lido do pedal difere do que foi gravado."))
