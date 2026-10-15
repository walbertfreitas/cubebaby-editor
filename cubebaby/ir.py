"""Conversão de arquivos WAV para o formato de IR do Cube Baby.

Registro no pedal (FUN_00499290): 0x808 bytes
  [0]      0
  [4:8]    distance (float32 LE) = valor do botão / 100
  [8:]     512 amostras float32 LE (primeiro canal; completa com zeros)
O slot de 4 KB fica com 0xFF depois do registro (flash apagada).

O CubeSuite (FUN_0050b2c0) só pega as primeiras 512 amostras, sem reamostragem.
Aqui há duas melhorias opcionais:
  - reamostragem para 48 kHz (a taxa do pedal), para o IR soar como foi gravado;
  - conversão para fase mínima antes do corte: concentra a energia no início, então o
    corte em 512 amostras preserva melhor o timbre (sobretudo os graves).
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from fractions import Fraction

import numpy as np
from scipy.signal import resample_poly

from .i18n import T

IR_SAMPLES = 512
IR_RECORD_SIZE = 0x808
SLOT_SIZE = 0x1000
SLOT_COUNT = 8
DEVICE_RATE = 48000


class WavError(Exception):
    pass


@dataclass
class WavInfo:
    channels: int
    sample_rate: int
    bits: int
    fmt: int  # 1 = PCM, 3 = float
    frames: int


@dataclass
class PreparedIR:
    samples: list[float]      # exatamente 512 amostras, prontas para o pedal
    energy_kept: float        # fração da energia do IR (já na taxa final) que coube nas 512 amostras
    resampled: bool
    min_phase: bool
    length_ms: float          # duração do IR completo na taxa final


def read_wav(path: str) -> tuple[np.ndarray, WavInfo]:
    """Lê o primeiro canal inteiro, em -1.0..1.0."""
    with open(path, "rb") as f:
        data = f.read()
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise WavError(T("O arquivo não é um WAV válido (falta o cabeçalho RIFF/WAVE)."))
    pos, fmt_chunk, pcm = 12, None, None
    while pos + 8 <= len(data):
        cid, size = data[pos:pos + 4], struct.unpack_from("<I", data, pos + 4)[0]
        body = data[pos + 8:pos + 8 + size]
        if cid == b"fmt ":
            fmt_chunk = body
        elif cid == b"data":
            pcm = body
        pos += 8 + size + (size & 1)
    if fmt_chunk is None or pcm is None:
        raise WavError(T("WAV sem os blocos 'fmt' ou 'data'."))
    fmt, channels, rate, _brate, align, bits = struct.unpack_from("<HHIIHH", fmt_chunk)
    if fmt == 0xFFFE and len(fmt_chunk) >= 26:  # WAVE_FORMAT_EXTENSIBLE: o subformato fica no GUID
        fmt = struct.unpack_from("<H", fmt_chunk, 24)[0]
    width = bits // 8
    frames = len(pcm) // align if align else 0
    if frames == 0:
        raise WavError(T("O WAV não tem amostras."))
    raw = np.frombuffer(pcm[:frames * align], dtype=np.uint8).reshape(frames, align)[:, :width]
    if fmt == 1 and bits == 16:
        samples = raw.copy().view("<i2")[:, 0] / 32767.0
    elif fmt == 1 and bits == 24:
        padded = np.zeros((frames, 4), dtype=np.uint8)
        padded[:, 1:] = raw
        samples = padded.view("<i4")[:, 0] / 2147483648.0
    elif fmt == 1 and bits == 32:
        samples = raw.copy().view("<i4")[:, 0] / 2147483648.0
    elif fmt == 3 and bits == 32:
        samples = raw.copy().view("<f4")[:, 0].astype(np.float64)
    else:
        raise WavError(T("Formato WAV não suportado ({bits} bits, tipo {fmt}). Use PCM 16/24 bits ou float 32.",
                          bits=bits, fmt=fmt))
    return samples, WavInfo(channels, rate, bits, fmt, frames)


def resample(samples: np.ndarray, rate: int, target: int = DEVICE_RATE) -> np.ndarray:
    if rate == target:
        return samples
    ratio = Fraction(target, rate).limit_denominator(1000)
    return resample_poly(samples, ratio.numerator, ratio.denominator)


def minimum_phase(h: np.ndarray) -> np.ndarray:
    """Mesma resposta de magnitude, energia concentrada no início (método do cepstro real)."""
    n = 1 << (int(np.ceil(np.log2(len(h)))) + 4)
    spectrum = np.fft.fft(h, n)
    cep = np.fft.ifft(np.log(np.maximum(np.abs(spectrum), 1e-9))).real
    fold = np.zeros(n)
    fold[0] = 1
    fold[1:n // 2] = 2
    fold[n // 2] = 1
    return np.fft.ifft(np.exp(np.fft.fft(cep * fold))).real[:len(h)]


def prepare(samples: np.ndarray, rate: int, to_48k: bool = True, min_phase: bool = True) -> PreparedIR:
    h = np.asarray(samples, dtype=np.float64)
    resampled = to_48k and rate != DEVICE_RATE
    if resampled:
        h = resample(h, rate)
    final_rate = DEVICE_RATE if resampled else rate
    if min_phase:
        h = minimum_phase(h)
    total = float(np.sum(h ** 2)) or 1.0
    out = np.zeros(IR_SAMPLES)
    out[:min(IR_SAMPLES, len(h))] = h[:IR_SAMPLES]
    peak = float(np.max(np.abs(out)))
    if peak > 1.0:  # evita saturar o pedal; os IRs de fábrica têm pico <= 1.0
        out /= peak
        total /= peak ** 2
    return PreparedIR(
        samples=[float(v) for v in out],
        energy_kept=float(np.sum(out ** 2)) / total,
        resampled=resampled,
        min_phase=min_phase,
        length_ms=1000.0 * len(h) / final_rate,
    )


def build_record(samples: list[float], distance_percent: int) -> bytes:
    if not 0 <= distance_percent <= 100:
        raise ValueError("distance deve estar entre 0 e 100")
    if len(samples) != IR_SAMPLES:
        raise ValueError(f"o IR precisa ter exatamente {IR_SAMPLES} amostras")
    rec = bytearray(IR_RECORD_SIZE)
    struct.pack_into("<f", rec, 4, distance_percent / 100.0)
    struct.pack_into(f"<{IR_SAMPLES}f", rec, 8, *samples)
    return bytes(rec)


def parse_record(rec: bytes) -> tuple[float, list[float]]:
    distance = struct.unpack_from("<f", rec, 4)[0]
    return distance, list(struct.unpack_from(f"<{IR_SAMPLES}f", rec, 8))
