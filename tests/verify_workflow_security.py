"""Impede regressões de segurança nos workflows de CI e release."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE_WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


def run_blocks(text: str) -> list[str]:
    return re.findall(r"(?ms)^        run: (?:\|\n)?(.*?)(?=^      - |\Z)", text)


def main() -> int:
    release = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    ci = CI_WORKFLOW.read_text(encoding="utf-8")
    errors: list[str] = []

    for forbidden in ("pull_request:", "workflow_dispatch:", "branches: [main]"):
        if forbidden in release:
            errors.append(f"release.yml não pode ser acionado por {forbidden}")

    for required in (
        "permissions:\n  contents: read",
        "persist-credentials: false",
        "RELEASE_TAG: ${{ github.ref_name }}",
        "if ($env:RELEASE_TAG -notmatch",
        'gh release create "$env:RELEASE_TAG"',
        "if: github.event_name == 'push' && github.ref_type == 'tag' && startsWith(github.ref_name, 'v')",
        "    permissions:\n      contents: write",
    ):
        if required not in release:
            errors.append(f"release.yml não contém proteção esperada: {required}")

    if any("github.ref_name" in block for block in run_blocks(release)):
        errors.append("release.yml interpola github.ref_name dentro de um bloco run")

    for required in (
        "permissions:\n  contents: read",
        "persist-credentials: false",
        "Download verified FFmpeg",
        "Verify published payload",
        "Verify installer payload",
    ):
        if required not in ci:
            errors.append(f"ci.yml não contém proteção esperada: {required}")

    if "contents: write" in ci:
        errors.append("ci.yml não pode receber contents: write")

    if errors:
        print("Workflow security contract: FALHOU", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print("Workflow security contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
