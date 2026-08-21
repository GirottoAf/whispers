"""Valida a sintaxe PowerShell da etapa privilegiada de publicação."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from verify_workflow_security import parse_workflow_subset  # noqa: E402


def publisher_script() -> str:
    workflow = parse_workflow_subset(ROOT / ".github" / "workflows" / "release.yml")
    steps = workflow["jobs"]["publish-release"]["steps"]
    release_step = next(step for step in steps if step.get("name") == "Create GitHub Release")
    return str(release_step["run"])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Valida a sintaxe PowerShell do publicador.")
    parser.add_argument(
        "--require-pwsh",
        action="store_true",
        help="Falha se pwsh não estiver disponível; use no CI Windows.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pwsh = shutil.which("pwsh")
    if pwsh is None:
        message = "pwsh indisponível; validação sintática do publicador será feita no CI Windows."
        print(message, file=sys.stderr if args.require_pwsh else sys.stdout)
        return 1 if args.require_pwsh else 0

    parser_script = """param([string]$ScriptPath)
$tokens = $null
$errors = $null
[System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$tokens, [ref]$errors) | Out-Null
if ($errors.Count -gt 0) {
  $errors | ForEach-Object { Write-Error $_ }
  exit 1
}
Write-Output 'PowerShell do publicador: sintaxe OK'
"""
    with tempfile.TemporaryDirectory(prefix="whispers-publish-script-") as directory:
        directory_path = Path(directory)
        script_path = directory_path / "publish-release.ps1"
        parser_path = directory_path / "parse-publish-release.ps1"
        script_path.write_text(publisher_script() + "\n", encoding="utf-8")
        parser_path.write_text(parser_script, encoding="utf-8")
        result = subprocess.run(
            [pwsh, "-NoLogo", "-NoProfile", "-NonInteractive", "-File", str(parser_path), str(script_path)],
            text=True,
            capture_output=True,
            check=False,
        )
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
