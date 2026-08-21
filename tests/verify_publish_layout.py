"""Verifica se o payload distribuído contém o app e suas dependências físicas."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REQUIRED_FILES = (
    "Whispers.exe",
    "Whispers.deps.json",
    "Whispers.runtimeconfig.json",
    "coreclr.dll",
    "hostfxr.dll",
    "hostpolicy.dll",
    "System.Private.CoreLib.dll",
    "PresentationCore.dll",
    "PresentationFramework.dll",
    "WindowsBase.dll",
    "tools/ffmpeg.exe",
    "tools/ffprobe.exe",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verifica se o payload publicado do Whispers é autocontido."
    )
    parser.add_argument("publish_dir", type=Path, help="Diretório a ser validado")
    return parser.parse_args()


def main() -> int:
    publish_dir = parse_args().publish_dir
    if not publish_dir.is_dir():
        print(f"Diretório de publicação não encontrado: {publish_dir}", file=sys.stderr)
        return 1

    missing = [relative for relative in REQUIRED_FILES if not (publish_dir / relative).is_file()]
    empty = [
        relative
        for relative in REQUIRED_FILES
        if (publish_dir / relative).is_file() and (publish_dir / relative).stat().st_size == 0
    ]

    if missing or empty:
        print("Payload do Whispers está incompleto:", file=sys.stderr)
        if missing:
            print("  Ausentes: " + ", ".join(missing), file=sys.stderr)
        if empty:
            print("  Vazios: " + ", ".join(empty), file=sys.stderr)
        return 1

    files = [path for path in publish_dir.rglob("*") if path.is_file()]
    total_bytes = sum(path.stat().st_size for path in files)
    print(
        "Layout do payload: OK "
        f"({len(REQUIRED_FILES)} dependências obrigatórias, "
        f"{len(files)} arquivos, {total_bytes} bytes)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
