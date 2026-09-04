"""Verify the public read-only RiskCourt release contract without mutating state.

Only GET requests are issued.  Response bodies are parsed for the minimum
health and recorded-case predicates; credentials, IDs, and payloads are never
printed.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    passed: bool
    detail: str


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frontend-url", required=True, help="public frontend origin")
    parser.add_argument("--backend-url", required=True, help="public backend origin")
    parser.add_argument("--timeout", type=_positive_timeout, default=15.0)
    args = parser.parse_args(argv)

    frontend = args.frontend_url.rstrip("/")
    backend = args.backend_url.rstrip("/")
    checks: list[Check] = []
    frontend_body, _, frontend_status = _get(frontend, args.timeout)
    checks.append(
        Check(
            "frontend reachable",
            frontend_status == 200,
            f"HTTP {frontend_status}",
        )
    )
    if frontend_status == 200 and frontend_body is not None:
        checks.append(
            Check(
                "frontend is RiskCourt",
                "RiskCourt" in frontend_body,
                "title or app marker present" if "RiskCourt" in frontend_body else "marker missing",
            )
        )

    health_body, _, health_status = _get(f"{backend}/healthz", args.timeout)
    checks.append(Check("healthz reachable", health_status == 200, f"HTTP {health_status}"))
    health: dict[str, object] | None = None
    if health_status == 200 and health_body is not None:
        try:
            parsed = json.loads(health_body)
            health = parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            health = None
        checks.append(Check("healthz JSON", health is not None, "object response" if health else "invalid JSON"))
        if health is not None:
            safe_runtime = (
                health.get("ready") is True
                and health.get("recorded_fallback") is True
                and health.get("live_trading_enabled") is False
            )
            checks.append(
                Check(
                    "healthz fail-closed runtime",
                    safe_runtime,
                    "ready with recorded fallback and live trading disabled"
                    if safe_runtime
                    else "unsafe or unavailable readiness flags",
                )
            )

    cases_url = f"{backend}/api/recorded-cases"
    expected_origin = _origin(frontend)
    cases_body, cases_headers, cases_status = _get(
        cases_url, args.timeout, origin=expected_origin
    )
    checks.append(Check("recorded-case API reachable", cases_status == 200, f"HTTP {cases_status}"))
    cases: list[object] | None = None
    if cases_status == 200 and cases_body is not None:
        try:
            parsed_cases = json.loads(cases_body)
            cases = parsed_cases if isinstance(parsed_cases, list) else None
        except json.JSONDecodeError:
            cases = None
        checks.append(
            Check(
                "recorded-case payload",
                cases is not None and len(cases) > 0,
                f"{len(cases)} cases" if cases is not None else "invalid or empty payload",
            )
        )

    cors_ok = cases_headers.get("access-control-allow-origin") == expected_origin
    checks.append(
        Check(
            "exact CORS allowlist",
            cors_ok,
            "frontend origin allowed" if cors_ok else "frontend origin not allowed",
        )
    )

    report = {"passed": all(check.passed for check in checks), "checks": [asdict(c) for c in checks]}
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


def _get(
    url: str, timeout: float, *, origin: str | None = None
) -> tuple[str | None, dict[str, str], int]:
    headers = {"Accept": "application/json,text/html"}
    if origin:
        headers["Origin"] = origin
    request = Request(url, method="GET", headers=headers)
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            return body, dict(response.headers.items()), response.status
    except HTTPError as error:
        return None, dict(error.headers.items()), error.code
    except (URLError, TimeoutError, OSError):
        return None, {}, 0


def _origin(url: str) -> str:
    parsed = urlsplit(url)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def _positive_timeout(value: str) -> float:
    try:
        timeout = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("timeout must be a number") from error
    if not math.isfinite(timeout) or timeout <= 0:
        raise argparse.ArgumentTypeError("timeout must be a positive finite number")
    return timeout


if __name__ == "__main__":
    raise SystemExit(main())
