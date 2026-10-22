"""Build and verify the second-stage submission package.

Layout matches the repository: AGENTS.md, WORKFLOW.md and README.md at the archive root and the
second-stage project under `Lab4-2/`. Runtime state, secrets and build output are never included.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from zoneinfo import ZoneInfo

STAGE = "Lab4-2"
ROOT = Path(__file__).resolve().parents[1]      # Lab4/Lab4-2
SHARED_ROOT = ROOT.parent                        # Lab4/
SHARED_FILES = ("AGENTS.md", "WORKFLOW.md", "README.md")
TOP_FILES = {
    ".env.example", ".gitignore", ".gitattributes", "progress.json", "environment.yml",
    "pytest.ini", "大作业一：需求变更.docx",
}
TOP_DIRS = {"survey_app", "scripts", "tests", "docs", "references", "results"}
EXCLUDED_PARTS = {".git", ".runtime", "__pycache__", ".pytest_cache", ".venv", "dist"}
MANIFEST = "results/stage2/manifest.json"
PROOF = "results/stage2/package-check.json"
REQUIRED = {
    "AGENTS.md", "WORKFLOW.md", "README.md",
    "Lab4-2/progress.json", "Lab4-2/environment.yml", "Lab4-2/.env.example",
    "Lab4-2/大作业一：需求变更.docx", "Lab4-2/survey_app/main.py", "Lab4-2/survey_app/db.py",
    "Lab4-2/survey_app/library.py", "Lab4-2/survey_app/templates/library.html",
    "Lab4-2/survey_app/static/library.js",
    "Lab4-2/docs/REQUIREMENTS.md", "Lab4-2/docs/DECISIONS.md", "Lab4-2/docs/DATABASE.md",
    "Lab4-2/docs/API.md", "Lab4-2/docs/LOGIC.md", "Lab4-2/docs/SYSTEM.md",
    "Lab4-2/docs/TEST_PLAN.md", "Lab4-2/docs/TEST_REPORT.md", "Lab4-2/docs/REPORT_STAGE2.md",
    "Lab4-2/docs/AI_USAGE.md", "Lab4-2/docs/EXPERIMENT_LOG.md",
    "Lab4-2/results/stage2/http-e2e.json", "Lab4-2/results/stage2/pytest.json",
    "Lab4-2/results/stage2/schema-check.json", "Lab4-2/results/stage2/migration.json",
}


def selected_files():
    selected = []
    for name in SHARED_FILES:
        path = SHARED_ROOT / name
        if not path.is_file():
            raise RuntimeError(f"Missing shared document: {SHARED_ROOT.name}/{name}")
        selected.append((name, path))
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        if relative.parts[:2] == ("results", "Lab4"):
            continue
        if path.name == ".env" or path.suffix in {".pyc", ".pyo"}:
            continue
        if relative.as_posix() in {MANIFEST, PROOF}:
            continue
        if ((len(relative.parts) == 1 and path.name in TOP_FILES)
                or (len(relative.parts) > 1 and relative.parts[0] in TOP_DIRS)):
            if path.is_symlink():
                raise RuntimeError("Submission must not follow symbolic links")
            selected.append((f"{STAGE}/{relative.as_posix()}", path))
    return sorted(selected)


def local_secret_values():
    values = []
    env_file = ROOT / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8-sig").splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() == "SESSION_SECRET" and len(value.strip()) >= 32:
                values.append(value.strip().strip("\"'").encode())
    return values


def verify(archive, entries, secrets):
    with ZipFile(archive) as bundle:
        names = bundle.namelist()
        expected = {name for name, _ in entries} | {f"{STAGE}/{MANIFEST}", f"{STAGE}/{PROOF}"}
        assert len(names) == len(set(names)) and set(names) == expected
        assert bundle.testzip() is None
        for name in names:
            relative = Path(name)
            assert ".." not in relative.parts
            assert not any(part in EXCLUDED_PARTS for part in relative.parts)
            assert relative.name != ".env"
            data = bundle.read(name)
            assert all(secret not in data for secret in secrets), "Local secret detected"
        manifest = json.loads(bundle.read(f"{STAGE}/{MANIFEST}"))
        for row in manifest["files"]:
            data = bundle.read(row["path"])
            assert len(data) == row["bytes"]
            assert hashlib.sha256(data).hexdigest() == row["sha256"]
        assert json.loads(bundle.read(f"{STAGE}/{PROOF}"))["status"] == "PASS"
    return len(names)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="dist/Lab4-stage2.zip")
    args = parser.parse_args()
    archive = (ROOT / args.output).resolve()
    if not archive.is_relative_to((ROOT / "dist").resolve()) or archive.suffix != ".zip":
        parser.error("Output must be a .zip inside this project's dist directory")
    archive.parent.mkdir(parents=True, exist_ok=True)
    entries = selected_files()
    missing = REQUIRED - {name for name, _ in entries}
    if missing:
        raise RuntimeError("Missing required submission files: " + ", ".join(sorted(missing)))
    manifest = {
        "schema_version": 2,
        "created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "layout": "shared governance documents at archive root; second stage under Lab4-2/",
        "scope": "Exact submitted bytes for the second stage; first stage ships separately.",
        "self_exclusions": [MANIFEST, PROOF],
        "package_exclusions": [".env", ".runtime/", ".git/", "dist/", "cache/"],
        "files": [{"path": name, "bytes": path.stat().st_size,
                   "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                  for name, path in entries],
    }
    destination = ROOT / MANIFEST
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    proof_path = ROOT / PROOF
    proof = {
        "status": "PASS", "time": manifest["created_at"],
        "command": "python scripts/package_stage2.py",
        "scope": "ZIP integrity, exact manifest bytes, entries and actual local secret exclusion; no business tests run.",
        "manifest_file_count": len(entries), "zip_file_count": len(entries) + 2,
        "checks": ["unique safe archive paths", "CRC", "all manifest SHA256 and byte counts",
                   "runtime/cache/credentials excluded", "actual local session secrets absent"],
        "exit_code": 0,
        "note": "This proof and manifest exclude their own hashes to avoid a circular digest. ZIP digest is in dist/*.sha256.",
    }
    proof_path.write_text(json.dumps(proof, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with ZipFile(archive, "w", compression=ZIP_DEFLATED) as bundle:
        for name, path in entries:
            bundle.write(path, name)
        bundle.write(destination, f"{STAGE}/{MANIFEST}")
        bundle.write(proof_path, f"{STAGE}/{PROOF}")
    try:
        count = verify(archive, entries, local_secret_values())
    except BaseException:
        proof["status"] = "FAIL"
        proof["exit_code"] = 1
        proof_path.write_text(json.dumps(proof, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        raise
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix(".zip.sha256").write_text(checksum + "  " + archive.name + "\n", encoding="ascii")
    print(json.dumps({"status": "PASS", "files": count, "zip": args.output,
                      "bytes": archive.stat().st_size, "sha256": checksum}))


if __name__ == "__main__":
    main()
