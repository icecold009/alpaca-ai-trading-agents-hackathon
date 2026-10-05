from __future__ import annotations

import json
import signal
import subprocess
import sys
import threading
from collections.abc import Callable
from contextlib import nullcontext
from pathlib import Path
from types import FrameType
from typing import cast
from urllib.request import Request

import pytest
from scripts import schedule_personal_scans as scheduler


class FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.read_limit: int | None = None

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self, limit: int) -> bytes:
        self.read_limit = limit
        return self.payload


class FakeOpener:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.request: Request | None = None
        self.timeout: float | None = None

    def open(self, request: Request, *, timeout: float) -> FakeResponse:
        self.request = request
        self.timeout = timeout
        return self.response


@pytest.mark.parametrize(
    "base_url",
    [
        "https://127.0.0.1:8000",
        "http://example.com",
        "http://127.0.0.1:8000/path",
        "http://user:password@127.0.0.1:8000",
        "http://127.0.0.1:8000/?token=secret",
        "http://127.0.0.1:8000/#fragment",
        "http://127.0.0.1:99999",
        "http://127.0.0.1:8000\\@example.com",
    ],
)
def test_scheduler_rejects_nonlocal_or_ambiguous_destinations(base_url: str) -> None:
    with pytest.raises(ValueError):
        scheduler.validate_base_url(base_url)


def test_scheduler_posts_only_bounded_scan_to_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    response = FakeResponse(json.dumps({"status": "completed"}).encode())
    opener = FakeOpener(response)
    passed_handlers: list[object] = []

    def fake_build_opener(*handlers: object) -> FakeOpener:
        passed_handlers.extend(handlers)
        return opener

    monkeypatch.setattr(scheduler, "build_opener", fake_build_opener)
    result = scheduler.scan_once("http://LOCALHOST:8000/", ["spy", "qqq"], 9)

    assert result == {"status": "completed"}
    assert opener.request is not None
    assert opener.request.full_url == "http://localhost:8000/api/scans"
    assert opener.request.get_method() == "POST"
    request_data = opener.request.data
    assert isinstance(request_data, bytes)
    assert json.loads(request_data.decode()) == {"symbols": ["SPY", "QQQ"]}
    assert opener.timeout == 9
    assert response.read_limit == scheduler.MAX_RESPONSE_BYTES + 1
    assert len(passed_handlers) == 1
    redirect_handler = passed_handlers[0]
    assert redirect_handler is scheduler._DenyRedirects
    scheduler._DenyRedirects().redirect_request(
        None, opener.request, None, 302, "Found", {}, "http://example.com/"
    )


@pytest.mark.parametrize(
    ("symbols", "timeout"),
    [(["AAPL"], 5), (["SPY", "SPY"], 5), (["SPY"], 121), (["SPY"], 0)],
)
def test_scheduler_rejects_unsupported_symbols_and_unbounded_timeouts(
    symbols: list[str], timeout: float
) -> None:
    with pytest.raises(ValueError):
        scheduler.scan_once("http://127.0.0.1:8000", symbols, timeout)


def test_scheduler_caps_json_response_size(monkeypatch: pytest.MonkeyPatch) -> None:
    response = FakeResponse(b"x" * (scheduler.MAX_RESPONSE_BYTES + 1))
    monkeypatch.setattr(scheduler, "build_opener", lambda *_: FakeOpener(response))

    with pytest.raises(ValueError, match="size limit"):
        scheduler.scan_once("http://127.0.0.1:8000", ["SPY"], 5)


def test_scheduler_lock_blocks_a_second_process_and_releases_on_exit(
    tmp_path: Path,
) -> None:
    origin = "http://127.0.0.1:58123"
    code = (
        "import sys, time; "
        "from pathlib import Path; "
        "from scripts.schedule_personal_scans import SchedulerInstanceLock; "
        "lock = SchedulerInstanceLock(sys.argv[1], Path(sys.argv[2])); "
        "lock.acquire(); print('ready', flush=True); time.sleep(30)"
    )
    child = subprocess.Popen(
        [sys.executable, "-c", code, origin, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert child.stdout is not None
        assert child.stdout.readline().strip() == "ready"
        competing = scheduler.SchedulerInstanceLock(origin, tmp_path)
        with pytest.raises(scheduler.SchedulerAlreadyRunning):
            competing.acquire()
    finally:
        child.terminate()
        child.wait(timeout=5)
        if child.stdout is not None:
            child.stdout.close()
        if child.stderr is not None:
            child.stderr.close()

    with scheduler.SchedulerInstanceLock(origin, tmp_path):
        pass


def test_scheduler_lock_releases_when_scan_loop_raises(tmp_path: Path) -> None:
    origin = "http://127.0.0.1:58124"
    with pytest.raises(RuntimeError, match="interrupted"), scheduler.SchedulerInstanceLock(
        origin, tmp_path
    ):
        raise RuntimeError("interrupted")

    with scheduler.SchedulerInstanceLock(origin, tmp_path):
        pass


def test_signal_handler_sets_stop_event_and_is_restored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handlers: dict[signal.Signals, object] = {}

    def fake_signal(signum: signal.Signals, handler: object) -> object:
        previous = handlers.get(signum, signal.SIG_DFL)
        handlers[signum] = handler
        return previous

    monkeypatch.setattr(signal, "signal", fake_signal)
    stop_event = threading.Event()
    with scheduler._shutdown_handlers(stop_event):
        handler = cast(
            Callable[[int, FrameType | None], object], handlers[signal.SIGTERM]
        )
        handler(signal.SIGTERM, None)
        assert stop_event.is_set()

    assert handlers[signal.SIGTERM] is signal.SIG_DFL


def test_retry_backoff_stops_promptly_on_shutdown(monkeypatch: pytest.MonkeyPatch) -> None:
    args = scheduler.build_parser().parse_args(
        ["--enable", "--once", "--retries", "3", "--backoff-seconds", "30"]
    )
    calls = 0

    def fail_scan(*_: object, **__: object) -> dict[str, object]:
        nonlocal calls
        calls += 1
        raise OSError("local API unavailable")

    class InterruptingEvent(threading.Event):
        def wait(self, timeout: float | None = None) -> bool:
            self.set()
            return True

    monkeypatch.setattr(scheduler, "scan_once", fail_scan)
    stop_event = InterruptingEvent()

    assert scheduler._scan_with_retry(args, stop_event) == (None, 1)
    assert calls == 1
    assert stop_event.is_set()


def test_scheduled_interval_stops_promptly_on_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = scheduler.build_parser().parse_args(
        ["--enable", "--interval-minutes", "1", "--base-url", "http://127.0.0.1:58125"]
    )
    calls: list[str] = []

    class FakeLock:
        def __init__(self, *_: object) -> None:
            pass

        def __enter__(self) -> FakeLock:
            return self

        def __exit__(self, *_: object) -> None:
            return None

    class InterruptingEvent(threading.Event):
        def wait(self, timeout: float | None = None) -> bool:
            calls.append("wait")
            self.set()
            return True

    monkeypatch.setattr(scheduler, "SchedulerInstanceLock", FakeLock)
    monkeypatch.setattr(scheduler, "scan_once", lambda *_: {"status": "ok"})
    monkeypatch.setattr(scheduler, "_shutdown_handlers", lambda _event: nullcontext())
    stop_event = InterruptingEvent()

    assert scheduler._run_scheduler(args, stop_event) == 0
    assert calls == ["wait"]
