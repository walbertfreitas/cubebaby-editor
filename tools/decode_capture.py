#!/usr/bin/env python3
"""Converte uma captura usbmon (pcapng) do Cube Baby em mensagens MIDI/SysEx legíveis.

Uso: decode_capture.py captura.pcapng [--device N]

Lê os endpoints MIDI do pedal (0x03 = PC->pedal, 0x83 = pedal->PC), remonta os
pacotes USB-MIDI (4 bytes: CIN + 3 bytes MIDI) e imprime uma linha por mensagem.
"""
import argparse
import subprocess
import sys

# Quantos bytes MIDI cada Code Index Number (CIN) carrega
CIN_LEN = {0x2: 2, 0x3: 3, 0x4: 3, 0x5: 1, 0x6: 2, 0x7: 3,
           0x8: 3, 0x9: 3, 0xA: 3, 0xB: 3, 0xC: 2, 0xD: 2, 0xE: 3, 0xF: 1}


def find_device(pcap):
    """Endereço USB do pedal (VID 301a), lido dos descritores na captura."""
    out = subprocess.run(
        ["tshark", "-r", pcap, "-Y", "usb.idVendor == 0x301a", "-T", "fields", "-e", "usb.device_address"],
        capture_output=True, text=True).stdout.split()
    return out[0] if out else None


def read_packets(pcap, device):
    filt = (f"usb.device_address=={device} && usb.urb_type=='C' && "
            "(usb.endpoint_address==0x83 || usb.endpoint_address==0x03) && usb.data_len>0")
    filt_out = (f"usb.device_address=={device} && usb.urb_type=='S' && "
                "usb.endpoint_address==0x03 && usb.data_len>0")
    rows = []
    for f in (filt, filt_out):
        out = subprocess.run(
            ["tshark", "-r", pcap, "-Y", f, "-T", "fields",
             "-e", "frame.time_relative", "-e", "usb.endpoint_address", "-e", "usb.capdata"],
            capture_output=True, text=True).stdout
        for line in out.splitlines():
            parts = line.split("\t")
            if len(parts) == 3 and parts[2]:
                rows.append((float(parts[0]), int(parts[1], 16), bytes.fromhex(parts[2].replace(":", ""))))
    rows.sort()
    return rows


def decode(rows):
    """Gera (tempo, direção, bytes_midi) por mensagem completa."""
    buf = {"OUT": bytearray(), "IN": bytearray()}
    start = {"OUT": 0.0, "IN": 0.0}
    for t, ep, data in rows:
        d = "IN" if ep & 0x80 else "OUT"
        for i in range(0, len(data) - 3, 4):
            cin = data[i] & 0x0F
            n = CIN_LEN.get(cin, 0)
            if n == 0:
                continue
            chunk = data[i + 1:i + 1 + n]
            if not buf[d]:
                start[d] = t
            buf[d] += chunk
            if cin != 0x4:  # 0x4 = SysEx continua; os demais encerram a mensagem
                yield start[d], d, bytes(buf[d])
                buf[d].clear()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pcap")
    ap.add_argument("--device")
    a = ap.parse_args()
    dev = a.device or find_device(a.pcap)
    if not dev:
        sys.exit("Pedal (VID 301a) não encontrado na captura; informe --device N (veja lsusb).")
    for t, d, msg in decode(read_packets(a.pcap, dev)):
        arrow = "PC -> pedal" if d == "OUT" else "pedal -> PC"
        print(f"{t:9.3f}  {arrow}  ({len(msg):3d})  {msg.hex(' ').upper()}")


if __name__ == "__main__":
    main()
