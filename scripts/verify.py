"""Run the credential-free repository verification contract."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"


@dataclass(frozen=True)
class StepResult:
    name: str
    command: tuple[str, ...]
    passed: bool
    exit_code: int


def executable(name: str) -> str:
    if sys.platform == "win32" and name == "npm":
        return shutil.which("npm.cmd") or "npm.cmd"
    return shutil.which(name) or name


def backend_python() -> str:
    candidates = (
        BACKEND / ".venv" / "Scripts" / "python.exe",
        BACKEND / ".venv" / "bin" / "python",
    )
    return next((str(path) for path in candidates if path.is_file()), sys.executable)


def run_step(name: str, command: list[str], cwd: Path) -> StepResult:
    print(f"==> {name}: {' '.join(command)}")
    completed = subprocess.run(command, cwd=cwd, check=False)
    result = StepResult(name, tuple(command), completed.returncode == 0, completed.returncode)
    print(f"<== {name}: {'PASS' if result.passed else 'FAIL'} ({result.exit_code})")
    return result


def secret_scan() -> StepResult:
    patterns = (
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        re.compile(r"AKIA[0-9A-Z]{16}"),
        re.compile(r"(?i)(?:api[_-]?key|secret[_-]?key)\s*[:=]\s*[A-Za-z0-9_\-/+=]{20,}"),
    )
    tracked = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout.decode("utf-8").split("\0")
    findings: list[str] = []
    for relative in tracked:
        if not relative or relative.endswith(".env.example"):
            continue
        path = ROOT / relative
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if any(pattern.search(text) for pattern in patterns):
            findings.append(relative)
    passed = not findings
    print(f"==> secret scan: {'PASS' if passed else 'FAIL'}")
    if findings:
        print("Potential secret patterns found in: " + ", ".join(findings))
    return StepResult("secret scan", ("git", "ls-files", "-z"), passed, 0 if passed else 1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-e2e",
        action="store_true",
        help="skip the browser run when Chromium is unavailable; CI runs it by default",
    )
    args = parser.parse_args()

    python = backend_python()
    npm = executable("npm")
    steps: list[StepResult] = [
        run_step("backend lint", [python, "-m", "ruff", "check", "src", "tests"], BACKEND),
        run_step("backend types", [python, "-m", "mypy", "src", "tests"], BACKEND),
        run_step("backend tests and fixture validation", [python, "-m", "pytest"], BACKEND),
        run_step("frontend lint", [npm, "run", "lint"], FRONTEND),
        run_step("frontend types", [npm, "run", "typecheck"], FRONTEND),
        run_step("frontend tests", [npm, "run", "test"], FRONTEND),
        run_step("frontend build", [npm, "run", "build"], FRONTEND),
        run_step("frontend format", [npm, "run", "format:check"], FRONTEND),
        secret_scan(),
    ]
    if not args.skip_e2e:
        steps.append(run_step("recorded browser E2E", [npm, "run", "e2e"], FRONTEND))

    report = {
        "passed": all(step.passed for step in steps),
        "steps": [asdict(step) for step in steps],
    }
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
