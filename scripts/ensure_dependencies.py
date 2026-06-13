#!/usr/bin/env python3
"""Check and install Autocite runtime dependencies."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REQUIREMENTS = REPO_ROOT / "requirements.txt"


def read_requirements(path: Path) -> list[str]:
    requirements: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        requirements.append(value)
    return requirements


def import_name(requirement: str) -> str:
    package = re.split(r"[<>=!~;\[]", requirement, maxsplit=1)[0].strip()
    return package.replace("-", "_")


def missing_python_packages(requirements: list[str]) -> list[str]:
    missing = []
    for requirement in requirements:
        if importlib.util.find_spec(import_name(requirement)) is None:
            missing.append(requirement)
    return missing


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def install_python_requirements(requirements_path: Path) -> None:
    run([sys.executable, "-m", "pip", "install", "-r", str(requirements_path)])


def pdftotext_install_command(
    system: str | None = None,
    command_exists=None,
    is_root: bool | None = None,
) -> list[str] | None:
    system = system or platform.system()
    command_exists = command_exists or (lambda name: shutil.which(name) is not None)
    is_root = os.geteuid() == 0 if is_root is None and hasattr(os, "geteuid") else bool(is_root)
    sudo = [] if is_root else ["sudo"]

    if system == "Darwin" and command_exists("brew"):
        return ["brew", "install", "poppler"]
    if system == "Linux":
        if command_exists("apt-get"):
            return [*sudo, "apt-get", "install", "-y", "poppler-utils"]
        if command_exists("dnf"):
            return [*sudo, "dnf", "install", "-y", "poppler-utils"]
        if command_exists("yum"):
            return [*sudo, "yum", "install", "-y", "poppler-utils"]
        if command_exists("pacman"):
            return [*sudo, "pacman", "-S", "--noconfirm", "poppler"]
    if system == "Windows":
        if command_exists("winget"):
            return ["winget", "install", "--id", "oschwartz10612.Poppler", "-e"]
        if command_exists("choco"):
            return ["choco", "install", "poppler", "-y"]
    return None


def ensure_pdftotext(auto_install: bool) -> bool:
    if shutil.which("pdftotext") is not None:
        return True
    if not auto_install:
        return False
    command = pdftotext_install_command()
    if command is None:
        return False
    run(command)
    return shutil.which("pdftotext") is not None


def ensure(requirements_path: Path, auto_install: bool, install_system: bool) -> dict[str, object]:
    requirements = read_requirements(requirements_path)
    missing_before = missing_python_packages(requirements)
    if missing_before and auto_install:
        install_python_requirements(requirements_path)
    missing_after = missing_python_packages(requirements)

    had_pdftotext = shutil.which("pdftotext") is not None
    has_pdftotext = ensure_pdftotext(auto_install and install_system)

    return {
        "requirements": requirements,
        "missing_python_before": missing_before,
        "missing_python_after": missing_after,
        "pdftotext_before": had_pdftotext,
        "pdftotext_after": has_pdftotext,
        "ok": not missing_after and has_pdftotext,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Ensure Autocite dependencies are installed.")
    parser.add_argument("--requirements", type=Path, default=DEFAULT_REQUIREMENTS)
    parser.add_argument("--check-only", action="store_true", help="Report missing dependencies without installing.")
    parser.add_argument("--skip-system-install", action="store_true", help="Do not try to install pdftotext/poppler.")
    args = parser.parse_args()

    summary = ensure(
        requirements_path=args.requirements,
        auto_install=not args.check_only,
        install_system=not args.skip_system_install,
    )
    print(json.dumps(summary, indent=2))
    if not summary["ok"]:
        print(
            "Dependency check failed. Install Python requirements with "
            "`python -m pip install -r requirements.txt` and install Poppler/pdftotext "
            "with your system package manager.",
            file=sys.stderr,
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
