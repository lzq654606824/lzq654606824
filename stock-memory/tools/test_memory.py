"""运行：python3 -m unittest discover -s tools（在 stock-memory/ 目录下）。"""
from __future__ import annotations

import io
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import memory  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent


class MemoryLibraryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        shutil.copytree(REPO_ROOT / "templates", self.root / "templates")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_cli(self, *argv: str):
        out = io.StringIO()
        with redirect_stdout(out):
            code = memory.main(["--root", str(self.root), *argv])
        return code, out.getvalue()

    def new(self, *argv: str) -> Path:
        code, out = self.run_cli("new", *argv)
        self.assertEqual(code, 0, out)
        return self.root / out.splitlines()[0]

    def find_ids(self, *argv: str):
        code, out = self.run_cli("find", "--paths", *argv)
        self.assertEqual(code, 0, out)
        ids = []
        for rel in out.split():
            meta, _ = memory.parse_frontmatter((self.root / rel).read_text(encoding="utf-8"))
            ids.append(meta["title"])
        return ids

    def test_new_writes_frontmatter_and_template_body(self):
        path = self.new(
            "note", "--title", "尾盘: 放量", "--date", "2026-11-05",
            "--symbols", "600519.sh", "--tags", "白酒,量价/放量", "--source", "self",
        )
        self.assertEqual(path.relative_to(self.root).parts[:2], ("notes", "2026"))
        self.assertTrue(path.name.startswith("2026-11-05-"))
        meta, body = memory.parse_frontmatter(path.read_text(encoding="utf-8"))
        self.assertEqual(meta["title"], "尾盘: 放量")
        self.assertEqual(meta["symbols"], ["600519.SH"])
        self.assertEqual(meta["tags"], ["白酒", "量价/放量"])
        self.assertTrue(str(meta["id"]).startswith("N-"))
        self.assertTrue(str(meta["created"]).endswith("+08:00"))
        self.assertIn("## 看到了什么", body)
        self.assertEqual(self.run_cli("check")[0], 0)

    def test_new_reports_missing_fields_and_check_fails(self):
        code, out = self.run_cli("new", "review", "--title", "未填方向", "--symbols", "00700.HK")
        self.assertEqual(code, 0)
        self.assertIn("待补全：缺少必填字段 direction", out)
        code, out = self.run_cli("check")
        self.assertEqual(code, 1)
        self.assertIn("缺少必填字段 result", out)

    def test_find_by_symbol_time_tag_and_text(self):
        self.new("note", "--title", "A", "--date", "2026-10-08", "--symbols", "600519.SH",
                 "--tags", "白酒", "--source", "news")
        self.new("review", "--title", "B", "--date", "2026-11-03", "--symbols", "600519.SH,000858.SZ",
                 "--tags", "白酒/高端", "--direction", "long", "--opened", "2026-10-20",
                 "--closed", "2026-11-03", "--result", "loss", "--pnl-pct", "-3.5")
        self.new("lead", "--title", "C 关注回购", "--date", "2026-11-05", "--symbols", "00700.HK",
                 "--tags", "回购", "--source", "announcement", "--review-on", "2000-01-01")

        self.assertEqual(self.find_ids("--symbol", "600519"), ["B", "A"])
        self.assertEqual(self.find_ids("--tag", "白酒"), ["B", "A"])
        self.assertEqual(self.find_ids("--tag", "白酒/高端"), ["B"])
        self.assertEqual(self.find_ids("--from", "2026-11-01", "--to", "2026-11-04"), ["B"])
        self.assertEqual(self.find_ids("--type", "review", "--result", "loss"), ["B"])
        self.assertEqual(self.find_ids("--source", "announcement"), ["C 关注回购"])
        self.assertEqual(self.find_ids("--due"), ["C 关注回购"])
        self.assertEqual(self.find_ids("--text", "回购"), ["C 关注回购"])
        self.assertEqual(self.run_cli("check")[0], 0)

        code, out = self.run_cli("tags")
        self.assertIn("回购", out)
        code, out = self.run_cli("symbols")
        self.assertIn("   2  600519.SH", out)

    def test_check_flags_bad_review_and_duplicate_id(self):
        folder = self.root / "reviews" / "2026"
        folder.mkdir(parents=True)
        content = (
            "---\nid: R-20261106-1000\ntype: review\ntitle: x\ndate: 2026-11-06\n"
            "created: 2026-11-06T10:00:00+08:00\nsymbols:\n  - 600519.SH\ntags: []\nsource: self\n"
            "direction: long\nopened: 2026-11-01\nresult: win\n---\n"
        )
        (folder / "2026-11-06-a.md").write_text(content, encoding="utf-8")
        (folder / "2026-11-06-b.md").write_text(content, encoding="utf-8")
        code, out = self.run_cli("check")
        self.assertEqual(code, 1)
        self.assertIn("必须填 closed", out)
        self.assertIn("重复", out)

    def test_templates_parse(self):
        for name in ("note", "review", "lead"):
            meta, body = memory.parse_frontmatter((REPO_ROOT / "templates" / f"{name}.md").read_text(encoding="utf-8"))
            self.assertEqual(meta["type"], name)
            self.assertEqual(meta["symbols"], [])
            self.assertTrue(body.strip().startswith("##"))


if __name__ == "__main__":
    unittest.main()
