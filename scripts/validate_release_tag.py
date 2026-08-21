"""Valida tags de release no formato SemVer 2.0.0 com prefixo v."""

from __future__ import annotations

import argparse
import re
import sys

SEMVER_TAG = re.compile(
    r"^v"
    r"(?:0|[1-9][0-9]*)\."
    r"(?:0|[1-9][0-9]*)\."
    r"(?:0|[1-9][0-9]*)"
    r"(?:-"
    r"(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*))*"
    r")?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$",
    re.ASCII,
)


def is_valid_release_tag(tag: str) -> bool:
    return bool(SEMVER_TAG.fullmatch(tag))


def self_test() -> None:
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
        "v1١.2.3",
        "v1.2٣.3",
        "v1.2.3-١alpha",
        "v1.2.3' ; Write-Host hacked",
    )
    for tag in valid:
        assert is_valid_release_tag(tag), f"A tag válida foi rejeitada: {tag}"
    for tag in invalid:
        assert not is_valid_release_tag(tag), f"A tag inválida foi aceita: {tag}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Valida uma tag SemVer de release.")
    parser.add_argument("tag", nargs="?", help="Tag no formato vMAJOR.MINOR.PATCH")
    parser.add_argument("--self-test", action="store_true", help="Executa casos de regressão")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.self_test:
        self_test()
        print("Release tag self-test: OK")
        return 0
    if not args.tag:
        print("Informe uma tag de release ou use --self-test.", file=sys.stderr)
        return 2
    if not is_valid_release_tag(args.tag):
        print(f"Tag de release inválida: {args.tag}", file=sys.stderr)
        return 1
    print(f"Tag de release válida: {args.tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
