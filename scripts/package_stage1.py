"""Build and verify a first-stage submission; never include runtime or secrets."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
CODE_BASELINE = "e7255c3332b3492691eff27a0a5ce7e395127422"
TOP_FILES = {
    ".env.example", ".gitignore", ".gitattributes", "AGENTS.md", "WORKFLOW.md",
    "README.md", "progress.json", "environment.yml", "pytest.ini",
    "大作业一第一阶段.docx",
}
TOP_DIRS = {"survey_app", "scripts", "tests", "docs", "references", "results"}
EXCLUDED_PARTS = {".git", ".runtime", "__pycache__", ".pytest_cache", ".venv", "dist"}
MANIFEST = "results/S7/manifest.json"
PROOF = "results/S7/package-check.json"
REQUIRED = {
    "README.md", "AGENTS.md", "WORKFLOW.md", "environment.yml", ".env.example",
    "progress.json", "大作业一第一阶段.docx", "survey_app/main.py", "survey_app/db.py",
    "docs/SYSTEM.md", "docs/DATABASE.md", "docs/API.md", "docs/LOGIC.md",
    "docs/REPORT_STAGE1.md", "docs/TEST_PLAN.md", "docs/TEST_REPORT.md",
    "docs/AI_USAGE.md", "docs/BASELINE_STAGE1.md", "docs/fixtures/statistics.json",
    "results/acceptance/reproduction-final.json", "results/S7/backup-restore.json",
    "results/S7/code-baseline.json",
}


def selected_files():
    selected = []
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
            selected.append((relative.as_posix(), path))
    return sorted(selected)


def local_secret_values():
    # Local files are read only to ensure their actual secret is absent from ZIP.
    values = []
    for env_file in [ROOT / ".env", ROOT / ".runtime/reproduction/project/.env"]:
        if env_file.is_file():
            for line in env_file.read_text(encoding="utf-8-sig").splitlines():
                key, sep, value = line.partition("=")
                if sep and key.strip() == "SESSION_SECRET" and len(value.strip()) >= 32:
                    values.append(value.strip().strip("\"'").encode())
    return values


def verify(archive, entries, secrets):
    with ZipFile(archive) as bundle:
        names = bundle.namelist()
        expected = {"Lab4/" + name for name, _ in entries} | {"Lab4/" + MANIFEST, "Lab4/" + PROOF}
        assert len(names) == len(set(names)) and set(names) == expected
        assert bundle.testzip() is None
        for name in names:
            relative = Path(name).relative_to("Lab4")
            assert ".." not in relative.parts
            assert not any(part in EXCLUDED_PARTS for part in relative.parts)
            assert relative.name != ".env"
            data = bundle.read(name)
            assert all(secret not in data for secret in secrets), "Local secret detected"
        manifest = json.loads(bundle.read("Lab4/" + MANIFEST))
        for row in manifest["files"]:
            data = bundle.read("Lab4/" + row["path"])
            assert len(data) == row["bytes"]
            assert hashlib.sha256(data).hexdigest() == row["sha256"]
        assert json.loads(bundle.read("Lab4/" + PROOF))["status"] == "PASS"
    return len(names)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="dist/Lab4-stage1.zip")
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
        "schema_version": 1,
        "created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "application_baseline_commit": CODE_BASELINE,
        "scope": "Exact submitted bytes; metadata may be newer than the tested application commit.",
        "self_exclusions": [MANIFEST, PROOF],
        "package_exclusions": [".env", ".runtime/", ".git/", "dist/", "cache/", "results/Lab4/"],
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
        "command": "python scripts/package_stage1.py",
        "scope": "ZIP integrity, exact manifest bytes, entries and actual local secret exclusion; no business tests run.",
        "manifest_file_count": len(entries), "zip_file_count": len(entries) + 2,
        "checks": ["unique safe Lab4 paths", "CRC", "all manifest SHA256 and byte counts",
                   "runtime/cache/credentials excluded", "actual local session secrets absent"],
        "exit_code": 0,
        "note": "This proof and manifest exclude their own hashes to avoid a circular digest. ZIP digest is in dist/*.sha256.",
    }
    proof_path.write_text(json.dumps(proof, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with ZipFile(archive, "w", compression=ZIP_DEFLATED) as bundle:
        for name, path in entries:
            bundle.write(path, "Lab4/" + name)
        bundle.write(destination, "Lab4/" + MANIFEST)
        bundle.write(proof_path, "Lab4/" + PROOF)
    # A failed verification never leaves a PASS proof behind.
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
