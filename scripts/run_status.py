#!/usr/bin/env python3
"""Read and write Autocite run status sidecars."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from io_utils import atomic_write_text


STATUS_FILE = "status.json"
VALID_STATES = (
    "created",
    "checking_dependencies",
    "extracting_comments",
    "extracting_pdfs",
    "preparing_endnote",
    "resolving_candidates",
    "awaiting_endnote",
    "inserting_citations",
    "verifying",
    "writing_audit",
    "completed",
    "failed",
    "cancelled",
)
TERMINAL_STATES = {"completed", "failed", "cancelled"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def status_path(run_dir: Path) -> Path:
    return run_dir / STATUS_FILE


def validate_state(state: str) -> None:
    if state not in VALID_STATES:
        raise ValueError(f"invalid status {state!r}; expected one of: {', '.join(VALID_STATES)}")


def write_status(
    run_dir: Path,
    state: str,
    *,
    step: str = "",
    reason: str = "",
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    validate_state(state)
    payload = {
        "state": state,
        "step": step,
        "reason": reason,
        "details": details or {},
        "updated_at": now_iso(),
        "terminal": state in TERMINAL_STATES,
    }
    atomic_write_text(status_path(run_dir), json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return payload


def read_status(run_dir: Path) -> dict[str, Any]:
    path = status_path(run_dir)
    if not path.exists():
        return {
            "state": "created",
            "step": "",
            "reason": "",
            "details": {},
            "updated_at": "",
            "terminal": False,
        }
    data = json.loads(path.read_text(encoding="utf-8"))
    state = data.get("state", "")
    validate_state(state)
    return data


def parse_detail(values: list[str]) -> dict[str, str]:
    details = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"--detail must use key=value form: {value!r}")
        key, raw = value.split("=", 1)
        details[key] = raw
    return details


def main() -> int:
    parser = argparse.ArgumentParser(description="Read or write an Autocite run status.json file.")
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--state", choices=VALID_STATES)
    parser.add_argument("--step", default="")
    parser.add_argument("--reason", default="")
    parser.add_argument("--detail", action="append", default=[], help="Add detail as key=value. May be repeated.")
    parser.add_argument("--read", action="store_true")
    args = parser.parse_args()

    try:
        if args.read:
            payload = read_status(args.run_dir)
        else:
            if not args.state:
                parser.error("--state is required unless --read is used")
            payload = write_status(
                args.run_dir,
                args.state,
                step=args.step,
                reason=args.reason,
                details=parse_detail(args.detail),
            )
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
