from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).parents[1] / "scripts" / "site_preview.py"


class SitePreviewTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.workspace = self.root / "site"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_cli(self, *args: str, expect: int = 0) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(expect, result.returncode, result.stderr)
        return result

    def stage(self, name: str, title: str = "V1") -> Path:
        source = self.root / name
        source.mkdir()
        (source / "style.css").write_text("body{color:#123}", encoding="utf-8")
        (source / "index.html").write_text(
            f'<!doctype html><link rel="stylesheet" href="style.css"><h1>{title}</h1>',
            encoding="utf-8",
        )
        return source

    def upsert(self, source: Path, material: str, title: str) -> dict:
        result = self.run_cli(
            "upsert", "--workspace", str(self.workspace), "--source-dir", str(source),
            "--project", "ExampleApp", "--task", "海报调整", "--title", title,
            "--project-slug", "example-app", "--task-slug", "poster", "--material-slug", material,
        )
        return json.loads(result.stdout)

    def test_upsert_update_and_clear_keep_stable_entry(self) -> None:
        original = self.stage("source-one")
        first = self.upsert(original, "design", "设计 V1")
        self.upsert(self.stage("source-two"), "plan", "方案")
        updated_source = self.stage("source-three", "V2")
        second = self.upsert(updated_source, "design", "设计 V2")

        self.assertEqual(first["href"], second["href"])
        catalog = json.loads(self.run_cli("list", "--workspace", str(self.workspace)).stdout)
        self.assertEqual(2, len(catalog["items"]))
        copied = self.workspace / "public/previews/example-app/poster/design/content/index.html"
        self.assertIn("V2", copied.read_text(encoding="utf-8"))
        self.assertTrue((original / "index.html").exists())

        cleared = json.loads(self.run_cli("clear", "--workspace", str(self.workspace)).stdout)
        self.assertEqual(2, cleared["cleared"])
        self.assertEqual([], json.loads(self.run_cli("list", "--workspace", str(self.workspace)).stdout)["items"])
        index = (self.workspace / "public/catalog/index.html").read_text(encoding="utf-8")
        self.assertIn("当前没有预览材料", index)
        self.assertTrue((original / "index.html").exists())

    def test_remove_only_selected_material(self) -> None:
        self.upsert(self.stage("source-one"), "design", "设计")
        self.upsert(self.stage("source-two"), "plan", "方案")
        self.run_cli(
            "remove", "--workspace", str(self.workspace), "--project-slug", "example-app",
            "--task-slug", "poster", "--material-slug", "design",
        )
        catalog = json.loads(self.run_cli("list", "--workspace", str(self.workspace)).stdout)
        self.assertEqual(["example-app/poster/plan"], [item["id"] for item in catalog["items"]])

    def test_rejects_missing_dependency_and_sensitive_file(self) -> None:
        missing = self.root / "missing"
        missing.mkdir()
        (missing / "index.html").write_text('<img src="lost.png">', encoding="utf-8")
        result = self.run_cli(
            "upsert", "--workspace", str(self.workspace), "--source-dir", str(missing),
            "--project", "临时预览", "--task", "测试", "--title", "缺图",
            "--project-slug", "temporary", "--task-slug", "test", "--material-slug", "missing",
            expect=2,
        )
        self.assertIn("lost.png", result.stderr)

        secret = self.stage("secret")
        (secret / ".env").write_text("TOKEN=x", encoding="utf-8")
        result = self.run_cli(
            "upsert", "--workspace", str(self.workspace), "--source-dir", str(secret),
            "--project", "临时预览", "--task", "测试", "--title", "敏感",
            "--project-slug", "temporary", "--task-slug", "test", "--material-slug", "secret",
            expect=2,
        )
        self.assertIn("敏感路径", result.stderr)

    def test_lock_blocks_second_writer_and_releases(self) -> None:
        first = subprocess.Popen(
            [sys.executable, str(SCRIPT), "lock", "--workspace", str(self.workspace), "--owner", "first"],
            text=True,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert first.stdout and first.stdin
        self.assertEqual("LOCK_ACQUIRED", first.stdout.readline().strip())
        blocked = self.run_cli(
            "lock", "--workspace", str(self.workspace), "--owner", "second", "--wait-seconds", "0.1",
            expect=2,
        )
        self.assertIn("LOCK_BUSY", blocked.stderr)
        first.stdin.write("release\n")
        first.stdin.flush()
        self.assertEqual("LOCK_RELEASED", first.stdout.readline().strip())
        self.assertEqual(0, first.wait(timeout=2))
        first.stdin.close()
        first.stdout.close()
        if first.stderr:
            first.stderr.close()


if __name__ == "__main__":
    unittest.main()
