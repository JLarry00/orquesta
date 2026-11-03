"""Rendering of the protocol and skills."""
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from orq import render

# Words that must not reach the product. Private ones (names, companies…) are not kept in the repo: list them,
# one per line, in the git-ignored file `.forbidden-words` at the repo root, or comma-separated in
# ORQ_FORBIDDEN_WORDS. The v1 install path is always forbidden.
def _forbidden():
    words = ["~/.claude/orquesta"]
    f = Path(__file__).resolve().parent.parent / ".forbidden-words"
    if f.exists():
        words += [w.strip() for w in f.read_text().splitlines() if w.strip() and not w.startswith("#")]
    words += [w.strip() for w in os.environ.get("ORQ_FORBIDDEN_WORDS", "").split(",") if w.strip()]
    return re.compile("|".join(re.escape(w) for w in words), re.I)


FORBIDDEN = _forbidden()


class TestRender(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.env = mock.patch.dict(os.environ, {"HOME": str(self.home), "ORQ_HOME": str(self.home / ".orquesta")})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def all_texts(self, cfg):
        return [t for _, t in render.outputs(cfg)]

    def test_no_placeholders_or_company_words(self):
        for text in self.all_texts({"user": "Ana", "approver": "Luis", "max_alive": 3}):
            self.assertNotIn("{{", text)
            self.assertIsNone(FORBIDDEN.search(text), FORBIDDEN.search(text) and FORBIDDEN.search(text).group(0))

    def test_values(self):
        proto, launch, resume = self.all_texts({"user": "Ana", "approver": "Luis", "max_alive": 3})
        self.assertIn("y Ana puede escribirte", proto)
        self.assertIn("Luis lo aprobará", proto)
        self.assertIn("`~/.orquesta/bin/orq`", proto)
        self.assertIn("`SendMessage`", proto)
        self.assertIn("Tope de 3 agentes vivos", launch)
        self.assertIn("OK de Luis", launch)
        self.assertIn("Pone a Ana al día", resume)
        self.assertIn("el tope es `high`", launch)
        self.assertNotIn("`opus` / `xhigh`", launch)

    def test_approver_defaults_to_user(self):
        proto = render.protocol({"user": "Ana"})
        self.assertIn("Ana lo aprobará", proto)

    def test_house_rules(self):
        rules = self.home / "reglas.md"
        rules.write_text("- Regla uno.\n")
        cfg = {"user": "Ana", "house_rules": str(rules)}
        proto, launch, resume = self.all_texts(cfg)
        self.assertTrue(proto.endswith("## Reglas de la casa\n\n- Regla uno.\n"))
        self.assertIn("## 8. Reglas de la casa", launch)
        self.assertNotIn("Regla uno", resume)

    def test_missing_house_rules_is_an_error(self):
        with self.assertRaises(render.RenderError):
            render.protocol({"user": "Ana", "house_rules": str(self.home / "no.md")})

    def test_no_house_rules_leaves_no_trace(self):
        proto = render.protocol({"user": "Ana"})
        self.assertNotIn("Reglas de la casa", proto)
        self.assertTrue(proto.endswith("en lugar de una ventana.\n"))

    def test_skills_can_be_disabled(self):
        self.assertEqual(len(render.outputs({"user": "Ana", "skills": False})), 1)


if __name__ == "__main__":
    unittest.main()
