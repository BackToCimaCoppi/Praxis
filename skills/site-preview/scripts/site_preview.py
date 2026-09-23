#!/usr/bin/env python3
"""Manage the local source tree for a portable local review catalog."""

from __future__ import annotations

import argparse
import fcntl
import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import time
from urllib.parse import unquote, urlsplit
import uuid


SLUG = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
CSS_URL = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.I)
CSS_IMPORT = re.compile(r"@import\s+(?:url\()?\s*(['\"])(.*?)\1", re.I)
JS_IMPORT = re.compile(
    r"(?:from\s*|import\s*\(|require\s*\(|new\s+URL\s*\()(['\"])(\.{1,2}/[^'\"]+)\1"
)
SECRET_PARTS = re.compile(
    r"^(?:\.git|\.env(?:\..*)?|id_(?:rsa|dsa|ecdsa|ed25519)|credentials?|secrets?)$",
    re.I,
)
SECRET_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".kdb", ".sqlite", ".db"}


class AssetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.refs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value for key, value in attrs if value}
        for key in ("src", "poster"):
            if key in values:
                self.refs.append(values[key])
        if tag.lower() == "link" and "href" in values:
            self.refs.append(values["href"])
        if tag.lower() == "a" and "href" in values:
            path = urlsplit(values["href"]).path.lower()
            if path.endswith((".html", ".htm")):
                self.refs.append(values["href"])
        if "srcset" in values:
            for candidate in values["srcset"].split(","):
                value = candidate.strip().split(maxsplit=1)[0]
                if value:
                    self.refs.append(value)
        if "style" in values:
            self.refs.extend(match.group(2) for match in CSS_URL.finditer(values["style"]))


def workspace_path(raw: str) -> Path:
    path = Path(raw).expanduser().resolve()
    if path == Path("/") or path == Path.home():
        raise ValueError("workspace 不能是根目录或用户主目录")
    return path


def require_slug(value: str, label: str) -> str:
    if not SLUG.fullmatch(value):
        raise ValueError(f"{label} 必须以小写字母开头，且只含小写字母、数字和单连字符: {value}")
    return value


def paths(workspace: Path) -> tuple[Path, Path, Path]:
    return workspace / "content" / "catalog.json", workspace / "public" / "catalog", workspace / "public" / "previews"


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        Path(temp_name).unlink(missing_ok=True)
        raise


def empty_catalog() -> dict:
    return {"schema_version": 1, "items": []}


def load_catalog(workspace: Path) -> dict:
    catalog_file, _, _ = paths(workspace)
    if not catalog_file.exists():
        return empty_catalog()
    data = json.loads(catalog_file.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or not isinstance(data.get("items"), list):
        raise ValueError(f"目录格式不受支持: {catalog_file}")
    return data


def catalog_html(data: dict) -> str:
    items = sorted(data["items"], key=lambda item: item["updated_at"], reverse=True)
    cards = []
    for item in items:
        cards.append(
            '<a class="card" target="_top" href="{href}">'
            '<span class="eyebrow">{project} · {task}</span>'
            '<strong>{title}</strong><time>{updated}</time></a>'.format(
                href=html.escape(item["href"], quote=True),
                project=html.escape(item["project"]),
                task=html.escape(item["task"]),
                title=html.escape(item["title"]),
                updated=html.escape(item["updated_at"].replace("T", " ").replace("Z", " UTC")),
            )
        )
    body = "".join(cards) if cards else (
        '<section class="empty"><div>✓</div><h2>当前没有预览材料</h2>'
        '<p>固定入口已经保留。下次发布后，材料会出现在这里。</p></section>'
    )
    return f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>手机审阅站</title><style>
:root{{color-scheme:light dark;--bg:#f4f5f7;--panel:#fff;--text:#15171a;--muted:#68707c;--line:#e4e7eb;--accent:#ea4c89}}
@media(prefers-color-scheme:dark){{:root{{--bg:#0d0f12;--panel:#171a1f;--text:#f4f6f8;--muted:#a1a8b3;--line:#2b3038}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Helvetica Neue",sans-serif}}
main{{width:min(760px,100%);margin:auto;padding:calc(28px + env(safe-area-inset-top)) 18px calc(40px + env(safe-area-inset-bottom))}}
header{{padding:8px 2px 24px}}h1{{font-size:30px;letter-spacing:-.02em;margin:0 0 8px}}header p,.empty p{{color:var(--muted);margin:0;line-height:1.6}}
.grid{{display:grid;gap:12px}}.card{{display:flex;flex-direction:column;gap:8px;padding:18px;border:1px solid var(--line);border-radius:18px;background:var(--panel);color:inherit;text-decoration:none;box-shadow:0 6px 24px rgba(0,0,0,.05)}}
.card:active{{transform:scale(.99)}}.eyebrow,time{{font-size:12px;color:var(--muted)}}strong{{font-size:18px;line-height:1.4}}.empty{{padding:52px 24px;text-align:center;border:1px dashed var(--line);border-radius:20px;background:var(--panel)}}.empty div{{font-size:28px;color:var(--accent)}}.empty h2{{font-size:19px;margin:12px 0 8px}}
</style></head><body><main><header><h1>手机审阅站</h1><p>手机审阅用的临时材料目录。本地文件仍是正式真值。</p></header><section class="grid">{body}</section></main></body></html>'''


def wrapper_html(title: str, updated_at: str) -> str:
    safe_title = html.escape(title)
    safe_time = html.escape(updated_at)
    return f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><title>{safe_title}</title><style>
*{{box-sizing:border-box}}html,body{{margin:0;height:100%;overflow:hidden;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}}body{{display:flex;flex-direction:column;background:#f5f5f7}}
.bar{{height:48px;padding:env(safe-area-inset-top) 12px 0;flex:0 0 calc(48px + env(safe-area-inset-top));display:flex;align-items:center;gap:10px;background:rgba(250,250,252,.94);border-bottom:1px solid rgba(0,0,0,.1);backdrop-filter:blur(16px)}}
.back{{color:#b21f5b;text-decoration:none;font-weight:650;white-space:nowrap}}.meta{{min-width:0}}.title{{font-size:14px;font-weight:650;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}time{{display:block;font-size:10px;color:#737984}}iframe{{border:0;width:100%;flex:1;background:white}}
@media(prefers-color-scheme:dark){{body{{background:#111318}}.bar{{color:#f6f7f9;background:rgba(25,27,32,.94);border-color:rgba(255,255,255,.12)}}time{{color:#a7adb7}}}}
</style></head><body><header class="bar"><a class="back" href="/">‹ 目录</a><div class="meta"><div class="title">{safe_title}</div><time>{safe_time}</time></div></header><iframe src="content/index.html" title="{safe_title}"></iframe></body></html>'''


def save_catalog(workspace: Path, data: dict) -> None:
    catalog_file, catalog_dir, _ = paths(workspace)
    atomic_text(catalog_file, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    atomic_text(catalog_dir / "index.html", catalog_html(data))


def init_workspace(workspace: Path) -> None:
    _, _, previews = paths(workspace)
    previews.mkdir(parents=True, exist_ok=True)
    save_catalog(workspace, load_catalog(workspace))


def reject_sensitive(source: Path) -> None:
    for candidate in [source, *source.rglob("*")]:
        relative = candidate.relative_to(source) if candidate != source else Path(".")
        if candidate.is_symlink():
            raise ValueError(f"staging 不允许符号链接: {relative}")
        for part in relative.parts:
            if part.startswith(".") or SECRET_PARTS.fullmatch(part):
                raise ValueError(f"staging 含隐藏或敏感路径: {relative}")
        if candidate.is_file() and candidate.suffix.lower() in SECRET_SUFFIXES:
            raise ValueError(f"staging 含敏感文件类型: {relative}")


def local_ref(raw: str) -> str | None:
    value = raw.strip()
    if not value or value.startswith(("#", "data:", "mailto:", "tel:", "javascript:", "blob:")):
        return None
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc:
        return None
    return unquote(parsed.path) or None


def refs_for(path: Path) -> list[str]:
    suffix = path.suffix.lower()
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return []
    if suffix in {".html", ".htm"}:
        parser = AssetParser()
        parser.feed(text)
        parser.refs.extend(match.group(2) for match in CSS_URL.finditer(text))
        return parser.refs
    if suffix == ".css":
        return [match.group(2) for match in CSS_URL.finditer(text)] + [match.group(2) for match in CSS_IMPORT.finditer(text)]
    if suffix in {".js", ".mjs", ".cjs"}:
        return [match.group(2) for match in JS_IMPORT.finditer(text)]
    return []


def validate_staging(source: Path) -> None:
    if not source.is_dir():
        raise ValueError(f"staging 目录不存在: {source}")
    if not (source / "index.html").is_file():
        raise ValueError("staging 根目录必须包含 index.html")
    reject_sensitive(source)
    missing: list[str] = []
    for document in source.rglob("*"):
        if not document.is_file():
            continue
        for raw in refs_for(document):
            ref = local_ref(raw)
            if ref is None:
                continue
            target = (source / ref.lstrip("/")) if ref.startswith("/") else (document.parent / ref)
            target = target.resolve()
            try:
                target.relative_to(source.resolve())
            except ValueError:
                missing.append(f"{document.relative_to(source)} -> 越界路径 {raw}")
                continue
            if not target.exists():
                missing.append(f"{document.relative_to(source)} -> {raw}")
    if missing:
        raise ValueError("缺失或非法的本地依赖:\n- " + "\n- ".join(sorted(set(missing))))


def target_for(workspace: Path, project_slug: str, task_slug: str, material_slug: str) -> Path:
    _, _, previews = paths(workspace)
    return previews / project_slug / task_slug / material_slug


def upsert(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    source = Path(args.source_dir).expanduser().resolve()
    for value, label in ((args.project_slug, "project-slug"), (args.task_slug, "task-slug"), (args.material_slug, "material-slug")):
        require_slug(value, label)
    init_workspace(workspace)
    validate_staging(source)
    target = target_for(workspace, args.project_slug, args.task_slug, args.material_slug)
    if source == target or target in source.parents:
        raise ValueError("staging 不能位于目标材料目录内")
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_root = Path(tempfile.mkdtemp(prefix=".upsert-", dir=target.parent))
    prepared = temp_root / "material"
    backup: Path | None = None
    try:
        (prepared / "content").parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, prepared / "content")
        updated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        atomic_text(prepared / "index.html", wrapper_html(args.title, updated_at))
        if target.exists():
            backup = target.with_name(f".{target.name}.backup-{uuid.uuid4().hex}")
            os.replace(target, backup)
        os.replace(prepared, target)
        data = load_catalog(workspace)
        item_id = "/".join((args.project_slug, args.task_slug, args.material_slug))
        item = {
            "id": item_id,
            "project": args.project,
            "task": args.task,
            "title": args.title,
            "project_slug": args.project_slug,
            "task_slug": args.task_slug,
            "material_slug": args.material_slug,
            "kind": args.kind,
            "href": f"/previews/{item_id}/",
            "updated_at": updated_at,
        }
        data["items"] = [existing for existing in data["items"] if existing.get("id") != item_id] + [item]
        save_catalog(workspace, data)
        if backup:
            shutil.rmtree(backup)
        print(json.dumps(item, ensure_ascii=False))
    except Exception:
        if backup and backup.exists():
            if target.exists():
                shutil.rmtree(target)
            os.replace(backup, target)
        raise
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def remove_item(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    for value, label in ((args.project_slug, "project-slug"), (args.task_slug, "task-slug"), (args.material_slug, "material-slug")):
        require_slug(value, label)
    data = load_catalog(workspace)
    item_id = "/".join((args.project_slug, args.task_slug, args.material_slug))
    matches = [item for item in data["items"] if item.get("id") == item_id]
    if not matches:
        raise ValueError(f"材料不存在: {item_id}")
    target = target_for(workspace, args.project_slug, args.task_slug, args.material_slug)
    if target.exists():
        shutil.rmtree(target)
    data["items"] = [item for item in data["items"] if item.get("id") != item_id]
    save_catalog(workspace, data)
    print(json.dumps({"removed": item_id}, ensure_ascii=False))


def clear_all(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    data = load_catalog(workspace)
    count = len(data["items"])
    _, _, previews = paths(workspace)
    if previews.exists():
        shutil.rmtree(previews)
    previews.mkdir(parents=True, exist_ok=True)
    save_catalog(workspace, empty_catalog())
    print(json.dumps({"cleared": count}, ensure_ascii=False))


def list_items(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    print(json.dumps(load_catalog(workspace), ensure_ascii=False, indent=2))


def hold_lock(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    lock_path = workspace / ".site-preview.lock"
    deadline = time.monotonic() + args.wait_seconds
    with lock_path.open("a+", encoding="utf-8") as handle:
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise RuntimeError("LOCK_BUSY: 另一个会话正在更新审阅站")
                time.sleep(0.2)
        handle.seek(0)
        handle.truncate()
        handle.write(json.dumps({"pid": os.getpid(), "owner": args.owner, "acquired_at": time.time()}, ensure_ascii=False))
        handle.flush()
        print("LOCK_ACQUIRED", flush=True)
        for line in sys.stdin:
            if line.strip().lower() == "release":
                print("LOCK_RELEASED", flush=True)
                return


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("init", "list", "clear"):
        command = commands.add_parser(name)
        command.add_argument("--workspace", required=True)
    command = commands.add_parser("upsert")
    command.add_argument("--workspace", required=True)
    command.add_argument("--source-dir", required=True)
    command.add_argument("--project", required=True)
    command.add_argument("--task", required=True)
    command.add_argument("--title", required=True)
    command.add_argument("--project-slug", required=True)
    command.add_argument("--task-slug", required=True)
    command.add_argument("--material-slug", required=True)
    command.add_argument("--kind", choices=("html", "markdown", "design"), default="html")
    command = commands.add_parser("remove")
    command.add_argument("--workspace", required=True)
    command.add_argument("--project-slug", required=True)
    command.add_argument("--task-slug", required=True)
    command.add_argument("--material-slug", required=True)
    command = commands.add_parser("lock")
    command.add_argument("--workspace", required=True)
    command.add_argument("--owner", default="site-preview")
    command.add_argument("--wait-seconds", type=float, default=900)
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "init":
            workspace = workspace_path(args.workspace)
            init_workspace(workspace)
            print(workspace)
        elif args.command == "upsert":
            upsert(args)
        elif args.command == "list":
            list_items(args)
        elif args.command == "remove":
            remove_item(args)
        elif args.command == "clear":
            clear_all(args)
        elif args.command == "lock":
            hold_lock(args)
        return 0
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
