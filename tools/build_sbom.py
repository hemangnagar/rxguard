from __future__ import annotations

import argparse
import importlib.metadata
import subprocess
import sys
from pathlib import Path

DENIED = ("AGPL", "GPL-2", "GPL-3", "SSPL", "BUSL", "COMMONS CLAUSE")
ROOT = Path(__file__).resolve().parents[1]
SBOM = ROOT / "sbom" / "cyclonedx.json"
LICENSES = ROOT / "sbom" / "licenses.md"


def license_text(distribution: importlib.metadata.Distribution) -> str:
    metadata = distribution.metadata
    expression = metadata.get("License-Expression") or metadata.get("License") or ""
    classifiers = [
        value.removeprefix("License :: ")
        for value in metadata.get_all("Classifier", [])
        if value.startswith("License :: ")
    ]
    return expression.strip() or "; ".join(classifiers) or "UNDECLARED"


def inventory() -> list[tuple[str, str, str]]:
    rows = []
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata.get("Name")
        if name:
            rows.append((name, distribution.version, license_text(distribution)))
    return sorted(set(rows), key=lambda row: row[0].lower())


def check(rows: list[tuple[str, str, str]]) -> None:
    violations = [
        f"{name} {version}: {license_name}"
        for name, version, license_name in rows
        if any(item in license_name.upper() for item in DENIED)
    ]
    if violations:
        raise SystemExit("Denied dependency license(s):\n" + "\n".join(violations))


def write_inventory(rows: list[tuple[str, str, str]]) -> None:
    lines = ["# Python dependency license inventory", "", "| Package | Version | Declared license |", "|---|---:|---|"]
    lines.extend(f"| {name} | {version} | {license_name.replace('|', '/')} |" for name, version, license_name in rows)
    LICENSES.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Check denied licenses without regenerating files")
    args = parser.parse_args()
    rows = inventory()
    check(rows)
    if args.check:
        return
    SBOM.parent.mkdir(exist_ok=True)
    cyclonedx = Path(sys.executable).with_name("cyclonedx-py")
    subprocess.run(
        [
            str(cyclonedx),
            "environment",
            sys.executable,
            "--pyproject",
            str(ROOT / "pyproject.toml"),
            "--output-reproducible",
            "--output-format",
            "JSON",
            "--output-file",
            str(SBOM),
        ],
        check=True,
    )
    write_inventory(rows)


if __name__ == "__main__":
    main()
