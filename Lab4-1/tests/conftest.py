"""Real MongoDB fixtures and optional, read-only pytest result collection."""

from __future__ import annotations

import hashlib
import json
import platform
import re
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from importlib.metadata import version
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from survey_app.config import PROJECT_ROOT, SEED, Settings
from survey_app.db import SCHEMAS, create_client, initialize_schema, safe_test_database


PASSWORD = "Lab4pass123!"  # Synthetic test password; never a real user credential.
LOCAL_TIMEZONE = timezone(timedelta(hours=8))


def unique_username() -> str:
    return f"u_{uuid4().hex[:20]}"


def register_login(client: TestClient, username: str | None = None) -> dict:
    """Create a synthetic user, log this client in, and return the public user."""
    username = username or unique_username()
    payload = {"username": username, "password": PASSWORD}
    registered = client.post("/api/auth/register", json=payload)
    assert registered.status_code == 201
    user = registered.json()
    logged_in = client.post("/api/auth/login", json=payload)
    assert logged_in.status_code == 200
    assert logged_in.json()["id"] == user["id"]
    return user


def pytest_addoption(parser) -> None:
    parser.addoption("--evidence", action="store", default=None, metavar="FILE",
                     help="Save actual phase outcomes/environment/UUID database cleanup as JSON")


def pytest_configure(config) -> None:
    config._lab4_evidence = {
        "started_at": datetime.now(LOCAL_TIMEZONE).isoformat(),
        "timezone": "Asia/Shanghai", "seed": SEED,
        "selection": list(config.args), "records": [], "collection_errors": [],
        "database": None, "cleanup": {"status": "NOT_RUN", "reason": "database fixture not used"},
        "environment": {
            "python": platform.python_version(), "platform": platform.platform(),
            "pytest": version("pytest"), "fastapi": version("fastapi"),
            "pymongo": version("pymongo"), "httpx": version("httpx"),
        },
    }


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    cases = sorted({str(case) for marker in item.iter_markers("case") for case in marker.args})
    entry = {"nodeid": report.nodeid, "phase": report.when, "outcome": report.outcome,
             "duration": report.duration, "cases": cases}
    if call.excinfo is not None:
        entry["exception_type"] = call.excinfo.type.__name__
    # Deliberately do not capture raw locals, headers, cookies or driver exceptions.
    item.config._lab4_evidence["records"].append(entry)


@pytest.hookimpl(hookwrapper=True)
def pytest_make_collect_report(collector):
    result = yield
    report = result.get_result()
    if report.failed:
        collector.config._lab4_evidence["collection_errors"].append({
            "nodeid": report.nodeid, "phase": "collect", "outcome": report.outcome,
        })


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus) -> None:
    report = session.config._lab4_evidence
    report["finished_at"] = datetime.now(LOCAL_TIMEZONE).isoformat()
    report["exit_code"] = int(exitstatus)
    calls = Counter(entry["outcome"] for entry in report["records"] if entry["phase"] == "call")
    phase_counts = Counter(f"{entry['phase']}:{entry['outcome']}" for entry in report["records"])
    report["summary"] = {
        "collected": session.testscollected, "passed": calls["passed"], "failed": calls["failed"],
        "skipped": sum(entry["outcome"] == "skipped" for entry in report["records"]),
        "setup_teardown_errors": sum(entry["outcome"] == "failed" and entry["phase"] != "call" for entry in report["records"]),
        "session_tests_failed": session.testsfailed, "phase_outcomes": dict(phase_counts),
        "collection_errors": len(report["collection_errors"]),
    }
    sources = sorted((PROJECT_ROOT / "survey_app").rglob("*.py")) + sorted((PROJECT_ROOT / "tests").rglob("*.py"))
    report["source_sha256"] = {
        path.relative_to(PROJECT_ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sources
    }
    for relative in ("pytest.ini",):
        path = PROJECT_ROOT / relative
        if path.is_file():
            report["source_sha256"][relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    destination = session.config.getoption("evidence")
    if destination:
        output = Path(destination)
        if not output.is_absolute():
            output = PROJECT_ROOT / output
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists():
            suffix = datetime.now(LOCAL_TIMEZONE).strftime("%Y%m%dT%H%M%S%f")
            archive = output.with_name(f"{output.stem}-{suffix}{output.suffix}")
            archive.write_bytes(output.read_bytes())
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


@pytest.fixture(scope="session")
def settings(pytestconfig) -> Settings:
    defaults = Settings.from_env()
    name = f"lab4_test_api_{uuid4().hex}"
    assert safe_test_database(name)
    assert name != defaults.database
    pytestconfig._lab4_evidence["database"] = name
    return Settings(
        mongodb_uri=defaults.mongodb_uri, database=name,
        session_secret="synthetic-lab4-test-secret-" + str(SEED) * 4,
        cookie_secure=False, session_ttl_seconds=86400,
    )


@pytest.fixture(scope="session")
def db(settings, pytestconfig):
    name = settings.database
    assert safe_test_database(name) and re.fullmatch(r"lab4_test_api_[0-9a-f]{32}", name)
    client = create_client(settings)
    database = client[name]
    cleanup_allowed = False
    metadata = pytestconfig._lab4_evidence
    try:
        if database.list_collection_names():
            raise RuntimeError("UUID test database already contains collections; no modification or cleanup allowed")
        cleanup_allowed = True
        initialize_schema(database)
        hello = client.admin.command("hello")
        metadata["environment"].update({
            "mongodb": client.server_info()["version"], "replica_set": hello.get("setName"),
            "writable_primary": hello.get("isWritablePrimary", False),
            "read_preference": "primary", "tz_aware": True,
        })
        assert hello.get("setName") and hello.get("isWritablePrimary") is True
        yield database
    finally:
        try:
            if cleanup_allowed:
                if not safe_test_database(name) or not re.fullmatch(r"lab4_test_api_[0-9a-f]{32}", name):
                    raise RuntimeError("UUID database cleanup safety check failed")
                counts = {collection: database[collection].count_documents({}) for collection in SCHEMAS}
                client.drop_database(name)
                remaining = client[name].list_collection_names()
                metadata["cleanup"] = {
                    "status": "PASS" if not remaining else "FAIL", "database": name,
                    "counts_before_drop": counts, "remaining_collections": remaining,
                }
                assert not remaining
        except Exception as exc:
            metadata["cleanup"] = {"status": "FAIL", "database": name, "error_type": type(exc).__name__}
            raise RuntimeError("Exact UUID test database cleanup failed") from None
        finally:
            client.close()


@pytest.fixture(scope="session")
def app(settings, db):
    from survey_app.main import create_app

    application = create_app(settings)
    # Exactly one lifespan per test session. Other clients reuse its MongoDB state.
    with TestClient(application):
        assert application.state.db.name == db.name
        assert application.state.service is not None
        yield application


@pytest.fixture
def client_factory(app):
    @contextmanager
    def factory():
        instance = TestClient(app)
        try:
            yield instance
        finally:
            instance.close()
    return factory


@pytest.fixture
def client(client_factory):
    with client_factory() as instance:
        yield instance
