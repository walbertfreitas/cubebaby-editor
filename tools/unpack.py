#!/usr/bin/env python3
"""Desempacota SysEx do Cube Baby (7 bits LSB-first) e descreve o quadro 00 59 CMD LEN DATA CHK."""
import sys

def unpack(b):
    acc = n = 0
    out = bytearray()
    for x in b:
        acc |= (x & 0x7F) << n
        n += 7
        while n >= 8:
            out.append(acc & 0xFF); acc >>= 8; n -= 8
    return bytes(out)

def describe(sysex):
    u = unpack(sysex[1:-1])
    if len(u) < 6 or u[:2] != b"\x00\x59":
        return f"?? {u.hex(' ')}"
    cmd, ln = u[2], int.from_bytes(u[3:6], "little")
    data, chk = u[6:6 + ln], u[6 + ln:6 + ln + 1]
    ok = chk and chk[0] == (~sum(data)) & 0xFF
    return f"cmd={cmd:02X} len={ln} data={data.hex(' ')} chk={'ok' if ok else 'ERRO'}"

if __name__ == "__main__":
    for line in sys.stdin:
        parts = line.split(")")
        if len(parts) < 2: continue
        hexs = parts[1].strip()
        print(line.rstrip()[:30], "|", describe(bytes.fromhex(hexs)))
