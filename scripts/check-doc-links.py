#!/usr/bin/env python3
"""Check relative Markdown links in the workspace.

Links into upstream submodules are skipped (their content is not part of this
repository), preserved partial snapshots under outputs/git-worktree-preservation/
are skipped, and links to versions listed as archived in config/outputs-status.json
count as satisfied because the archive lives in a GitHub Release.
"""
import json
import os
import posixpath
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
SKIP_SOURCES = ("outputs/git-worktree-preservation/",)
EXTERNAL = ("http://", "https://", "mailto:", "tel:", "#")


def git(*args):
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True)


def tracked_markdown():
    out = git("ls-files", "-z", "--", "*.md").stdout.decode()
    return [name for name in out.split("\0") if name]


def submodule_roots():
    out = git("config", "-f", ".gitmodules", "--get-regexp", r"^submodule\..*\.path$").stdout.decode()
    return {line.split(None, 1)[1].strip() for line in out.splitlines() if line.strip()}


def archived_versions():
    try:
        data = json.loads((ROOT / "config" / "outputs-status.json").read_text(encoding="utf-8"))
    except OSError:
        return {}
    archived = {}
    for artifact_id, meta in data["artifacts"].items():
        versions = set()
        for record in meta.get("archived_versions", []):
            span = record.get("versions", "")
            match = re.match(r"v(\d+)\s*[-–—]\s*v(\d+)$", span)
            if match:
                versions.update("v%03d" % number for number in range(int(match.group(1)), int(match.group(2)) + 1))
            elif re.match(r"v\d+$", span):
                versions.add(span)
        if versions:
            archived[artifact_id] = versions
    return archived


def check():
    roots = submodule_roots()
    archived = archived_versions()
    problems = []
    checked = 0
    for source in tracked_markdown():
        path = ROOT / source
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as error:
            problems.append("%s: cannot read (%s)" % (source, error))
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            for match in LINK.finditer(line):
                target = match.group(1)
                if target.startswith(EXTERNAL) or target.startswith("<"):
                    continue
                target = target.split("#", 1)[0]
                if not target:
                    continue
                checked += 1
                relative = unquote(target)
                resolved = posixpath.normpath(posixpath.join(posixpath.dirname(source), relative))
                if resolved.startswith(".."):
                    problems.append("%s:%d: link escapes the repository: %s" % (source, line_number, target))
                    continue
                parts = resolved.split("/")
                if parts and parts[0] in roots:
                    continue
                if any(source.startswith(prefix) for prefix in SKIP_SOURCES):
                    continue
                if not (ROOT / resolved).exists():
                    if len(parts) >= 3 and parts[0] == "outputs":
                        versions = archived.get(parts[1], set())
                        if parts[2] in versions:
                            continue
                    problems.append("%s:%d: missing %s" % (source, line_number, target))
    print("checked %d relative links in %d files" % (checked, len(tracked_markdown())))
    for problem in problems:
        print("ERROR: " + problem, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(check())
