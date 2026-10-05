"""Opt-in, serial local scheduler for scan-only RiskCourt workstation runs.

The helper accepts only loopback HTTP destinations and SPY/QQQ. It never calls
an order endpoint, refuses redirects, bounds response sizes and network waits,
and retries failures with a capped backoff.
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import signal
import sqlite3
import tempfile
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

MAX_RESPONSE_BYTES = 1_000_000
MAX_TIMEOUT_SECONDS = 120.0
MAX_RETRIES = 5
MAX_BACKOFF_SECONDS = 30.0
MAX_INTERVAL_MINUTES = 24 * 60
ALLOWED_SYMBOLS = frozenset({"SPY", "QQQ"})
LOCK_DIRECTORY = Path(tempfile.gettempdir()) / "riskcourt" / "scheduler-locks"


class _DenyRedirects(HTTPRedirectHandler):
    def redirect_request(self, *_: object, **__: object) -> None:
        return None


class SchedulerAlreadyRunning(RuntimeError):
    """Raised when another scheduler owns the lock for this local API origin."""


class SchedulerInstanceLock:
    """Hold an OS-level per-origin lock for one scheduler process."""

    def __init__(self, base_url: str, lock_directory: Path = LOCK_DIRECTORY) -> None:
        origin = validate_base_url(base_url)
        digest = hashlib.sha256(origin.encode("utf-8")).hexdigest()
        self.path = lock_directory / f"{digest}.sqlite3"
        self._connection: sqlite3.Connection | None = None

    def acquire(self) -> None:
        if self._connection is not None:
            raise RuntimeError("scheduler lock is already held by this instance")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=0, isolation_level=None)
        try:
            connection.execute("BEGIN EXCLUSIVE")
        except sqlite3.OperationalError as error:
            connection.close()
            if "locked" in str(error).casefold() or "busy" in str(error).casefold():
                raise SchedulerAlreadyRunning from None
            raise
        self._connection = connection

    def release(self) -> None:
        connection, self._connection = self._connection, None
        if connection is None:
            return
        try:
            connection.rollback()
        finally:
            connection.close()

    def __enter__(self) -> SchedulerInstanceLock:
        self.acquire()
        return self

    def __exit__(self, *_: object) -> None:
        self.release()


@contextmanager
def _shutdown_handlers(stop_event: threading.Event) -> Iterator[None]:
    """Temporarily turn common termination signals into a cooperative stop."""

    previous: dict[signal.Signals, object] = {}

    def request_stop(_signum: int, _frame: object) -> None:
        stop_event.set()

    handled_signals = [signal.SIGINT, signal.SIGTERM]
    if hasattr(signal, "SIGBREAK"):
        handled_signals.append(signal.SIGBREAK)
    try:
        for signum in handled_signals:
            previous[signum] = signal.signal(signum, request_stop)
    except ValueError as error:
        for signum, handler in previous.items():
            signal.signal(signum, cast(signal.Handlers, handler))
        raise RuntimeError("scheduler signal handling requires the main thread") from error
    try:
        yield
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, cast(signal.Handlers, handler))


def validate_base_url(base_url: str) -> str:
    """Return a canonical loopback HTTP origin; reject every other URL form."""

    if "\\" in base_url:
        raise ValueError("scheduler destination must be a local HTTP origin")
    try:
        parsed = urlsplit(base_url)
        host = parsed.hostname
        port = parsed.port
    except ValueError as error:
        raise ValueError("scheduler destination must be a local HTTP origin") from error
    if (
        parsed.scheme != "http"
        or host is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("scheduler destination must be a local HTTP origin")
    if host.lower() != "localhost":
        try:
            if not ipaddress.ip_address(host).is_loopback:
                raise ValueError("scheduler destination must be loopback")
        except ValueError as error:
            if str(error) == "scheduler destination must be loopback":
                raise
            raise ValueError("scheduler destination must be loopback") from error
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("scheduler destination port is invalid")
    authority = f"[{host.lower()}]" if ":" in host else host.lower()
    if port is not None:
        authority = f"{authority}:{port}"
    return f"http://{authority}"


def scan_once(base_url: str, symbols: Sequence[str], timeout: float) -> dict[str, object]:
    origin = validate_base_url(base_url)
    normalized_symbols = tuple(symbol.upper() for symbol in symbols)
    if not normalized_symbols or any(
        symbol not in ALLOWED_SYMBOLS for symbol in normalized_symbols
    ):
        raise ValueError("scheduler supports SPY and QQQ only")
    if len(set(normalized_symbols)) != len(normalized_symbols):
        raise ValueError("scheduler symbols must be unique")
    if not 0 < timeout <= MAX_TIMEOUT_SECONDS:
        raise ValueError("scheduler timeout must be between 0 and 120 seconds")

    payload = json.dumps({"symbols": list(normalized_symbols)}).encode("utf-8")
    request = Request(
        f"{origin}/api/scans",
        data=payload,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method="POST",
    )
    opener = build_opener(_DenyRedirects)
    with opener.open(request, timeout=timeout) as response:  # nosec B310 - URL is validated loopback
        raw = response.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("local scan response exceeded its size limit")
    result = json.loads(raw.decode("utf-8"))
    if not isinstance(result, dict):
        raise ValueError("local scan response must be an object")
    return result


def _bounded_float(value: str, *, minimum: float, maximum: float, name: str) -> float:
    try:
        parsed = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"{name} must be a number") from error
    if not minimum <= parsed <= maximum:
        raise argparse.ArgumentTypeError(f"{name} must be between {minimum:g} and {maximum:g}")
    return parsed


def _timeout(value: str) -> float:
    return _bounded_float(value, minimum=0.1, maximum=MAX_TIMEOUT_SECONDS, name="timeout")


def _interval(value: str) -> float:
    return _bounded_float(value, minimum=1, maximum=MAX_INTERVAL_MINUTES, name="interval-minutes")


def _backoff(value: str) -> float:
    return _bounded_float(value, minimum=0, maximum=MAX_BACKOFF_SECONDS, name="backoff-seconds")


def _nonnegative_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("retries must be an integer") from error
    if not 0 <= parsed <= MAX_RETRIES:
        raise argparse.ArgumentTypeError("retries must be between 0 and 5")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enable", action="store_true", help="explicitly enable scheduled scans")
    parser.add_argument("--once", action="store_true", help="run one scan and exit")
    parser.add_argument(
        "--interval-minutes",
        type=_interval,
        default=None,
        help="repeat interval from 1 minute to 24 hours; required unless --once is set",
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=_timeout, default=30.0)
    parser.add_argument("--retries", type=_nonnegative_int, default=2)
    parser.add_argument("--backoff-seconds", type=_backoff, default=1.0)
    parser.add_argument(
        "--symbols", nargs="+", choices=sorted(ALLOWED_SYMBOLS), default=["SPY", "QQQ"]
    )
    return parser


def _scan_with_retry(
    args: argparse.Namespace, stop_event: threading.Event | None = None
) -> tuple[dict[str, object] | None, int]:
    event = stop_event or threading.Event()
    for attempt in range(args.retries + 1):
        if event.is_set():
            return None, attempt
        try:
            return scan_once(args.base_url, args.symbols, args.timeout), attempt + 1
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, UnicodeError):
            if attempt >= args.retries:
                return None, attempt + 1
            delay = min(args.backoff_seconds * (2**attempt), MAX_BACKOFF_SECONDS)
            if delay and event.wait(delay):
                return None, attempt + 1
    return None, args.retries + 1


def _run_scheduler(args: argparse.Namespace, stop_event: threading.Event) -> int:
    with SchedulerInstanceLock(args.base_url), _shutdown_handlers(stop_event):
        while not stop_event.is_set():
            result, attempts = _scan_with_retry(args, stop_event)
            if stop_event.is_set():
                return 0
            if result is None:
                print(
                    json.dumps(
                        {
                            "status": "scan_failed",
                            "attempts": attempts,
                            "reason": "local_api_unavailable",
                        },
                        sort_keys=True,
                    )
                )
                if args.once:
                    return 1
            else:
                print(json.dumps(result, sort_keys=True))
            if args.once:
                return 0
            if stop_event.wait(args.interval_minutes * 60):
                return 0
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.enable:
        parser.error("scheduled scans are disabled by default; pass --enable explicitly")
    if not args.once and args.interval_minutes is None:
        parser.error("provide --once or a positive --interval-minutes value")
    try:
        args.base_url = validate_base_url(args.base_url)
    except ValueError as error:
        parser.error(str(error))

    try:
        return _run_scheduler(args, threading.Event())
    except SchedulerAlreadyRunning:
        print(json.dumps({"status": "already_running"}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
