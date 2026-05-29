from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@dataclass
class CheckResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    details: dict[str, object] = field(default_factory=dict)


def _path_from_env(env: Mapping[str, str], name: str, default: str) -> Path:
    return Path(env.get(name, default))


def _check_readable_file(errors: list[str], label: str, path: Path) -> None:
    if not path.exists():
        errors.append(f"{label} missing: {path}")
        return
    if not path.is_file():
        errors.append(f"{label} is not a file: {path}")
        return
    try:
        with path.open("rb"):
            pass
    except OSError as exc:
        errors.append(f"{label} unreadable: {path} ({exc})")


def _check_writable_file(errors: list[str], label: str, path: Path) -> None:
    if not path.exists():
        errors.append(f"{label} missing: {path}")
        return
    if not path.is_file():
        errors.append(f"{label} is not a file: {path}")
        return
    try:
        with path.open("a", encoding="utf-8"):
            pass
    except OSError as exc:
        errors.append(f"{label} not writable: {path} ({exc})")


def _check_log_path(errors: list[str], env: Mapping[str, str]) -> None:
    log_file = env.get("GMM_LOG_FILE")
    if not log_file:
        return
    log_path = Path(log_file)
    log_dir = log_path.parent
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8"):
            pass
    except OSError as exc:
        errors.append(f"GMM_LOG_FILE directory not writable: {log_dir} ({exc})")


def _route_details(env: Mapping[str, str]) -> dict[str, object]:
    previous = os.environ.copy()
    route_env = {
        "LINE_CHANNEL_ACCESS_TOKEN": "container-check-dummy",
        "LINE_CHANNEL_SECRET": "container-check-dummy",
        "MY_LINE_UID": "container-check-dummy",
        **env,
    }
    os.environ.update(route_env)
    try:
        from app import GmailMonitor, build_app_config_from_env

        cfg = build_app_config_from_env()
        monitor = GmailMonitor(cfg)
        routes = sorted(rule.rule for rule in monitor.app.url_map.iter_rules())
        with monitor.app.test_client() as client:
            health_status = client.get("/health").status_code
        return {"routes": routes, "health_status": health_status}
    finally:
        os.environ.clear()
        os.environ.update(previous)


def run_checks(
        env: Mapping[str, str] | None = None,
        check_routes: bool = True,
    ) -> CheckResult:
    check_env = dict(os.environ if env is None else env)
    errors: list[str] = []
    details: dict[str, object] = {}

    try:
        import app  # noqa: F401
        import gmm_server  # noqa: F401
        import google_service  # noqa: F401
        import line_webhook  # noqa: F401
        import extract_gmail_content  # noqa: F401
    except Exception as exc:
        errors.append(f"import failed: {exc}")
        return CheckResult(ok=False, errors=errors, details=details)

    creds_path = _path_from_env(check_env, "GMM_CREDS_PATH", "credentials.json")
    token_path = _path_from_env(check_env, "GMM_TOKEN_PATH", "token.json")
    filter_path = _path_from_env(check_env, "GMM_FILTER_PATH", "filters.json")

    _check_readable_file(errors, "GMM_CREDS_PATH", creds_path)
    _check_writable_file(errors, "GMM_TOKEN_PATH", token_path)
    _check_readable_file(errors, "GMM_FILTER_PATH", filter_path)
    _check_log_path(errors, check_env)

    if check_routes and not errors:
        try:
            details.update(_route_details(check_env))
            if details.get("health_status") != 200:
                errors.append(f"/health returned {details.get('health_status')}")
        except Exception as exc:
            errors.append(f"route check failed: {exc}")

    details.setdefault(
        "runtime_paths",
        {
            "credentials": str(creds_path),
            "token": str(token_path),
            "filters": str(filter_path),
            "log_file": check_env.get("GMM_LOG_FILE", ""),
        },
    )
    return CheckResult(ok=not errors, errors=errors, details=details)


def main() -> int:
    result = run_checks()
    if result.ok:
        print("container check: OK")
        for key, value in result.details.items():
            print(f"{key}: {value}")
        return 0

    print("container check: FAILED", file=sys.stderr)
    for error in result.errors:
        print(f"- {error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
