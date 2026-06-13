#!/usr/bin/env python3
"""Install this repository as a Codex skill."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

import validate_package


SKILL_NAME = "autocite"
REPO_ROOT = Path(__file__).resolve().parents[1]
EXCLUDE_NAMES = {".git", ".DS_Store", "__pycache__", "tests"}
EXCLUDE_SUFFIXES = {".pyc"}


def default_target_root(codex_home: Path | None = None) -> Path:
    home = codex_home or Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    return Path(home).expanduser() / "skills"


def should_ignore(path: Path) -> bool:
    return path.name in EXCLUDE_NAMES or path.suffix in EXCLUDE_SUFFIXES


def copy_package(source: Path, destination: Path) -> None:
    def ignore(directory: str, names: list[str]) -> set[str]:
        ignored = set()
        for name in names:
            candidate = Path(directory) / name
            if should_ignore(candidate):
                ignored.add(name)
        return ignored

    shutil.copytree(source, destination, ignore=ignore)


def remove_existing(destination: Path) -> None:
    if destination.is_symlink() or destination.is_file():
        destination.unlink()
    elif destination.is_dir():
        shutil.rmtree(destination)


def install(source: Path = REPO_ROOT, target_root: Path | None = None, force: bool = False) -> Path:
    source = source.resolve()
    summary = validate_package.validate_package(source)
    if not summary["ok"]:
        raise ValueError("package validation failed: " + "; ".join(summary["errors"]))

    root = target_root or default_target_root()
    destination = root.expanduser().resolve() / SKILL_NAME
    if destination.exists():
        if not force:
            raise FileExistsError(f"target already exists: {destination}")
        remove_existing(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    copy_package(source, destination)
    return destination


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install Autocite into Codex skills.")
    parser.add_argument("--source", type=Path, default=REPO_ROOT)
    parser.add_argument("--target", type=Path, help="Codex skills root. Defaults to $CODEX_HOME/skills or ~/.codex/skills.")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = validate_package.validate_package(args.source)
    if not summary["ok"]:
        print("[ERROR] Package validation failed", file=sys.stderr)
        for error in summary["errors"]:
            print(f"- {error}", file=sys.stderr)
        return 1
    if args.validate_only:
        print(f"[OK] Package is valid: {Path(args.source).resolve()}")
        return 0

    target_root = args.target or default_target_root()
    destination = Path(target_root).expanduser().resolve() / SKILL_NAME
    if args.dry_run:
        print(f"Source: {Path(args.source).resolve()}")
        print(f"Destination: {destination}")
        print("Files will exclude: .git, tests, .DS_Store, __pycache__, *.pyc")
        return 0

    try:
        installed = install(args.source, target_root, args.force)
    except Exception as exc:
        print(f"[ERROR] Install failed: {exc}", file=sys.stderr)
        return 1
    print(f"[OK] Installed Autocite for Codex: {installed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
