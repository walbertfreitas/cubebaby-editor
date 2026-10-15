"""Confere o protocolo contra mensagens reais capturadas entre o CubeSuite e o pedal."""
import os
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cubebaby import ir  # noqa: E402
from cubebaby import protocol as p  # noqa: E402

H = bytes.fromhex


class CapturedFrames(unittest.TestCase):
    def test_info_request(self):
        self.assertEqual(p.build_frame(p.CMD_INFO), H("F0 00 32 45 00 00 00 40 7F F7"))

    def test_status_request(self):
        self.assertEqual(p.build_frame(p.CMD_STATUS), H("F0 00 32 49 00 00 00 40 7F F7"))

    def test_read_flash_info(self):
        self.assertEqual(p.read_frame(0, 0x2100, 0x14),
                         H("F0 00 32 0D 41 00 00 00 00 00 42 00 00 40 02 00 00 4A 01 F7"))

    def test_live_write_volume(self):
        # VOLUME do preset A = 97, capturado em 02-editor.pcapng
        frame = p.parse_sysex(p.write_frame(5, p.LIVE + 5, bytes([0x61])))
        self.assertEqual(frame.cmd, p.CMD_WRITE)
        self.assertEqual(frame.data, H("05 05 00 00 80 01 00 00 61"))

    def test_parse_info_response(self):
        fr = p.parse_sysex(H("F0 00 32 45 58 01 00 40 29 49 1C 0D 7A 54 65 50 3A 62 4A 09 0A 26 2C 1E "
                             "10 20 40 00 01 12 60 04 0A 15 2C 5C 40 11 43 07 F7"))
        self.assertEqual(fr.cmd, p.CMD_INFO)
        self.assertTrue(fr.data.startswith(b"SINCO-CubeBaby"))

    def test_parse_flash_info_response(self):
        fr = p.parse_sysex(H("F0 00 32 0D 61 01 00 00 00 00 42 00 00 40 02 00 00 01 00 00 00 60 79 13 00 "
                             "00 00 00 18 00 00 00 00 06 00 00 00 69 00 40 06 F7"))
        payload = fr.data[8:]
        self.assertEqual(int.from_bytes(payload[4:8], "little"), 0x4FCE)
        self.assertEqual(int.from_bytes(payload[16:20], "little"), 0x69000)

    def test_bad_checksum_rejected(self):
        good = bytearray(p.build_frame(p.CMD_INFO))
        good[-2] ^= 0x01
        with self.assertRaises(p.ProtocolError):
            p.parse_sysex(bytes(good))

    def test_pack_roundtrip(self):
        data = bytes(range(256))
        self.assertEqual(p.unpack7(p.pack7(data))[:256], data)
        self.assertTrue(all(b < 0x80 for b in p.pack7(data)))

    def test_block_size(self):
        self.assertEqual(p.block_size(0x4FCE), 0x80)
        self.assertEqual(p.block_size(0x1234), 0x400)


class IrRecord(unittest.TestCase):
    def _wav(self, samples, bits=16, channels=1, fmt=1):
        width = bits // 8
        frames = b""
        for s in samples:
            if fmt == 3:
                one = struct.pack("<f", s)
            elif bits == 32:
                one = struct.pack("<i", round(s * 2147483647))
            elif bits == 16:
                one = struct.pack("<h", round(s * 32767))
            else:
                one = round(s * 8388608).to_bytes(3, "little", signed=True)
            frames += one * channels
        fmt_chunk = struct.pack("<HHIIHH", fmt, channels, 48000, 48000 * width * channels, width * channels, bits)
        body = b"WAVE" + b"fmt " + struct.pack("<I", 16) + fmt_chunk + b"data" + struct.pack("<I", len(frames)) + frames
        f = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        f.write(b"RIFF" + struct.pack("<I", len(body)) + body)
        f.close()
        self.addCleanup(os.unlink, f.name)
        return f.name

    def test_record_layout(self):
        rec = ir.build_record([0.5] + [0.0] * 511, 85)
        self.assertEqual(len(rec), 0x808)
        self.assertEqual(rec[0], 0)
        self.assertAlmostEqual(struct.unpack_from("<f", rec, 4)[0], 0.85, places=6)
        self.assertAlmostEqual(struct.unpack_from("<f", rec, 8)[0], 0.5, places=6)

    def test_wav_formats(self):
        for bits, fmt in ((16, 1), (24, 1), (32, 1), (32, 3)):
            for ch in (1, 2):
                samples, info = ir.read_wav(self._wav([0.25, -0.5, 0.75], bits=bits, channels=ch, fmt=fmt))
                self.assertEqual(len(samples), 3)
                self.assertAlmostEqual(samples[1], -0.5, places=3)
                self.assertAlmostEqual(samples[2], 0.75, places=3)
                self.assertEqual(info.channels, ch)

    def test_prepare_like_cubesuite(self):
        # Sem as melhorias, deve ser idêntico ao CubeSuite: primeiras 512 amostras, zeros depois.
        samples, info = ir.read_wav(self._wav([0.1 * ((i % 7) - 3) / 3 for i in range(2000)]))
        prep = ir.prepare(samples, info.sample_rate, to_48k=False, min_phase=False)
        self.assertEqual(len(prep.samples), 512)
        self.assertAlmostEqual(prep.samples[511], samples[511], places=9)
        short = ir.prepare(samples[:100], 48000, to_48k=False, min_phase=False)
        self.assertEqual(short.samples[100:], [0.0] * 412)

    def test_resample_44k1(self):
        samples = [1.0] + [0.0] * 2047
        prep = ir.prepare(samples, 44100, to_48k=True, min_phase=False)
        self.assertTrue(prep.resampled)
        self.assertAlmostEqual(prep.length_ms, 2048 / 44.1, delta=0.1)

    def test_min_phase_keeps_magnitude_and_front_loads(self):
        rng = __import__("numpy").random.default_rng(1)
        np = __import__("numpy")
        h = rng.standard_normal(1024) * np.exp(-np.arange(1024) / 300.0)
        m = ir.minimum_phase(h)
        H, M = np.abs(np.fft.rfft(h, 8192)), np.abs(np.fft.rfft(m, 8192))
        # Percentil 99: vales profundos do espectro amplificam diferenças ínfimas em dB.
        self.assertLess(np.percentile(np.abs(20 * np.log10(M / H)), 99), 0.05)
        self.assertGreater(np.sum(m[:256] ** 2), np.sum(h[:256] ** 2))

    def test_never_exceeds_full_scale(self):
        prep = ir.prepare([3.0, -2.0] + [0.0] * 510, 48000, to_48k=False, min_phase=False)
        self.assertLessEqual(max(abs(s) for s in prep.samples), 1.0)

    def test_factory_file_matches_layout(self):
        # O BCIF.bin é da Cuvave e não vai no repositório; aponte CUBEBABY_BCIF para uma cópia sua.
        path = os.environ.get("CUBEBABY_BCIF", os.path.expanduser("~/.local/share/cubebaby-editor/factory/BCIF.bin"))
        if not os.path.exists(path):
            self.skipTest("BCIF.bin não disponível")
        with open(path, "rb") as f:
            data = f.read()
        self.assertEqual(len(data), ir.SLOT_COUNT * ir.SLOT_SIZE)
        dist, samples = ir.parse_record(data[:0x808])
        rebuilt = ir.build_record(samples, round(dist * 100))
        self.assertEqual(rebuilt, data[:0x808])


if __name__ == "__main__":
    unittest.main()
