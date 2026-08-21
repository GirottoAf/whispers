"""Verifica a validação estrita de tags SemVer usadas em releases."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_release_tag.py"


def load_validator():
    if not SCRIPT.is_file():
        raise AssertionError(f"Validador de tag ausente: {SCRIPT}")

    spec = importlib.util.spec_from_file_location("validate_release_tag", SCRIPT)
    if spec is None or spec.loader is None:
        raise AssertionError("Não foi possível carregar o validador de tag.")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    validator = load_validator()
    valid = (
        "v0.0.0",
        "v1.2.3",
        "v1.2.3-0",
        "v1.2.3-rc.1",
        "v1.2.3-01alpha",
        "v1.2.3+build.5",
        "v1.2.3-rc.1+build.5",
    )
    invalid = (
        "1.2.3",
        "v01.2.3",
        "v1.02.3",
        "v1.2.03",
        "v1.2",
        "v1.2.3-01",
        "v1.2.3-rc.02",
        "v1.2.3-",
        "v1.2.3+",
        "v1.2.3' ; Write-Host hacked",
    )

    for tag in valid:
        assert validator.is_valid_release_tag(tag), f"A tag válida foi rejeitada: {tag}"
    for tag in invalid:
        assert not validator.is_valid_release_tag(tag), f"A tag inválida foi aceita: {tag}"

    print("Release tag validation: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
