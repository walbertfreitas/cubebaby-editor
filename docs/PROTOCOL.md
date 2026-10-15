# Cube Baby AC — USB/MIDI protocol

Reverse-engineered for **interoperability** from the vendor editor *CubeSuite V2.8.10*
(`CubeSuite.exe`, SHA-256 `0e0183fd6dc1b347534c9ce1e3677ecda2a6ae77fe3da8d6314d43c7c2cfd2e6`)
by capturing USB traffic between CubeSuite (running under Wine) and a real pedal, and by
static analysis of the executable with Ghidra. Function addresses (`FUN_xxxxxxxx`) refer to
that executable and are kept so others can verify the findings.

Device: **Cube Baby AC** (Cuvave / M-VAVE), USB ID `301a:5555` ("SmartlinkTechnology USB2.0 Device"),
firmware reported as `V0.0.1`, chip id `0x4FCE`.

> Only the **Cube Baby AC** was tested. Other models of the family share the transport and
> framing but have different memory maps — do not write to them with these addresses.

---

## 1. USB layer

The pedal is **class compliant**; no vendor driver is needed on Linux (`snd-usb-audio`).

| Function | Details |
|---|---|
| Audio capture | 1 channel, 48 kHz, S16_LE |
| Audio playback | 2 channels, 48 kHz, S16_LE |
| MIDI | ALSA port `USB2.0 Device MIDI 1` (bulk endpoints `0x03` OUT / `0x83` IN) |

The editor protocol runs entirely over **MIDI System Exclusive** messages.

## 2. SysEx transport (`FUN_00486980`)

```
F0 <7-bit packed payload> F7
```

Packing is an **LSB-first bit stream**: every 8-bit byte is appended to an accumulator and
7-bit slices are emitted (bit 7 always 0). Leftover bits are emitted as a final byte.
Unpacking is the inverse (accumulate 7 bits per byte, emit 8).

```python
def pack7(data):
    out, acc, n = bytearray(), 0, 0
    for b in data:
        acc |= b << n; n += 8
        while n >= 7:
            out.append(acc & 0x7F); acc >>= 7; n -= 7
    if n: out.append(acc & 0x7F)
    return bytes(out)
```

Because of the packing, the visible prefix `F0 00 32 …` is **not** a manufacturer ID — it is
the packed form of the frame header below.

## 3. Frame (inside the unpacked payload)

```
00 59 | CMD (u8) | LEN (u24 LE) | DATA[LEN] | CHK
```

- `00 59` — constant magic (`0x5900` little-endian, `DAT_00756ad0`).
- `CHK = ~sum(DATA) & 0xFF`; an empty DATA gives `0xFF` (validated by `FUN_00507970`,
  which logs `"Checksum error,calc=%.2X, got=%.2X"`).

## 4. Commands

Frame builders live at `0x507680–0x507930` (class `CUSBPort`).

| CMD | DATA sent | Meaning | Reply |
|---|---|---|---|
| `0x11` | — | Identify | `0x11`: ASCII `"SINCO-CubeBaby"` + 8 bytes |
| `0x12` | — | Status | `0x12`: 6 bytes |
| `0x21` | bank u8, addr u32 | **Erase one flash sector** (30 s timeout) | ACK |
| `0x22` | bank u8, addr u32, len u24, data | **Write memory** | ACK |
| `0x23` | bank u8, addr u32, len u24 | **Read memory** | `0x23`: echoed bank/addr/len + data |
| `0x24` | bank u8, addr u32, len u32 | 16-bit sum of a memory range (used after writes) | `0x24`: bank, addr, len u24, sum u16 |
| `0x50` | `7F 7F` | Mode toggle used by other models (`FUN_005071b0`) | — |

**ACK** = frame with `CMD 0x00`, `LEN 1`, `DATA 00` (status 0 = success).

**Transfer block size** depends on the chip id (`FUN_005071f0`): ids
`0x76DF 0x4F06 0x272E 0x5032 0x4FCE 0x2792 0x4E3E 0x4EA2 0x4F09 0x272F 0x4E3F` use **128 bytes**,
`0x2733 0x29E5 0x2A49` use 512, everything else 1024. Reads carry `block − 15` data bytes.
The Cube Baby AC (`0x4FCE`) therefore uses 128-byte writes and 113-byte reads.

## 5. Device information (bank 0, address `0x2100`, 20 bytes)

Read right after connecting. Five little-endian u32 values:

| Offset | Value on the Cube Baby AC | Meaning |
|---|---|---|
| 0 | `1` | version |
| 4 | `0x4FCE` | chip / model id |
| 8 | `0x30000` | (flash layout) |
| 12 | `0x60000` | (flash layout) |
| 16 | `0x69000` | **base address of the IR area** |

A table inside CubeSuite (`0x7548E0`, 0x54-byte entries) maps `0x4FCE` → `"Cube Baby AC"`,
flash **bank 0**, **sector 0x1000**, size **0x80000** (512 KB).

> ⚠️ **The firmware lives in the same flash (bank 0).** Erasing or writing outside the IR area
> can brick the pedal. The editor refuses any flash erase/write outside `0x69000–0x70FFF`.

## 6. Presets (bank 5)

Three presets (**A, B, C**) of 16 bytes each, stored at bank 5, address 0 (48 bytes).

| Offset | Control | Range |
|---|---|---|
| `0x00` | TREB | 0–127 |
| `0x01` | MID | 0–127 |
| `0x02` | BASS | 0–127 |
| `0x03` | TIME | 0–127 |
| `0x04` | MOD | 0–15 |
| `0x05` | VOLUME | 0–127 |
| `0x06` | ANTI FB | 0–8 |
| `0x07` | SPACE | 0–31 |
| `0x08` | COMP | 0–8 |
| `0x09` | IR CAB | 0–8 |
| `0x0A` | section switch: IR (enables IR CAB) | 0/1 |
| `0x0B` | section switch: TIME / SPACE / MOD | 0/1 |
| `0x0C` | section switch: ANTI FB / COMP / BASS / MID / TREB | 0/1 |
| `0x0D–0x0F` | unused (0) | |

Offsets were confirmed by a guided capture (one control changed at a time) and ranges come
from `FUN_00499bd0`; the switch → section mapping comes from `FUN_0049a8f0`.

- **Live edit:** write 1 byte to bank 5, address `0x80000000 + preset*16 + offset`.
  The high bit means "apply now, do not persist".
- **Save:** write the 48 bytes to bank 5, address `0` (no high bit → persistent), then read back.
- **Factory presets** (`OnResetSound` → `FUN_00498f30`): write the 48-byte default table found
  at `0x584738` to bank 5, address 0.
- Switching the A/B/C selector in CubeSuite sends nothing — it only changes the view.

## 7. USB Loopback (bank 0, address `0x3000`)

One byte, `0` = off, `1` = on. Readable and writable. CubeSuite writes it when the editor opens.

## 8. Impulse responses (IRs)

8 slots in bank 0 at `IR_BASE + slot * 0x1000` (one 4 KB sector each; `IR_BASE = 0x69000`).

Record layout, 0x808 bytes (`FUN_00499290`), rest of the sector left erased (`0xFF`):

| Offset | Type | Content |
|---|---|---|
| 0 | u8 | `0` |
| 4 | float32 LE | **distance** = dial value / 100 (factory IRs use 0.52–0.80) |
| 8 | 512 × float32 LE | IR samples |

How CubeSuite loads a WAV (`FUN_0050b2c0`): first 512 samples of the first channel, scaled
16-bit ÷ 32767, 24-bit ÷ 2²³, float32 as is. **No resampling, no normalisation, no sample-rate
check.** (This editor optionally resamples to 48 kHz and converts to minimum phase before
truncating — see the README.)

Writing a slot (`FUN_00498f50`): `0x21` erase sector → `0x22` write record → `0x23` read back and
compare. *Factory IR* (`FUN_004989b0`) erases all 8 sectors and writes `bin/BCIF.bin` (32 KB,
8 × 4096) shipped with CubeSuite. That file is Cuvave's property and is **not** distributed here.

## 9. Startup sequence observed

```
PC → 0x11 (identify)           ← "SINCO-CubeBaby…"
PC → 0x23 bank 0 0x2100 len 20 ← device information
PC → 0x12 (status)             ← 01 00 00 00 00 00
```

## 10. Not implemented / unknown

- **Firmware update.** The bundled file `cubebaby_A_20220706.up` is for the *non-AC* Cube Baby
  and must never be flashed to an AC. CubeSuite fetches firmware lists over plain HTTP.
- How the firmware uses the per-IR **distance** value.
- Exact meaning of TIME / SPACE / MOD and of `IR CAB = 0` (inferred from names only).

## Tools

- `tools/decode_capture.py` — decodes a `usbmon` pcapng capture into MIDI/SysEx lines.
- `tools/unpack.py` — unpacks those lines and pretty-prints the frames.
