"""Opt-in local scheduler for scan-only RiskCourt workstation runs.

This helper calls the local scan API. It never calls an order endpoint, and it
requires ``--enable`` so a scheduled process cannot be started accidentally.
"""

from __future__ import annotations

import argparse
import json
import time
from collections.abc import Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def scan_once(base_url: str, symbols: Sequence[str], timeout: float) -> dict[str, object]:
    payload = json.dumps({"symbols": list(symbols)}).encode("utf-8")
    request = Request(
        f"{base_url.rstrip('/')}/api/scans",
        data=payload,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - caller supplies local URL
        return json.loads(response.read().decode("utf-8"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enable", action="store_true", help="explicitly enable scheduled scans")
    parser.add_argument("--once", action="store_true", help="run one scan and exit")
    parser.add_argument(
        "--interval-minutes",
        type=float,
        default=None,
        help="repeat interval; required unless --once is set",
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--symbols", nargs="+", default=["SPY", "QQQ"])
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.enable:
        parser.error("scheduled scans are disabled by default; pass --enable explicitly")
    if not args.once and (args.interval_minutes is None or args.interval_minutes <= 0):
        parser.error("provide --once or a positive --interval-minutes value")

    while True:
        try:
            result = scan_once(args.base_url, args.symbols, args.timeout)
            print(json.dumps(result, sort_keys=True))
        except (HTTPError, URLError, TimeoutError, ValueError) as error:
            print(json.dumps({"status": "scan_failed", "reason": str(error)}))
            if args.once:
                return 1
        if args.once:
            return 0
        time.sleep(args.interval_minutes * 60)


if __name__ == "__main__":
    raise SystemExit(main())
