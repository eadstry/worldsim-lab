#!/usr/bin/env python3
"""Regenerate outputs/index.json and the index table in outputs/README.md.

The registry is derived from the sealed manifests under outputs/<artifact>/<version>/
plus the curated lifecycle metadata in config/outputs-status.json. Nothing here
modifies sealed artifacts; it only reads them.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
STATUS_FILE = ROOT / "config" / "outputs-status.json"
INDEX_FILE = OUTPUTS / "index.json"
README_FILE = OUTPUTS / "README.md"
START = "<!-- outputs-index:start -->"
END = "<!-- outputs-index:end -->"
BT = chr(96)
STATUS_ORDER = {"current": 0, "supporting": 1, "superseded": 2, "archived": 3}
STATUS_LABEL = {
    "current": "当前",
    "supporting": "支撑材料",
    "superseded": "已被取代",
    "archived": "归档",
}


def artifact_files(manifest):
    files = manifest["files"]
    if isinstance(files, dict):
        return list(files.keys())
    return [item["path"] for item in files]


def human_size(num):
    if num >= 1024 * 1024:
        return "%.1f MB" % (num / 1048576.0)
    return "%.0f KB" % (max(num, 0) / 1024.0)


def load_status():
    return json.loads(STATUS_FILE.read_text(encoding="utf-8"))["artifacts"]


def collect(status):
    errors = []
    artifacts = {}
    for manifest_path in sorted(OUTPUTS.glob("*/*/manifest.json")):
        version_dir = manifest_path.parent
        artifact_dir = version_dir.parent
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        artifact_id = manifest.get("artifact_id")
        version = manifest.get("version")
        rel = manifest_path.relative_to(ROOT).as_posix()
        if artifact_id != artifact_dir.name:
            errors.append("%s: artifact_id %r does not match directory %r" % (rel, artifact_id, artifact_dir.name))
        if version != version_dir.name:
            errors.append("%s: version %r does not match directory %r" % (rel, version, version_dir.name))
        names = artifact_files(manifest)
        missing = [name for name in names if not (version_dir / name).is_file()]
        if missing:
            errors.append("%s: %d sealed files missing, first: %s" % (rel, len(missing), missing[0]))
        size = sum((version_dir / name).stat().st_size for name in names if (version_dir / name).is_file())
        entry = artifacts.setdefault(artifact_id, {"id": artifact_id, "versions": []})
        entry["versions"].append({
            "version": version,
            "sealed_at": manifest.get("sealed_at", ""),
            "files": len(names),
            "bytes": size,
        })
    for artifact_id, entry in artifacts.items():
        meta = status.get(artifact_id)
        if meta is None:
            errors.append("outputs/%s: not registered in config/outputs-status.json" % artifact_id)
            continue
        entry["versions"].sort(key=lambda item: int(str(item["version"]).lstrip("v")))
        for index, item in enumerate(entry["versions"]):
            item["current"] = index == len(entry["versions"]) - 1
        entry.update({
            "title": meta["title"],
            "status": meta["status"],
            "supersedes": meta.get("supersedes", []),
            "superseded_by": meta.get("superseded_by"),
            "summary": meta.get("summary", ""),
            "delivery": meta.get("delivery", ""),
            "current_version": entry["versions"][-1]["version"],
        })
    for artifact_id in status:
        if artifact_id not in artifacts:
            errors.append("config/outputs-status.json: %s has no directory under outputs/" % artifact_id)
    return artifacts, errors


def ordered(artifacts):
    return sorted(artifacts.values(), key=lambda a: (STATUS_ORDER.get(a["status"], 9), a["id"]))


def render_index(items):
    payload = {
        "schema_version": 1,
        "artifact_count": len(items),
        "version_count": sum(len(a["versions"]) for a in items),
        "artifacts": [
            {
                "id": a["id"],
                "title": a["title"],
                "status": a["status"],
                "supersedes": a["supersedes"],
                "superseded_by": a["superseded_by"],
                "current_version": a["current_version"],
                "versions": a["versions"],
            }
            for a in items
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def entry_link(artifact_id, version):
    for name in ("index.html", "charts.html", "report.md", "README.md", "architecture.html",
                 "catalog.json", "manifest.json"):
        rel = "outputs/%s/%s/%s" % (artifact_id, version, name)
        if (ROOT / rel).is_file():
            return "[%s](%s)" % (version, rel[len("outputs/"):])
    return "[%s](%s/%s/)" % (version, artifact_id, version)


def render_section(items, status):
    lines = [START, ""]
    lines.append("| 主题 | 状态 | 版本 | 入口 | 内容与验证范围 | 已记录交付 |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for a in items:
        label = STATUS_LABEL.get(a["status"], a["status"])
        if a["status"] == "superseded" and a["superseded_by"]:
            label += "（→ %s）" % a["superseded_by"]
        total = sum(v["bytes"] for v in a["versions"])
        version_cell = "%s · %d 版 · %s" % (a["current_version"], len(a["versions"]), human_size(total))
        lines.append("| %s | %s | %s | %s | %s | %s |" % (
            a["title"], label, version_cell, entry_link(a["id"], a["current_version"]),
            a["summary"].replace("|", "/"), a["delivery"].replace("|", "/")))
    archived = []
    for artifact_id in sorted(status):
        for record in status[artifact_id].get("archived_versions", []):
            archived.append((artifact_id, record))
    if archived:
        lines.extend(["", "**已归档版本**（移出主树，原文与校验值保存在单独归档中，位置见仓库整理记录）：", ""])
        for artifact_id, record in archived:
            lines.append("- %s %s → [%s](%s)" % (
                BT + artifact_id + BT, record["versions"], record.get("archive", record.get("release", "归档记录")), record["url"]))
    lines.extend(["", END])
    return "\n".join(lines)


def render_readme(current, section):
    if START not in current or END not in current:
        raise SystemExit("outputs/README.md is missing the index markers")
    head = current.split(START)[0]
    tail = current.split(END, 1)[1]
    return head + section + tail


def current_text(path):
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail when generated files are out of date")
    args = parser.parse_args()

    status = load_status()
    artifacts, errors = collect(status)
    if errors:
        for error in errors:
            print("ERROR: " + error, file=sys.stderr)
        return 1

    items = ordered(artifacts)
    index_text = render_index(items)
    readme_text = render_readme(README_FILE.read_text(encoding="utf-8"), render_section(items, status))
    stale = []
    if current_text(INDEX_FILE) != index_text:
        stale.append("outputs/index.json")
    if current_text(README_FILE) != readme_text:
        stale.append("outputs/README.md")
    versions = sum(len(a["versions"]) for a in items)

    if args.check:
        if stale:
            print("out of date: " + ", ".join(stale), file=sys.stderr)
            print("run: python3 scripts/build-outputs-index.py", file=sys.stderr)
            return 1
        print("outputs index up to date: %d artifacts, %d versions" % (len(items), versions))
        return 0

    if stale:
        INDEX_FILE.write_text(index_text, encoding="utf-8")
        README_FILE.write_text(readme_text, encoding="utf-8")
    print("outputs index updated: %d artifacts, %d versions (%s)" % (
        len(items), versions, ", ".join(stale) if stale else "no change"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
