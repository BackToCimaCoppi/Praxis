#!/usr/bin/env python3
"""Discover local review bridges without exposing authentication details."""

import json
import re
import shutil
import subprocess
import sys


def run(args, timeout=35):
    return subprocess.run(args, stdin=subprocess.DEVNULL, text=True,
                          capture_output=True, timeout=timeout, check=False)


def entry(name, command):
    return {"bridge": name, "installed": bool(shutil.which(command)),
            "available": False, "models": [], "reason": ""}


def claude():
    result = entry("claude-code", "claude")
    if not result["installed"]:
        result["reason"] = "未安装 Claude Code CLI"
        return result
    try:
        auth = run(["claude", "auth", "status"])
        if auth.returncode or not json.loads(auth.stdout).get("loggedIn"):
            result["reason"] = "Claude Code 未登录或认证不可用"
            return result
        listing = run(["claude", "-p", "/model", "--output-format", "text",
                       "--no-session-persistence"], timeout=60)
        match = re.search(r"Available:\s*(.+?)(?:\.|$)", listing.stdout, re.S)
        if listing.returncode or not match:
            result["reason"] = "Claude Code 模型查询失败"
            return result
        names = [x.strip().strip('`') for x in re.split(r",|\bor\b", match.group(1))]
        result["models"] = [{"id": x, "display_name": x} for x in names
                            if x and x not in {"best", "default", "opusplan"}
                            and "fast" not in x.lower() and "full model ID" not in x]
    except (subprocess.TimeoutExpired, ValueError, OSError):
        result["reason"] = "Claude Code 模型查询超时或返回无法解析"
        return result
    result["available"] = bool(result["models"])
    return result


def cursor():
    result = entry("cursor", "agent")
    cursor_cli = shutil.which("agent") or shutil.which("cursor-agent")
    result["installed"] = bool(cursor_cli)
    if not result["installed"]:
        result["reason"] = "未安装 Cursor Agent CLI"
        return result
    try:
        auth = run([cursor_cli, "status"])
        if auth.returncode or "logged in" not in (auth.stdout + auth.stderr).lower():
            result["reason"] = "Cursor Agent 未登录或认证不可用"
            return result
        listing = run([cursor_cli, "models"])
        if listing.returncode:
            result["reason"] = "Cursor 模型查询失败"
            return result
        for line in listing.stdout.splitlines():
            match = re.match(r"^([\w.-]+)\s+-\s+(.+)$", line.strip())
            if match and match.group(1) != "auto" and "fast" not in match.group(1).lower() and "fast" not in match.group(2).lower():
                result["models"].append({"id": match.group(1), "display_name": match.group(2)})
    except (subprocess.TimeoutExpired, OSError):
        result["reason"] = "Cursor 模型查询超时或失败"
        return result
    result["available"] = bool(result["models"])
    return result


def codex():
    result = entry("codex", "codex")
    if not result["installed"]:
        result["reason"] = "未安装 Codex CLI"
        return result
    try:
        auth = run(["codex", "login", "status"])
        if auth.returncode or "logged in" not in (auth.stdout + auth.stderr).lower():
            result["reason"] = "Codex 未登录或认证不可用"
            return result
        import selectors
        requests = [
            {"id": 1, "method": "initialize", "params": {"clientInfo": {"name": "praxis-bridge-discovery", "version": "1.0"}, "capabilities": {}}},
            {"method": "initialized", "params": {}},
            {"id": 2, "method": "model/list", "params": {}}]
        process = subprocess.Popen(["codex", "app-server"], stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        buffer = b""
        def receive(target):
            nonlocal buffer
            while True:
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    try:
                        message = json.loads(line)
                    except ValueError:
                        continue
                    if message.get("id") == target:
                        return message
                if not selector.select(timeout=35):
                    raise subprocess.TimeoutExpired("codex app-server", 35)
                chunk = process.stdout.read1(65536)
                if not chunk:
                    raise ValueError("app-server closed before model/list")
                buffer += chunk
        try:
            process.stdin.write((json.dumps(requests[0]) + "\n").encode()); process.stdin.flush()
            receive(1)
            for request in requests[1:]:
                process.stdin.write((json.dumps(request) + "\n").encode()); process.stdin.flush()
            response = receive(2)
        finally:
            process.kill()
            process.wait(timeout=5)
        if not response:
            result["reason"] = "Codex 模型查询失败"
            return result
        for model in response.get("result", {}).get("data", []):
            model_id = model.get("model") or model.get("id")
            if model_id and not model.get("hidden") and "fast" not in model_id.lower():
                result["models"].append({"id": model_id,
                                         "display_name": model.get("displayName", model_id),
                                         "description": model.get("description", ""),
                                         "reasoning": [x.get("reasoningEffort") for x in model.get("supportedReasoningEfforts", [])]})
    except (subprocess.TimeoutExpired, ValueError, OSError):
        result["reason"] = "Codex 模型查询超时或返回无法解析"
        return result
    result["available"] = bool(result["models"])
    return result


def main():
    results = [claude(), cursor(), codex()]
    print(json.dumps({"bridges": results}, ensure_ascii=False, indent=2))
    return 0 if any(x["available"] for x in results) else 1


if __name__ == "__main__":
    sys.exit(main())
