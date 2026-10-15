"""Garante que todo texto mostrado na interface tem tradução para o inglês."""
import ast
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cubebaby import i18n  # noqa: E402
from cubebaby.model import SWITCHES  # noqa: E402

PKG = os.path.join(os.path.dirname(__file__), "..", "cubebaby")
# Funções/métodos que recebem texto em português (posição do argumento traduzível).
TEXT_ARGS = {"T": [0], "_msg": [0], "_confirm": [0, 1], "_tr": [2], "_write_ir_image": [1]}


def _strings(node):
    """Constantes de texto de um argumento (inclui os dois lados de `a if cond else b`)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.IfExp):
        return _strings(node.body) + _strings(node.orelse)
    return []


def collect_ui_texts():
    texts = set()
    for name in os.listdir(PKG):
        if not name.endswith(".py") or name == "i18n.py":
            continue
        with open(os.path.join(PKG, name), encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            fname = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None
            for pos in TEXT_ARGS.get(fname, []):
                if pos < len(node.args):
                    texts.update(_strings(node.args[pos]))
            for kw in node.keywords:
                if kw.arg == "label":
                    texts.update(_strings(kw.value))
    texts.update(name for name, _off, _params in SWITCHES)
    return texts


class Translations(unittest.TestCase):
    def test_every_ui_text_has_english(self):
        texts = collect_ui_texts()
        self.assertGreater(len(texts), 50)
        missing = sorted(t for t in texts if t not in i18n.EN)
        self.assertEqual(missing, [], "Textos sem tradução em i18n.EN")

    def test_placeholders_match(self):
        import string
        fields = lambda s: {f for _, f, _, _ in string.Formatter().parse(s) if f}
        for pt, en in i18n.EN.items():
            self.assertEqual(fields(pt), fields(en), pt)

    def test_switch_and_fallback(self):
        try:
            i18n.set_language("en")
            self.assertEqual(i18n.T("Ferramentas"), "Tools")
            self.assertEqual(i18n.T("Gravando IR no slot {n}…", n=3), "Writing IR to slot 3…")
            self.assertEqual(i18n.T("texto sem tradução"), "texto sem tradução")
            i18n.set_language("pt")
            self.assertEqual(i18n.T("Ferramentas"), "Ferramentas")
        finally:
            i18n.set_language("pt")


if __name__ == "__main__":
    unittest.main()
