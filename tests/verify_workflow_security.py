"""Valida a estrutura de segurança dos workflows de CI e release.

O parser abaixo suporta deliberadamente o subconjunto YAML usado nos workflows
versionados. Ele falha fechado diante de sintaxe não esperada, para não trocar
uma verificação de segurança por uma aceitação parcial do arquivo.
"""

from __future__ import annotations

import copy
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RELEASE_WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
GITHUB_EXPRESSION = re.compile(r"\$\{\{")
IMMUTABLE_ACTION = re.compile(r"^[a-z0-9_.-]+/[a-z0-9_.-]+@[0-9a-f]{40}$")

ACTIONS = {
    "checkout": "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
    "setup_dotnet": "actions/setup-dotnet@a98b56852c35b8e3190ac28c8c2271da59106c68",
    "upload_artifact": "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02",
    "download_artifact": "actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093",
}
BUILD_GUARD = (
    "github.event_name == 'push' && github.event.deleted == false && "
    "github.ref_type == 'tag' && startsWith(github.ref_name, 'v')"
)
PUBLISH_GUARD = "needs.build-installer.result == 'success' && " + BUILD_GUARD
RELEASE_ENV = {
    "GH_TOKEN": "${{ github.token }}",
    "GH_REPO": "${{ github.repository }}",
    "RELEASE_SHA": "${{ github.sha }}",
    "RELEASE_TAG": "${{ github.ref_name }}",
}


def indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def parse_scalar(value: str) -> Any:
    value = value.strip()
    if "#" in value:
        raise ValueError("Comentários inline não são permitidos no contrato de segurança")
    if value == "{}":
        return {}
    if value.startswith("[") and value.endswith("]"):
        contents = value[1:-1].strip()
        return [] if not contents else [parse_scalar(item) for item in contents.split(",")]
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def split_key_value(text: str, context: str) -> tuple[str, str]:
    key, separator, value = text.partition(":")
    if not separator or not key.strip():
        raise ValueError(f"YAML inválido em {context}: {text!r}")
    return key.strip(), value.strip()


def next_boundary(lines: list[str], start: int, indentation: int, end: int) -> int:
    index = start
    while index < end:
        line = lines[index]
        if line.strip() and indent_of(line) <= indentation:
            return index
        index += 1
    return end


def parse_flat_mapping(
    lines: list[str], start: int, end: int, indentation: int, context: str
) -> tuple[dict[str, Any], int]:
    mapping: dict[str, Any] = {}
    index = start
    while index < end:
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        current_indent = indent_of(line)
        if current_indent < indentation:
            break
        if current_indent != indentation or line[indentation:].startswith("- "):
            raise ValueError(f"Sintaxe YAML não suportada em {context}: {line!r}")
        key, raw_value = split_key_value(line[indentation:], context)
        if not raw_value:
            raise ValueError(f"Mapeamento aninhado não suportado em {context}: {line!r}")
        if key in mapping:
            raise ValueError(f"Chave YAML duplicada em {context}: {key}")
        mapping[key] = parse_scalar(raw_value)
        index += 1
    return mapping, index


def parse_steps(lines: list[str], start: int, end: int, context: str) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    index = start
    while index < end:
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        if indent_of(line) != 6 or not line[6:].startswith("- "):
            raise ValueError(f"Etapa YAML inválida em {context}: {line!r}")

        first_key, first_value = split_key_value(line[8:], context)
        step: dict[str, Any] = {}
        if first_key in {"with", "env"} and not first_value:
            nested_end = next_boundary(lines, index + 1, 6, end)
            step[first_key], index = parse_flat_mapping(lines, index + 1, nested_end, 10, context)
        elif first_key == "run" and first_value in {"|", ">", "|-", ">-"}:
            block_end = next_boundary(lines, index + 1, 6, end)
            block: list[str] = []
            for block_line in lines[index + 1 : block_end]:
                if block_line.strip() and indent_of(block_line) < 10:
                    raise ValueError(f"Bloco run inválido em {context}: {block_line!r}")
                block.append(block_line[10:] if len(block_line) >= 10 else "")
            step[first_key] = "\n".join(block).strip()
            index = block_end
        else:
            if not first_value:
                raise ValueError(f"Valor ausente em etapa {context}: {line!r}")
            step[first_key] = parse_scalar(first_value)
            index += 1

        while index < end:
            child = lines[index]
            if not child.strip():
                index += 1
                continue
            if indent_of(child) <= 6:
                break
            if indent_of(child) != 8:
                raise ValueError(f"Indentação de etapa inválida em {context}: {child!r}")
            key, raw_value = split_key_value(child[8:], context)
            if key in step:
                raise ValueError(f"Chave de etapa duplicada em {context}: {key}")
            if key in {"with", "env"}:
                if raw_value:
                    raise ValueError(f"Mapa {key} inválido em {context}: {child!r}")
                nested_end = next_boundary(lines, index + 1, 8, end)
                step[key], index = parse_flat_mapping(lines, index + 1, nested_end, 10, context)
                continue
            if key == "run" and raw_value in {"|", ">", "|-", ">-"}:
                block_end = next_boundary(lines, index + 1, 8, end)
                block = []
                for block_line in lines[index + 1 : block_end]:
                    if block_line.strip() and indent_of(block_line) < 10:
                        raise ValueError(f"Bloco run inválido em {context}: {block_line!r}")
                    block.append(block_line[10:] if len(block_line) >= 10 else "")
                step[key] = "\n".join(block).strip()
                index = block_end
                continue
            if not raw_value:
                raise ValueError(f"Valor ausente em etapa {context}: {child!r}")
            step[key] = parse_scalar(raw_value)
            index += 1

        steps.append(step)
    return steps


def parse_job(lines: list[str], start: int, end: int, context: str) -> dict[str, Any]:
    job: dict[str, Any] = {}
    index = start
    while index < end:
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        if indent_of(line) != 4:
            raise ValueError(f"Job YAML inválido em {context}: {line!r}")
        key, raw_value = split_key_value(line[4:], context)
        if key in job:
            raise ValueError(f"Chave de job duplicada em {context}: {key}")
        if key == "permissions":
            if raw_value:
                raise ValueError(f"Permissions inválido em {context}: {line!r}")
            nested_end = next_boundary(lines, index + 1, 4, end)
            job[key], index = parse_flat_mapping(lines, index + 1, nested_end, 6, context)
            continue
        if key == "steps":
            if raw_value:
                raise ValueError(f"Steps inválido em {context}: {line!r}")
            nested_end = next_boundary(lines, index + 1, 4, end)
            job[key] = parse_steps(lines, index + 1, nested_end, context)
            index = nested_end
            continue
        if not raw_value:
            raise ValueError(f"Valor de job ausente em {context}: {line!r}")
        job[key] = parse_scalar(raw_value)
        index += 1
    return job


def parse_workflow_subset(path: Path) -> dict[str, Any]:
    lines = path.read_text(encoding="utf-8").splitlines()
    top_level: dict[str, tuple[str, int]] = {}
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        if indent_of(line) != 0:
            continue
        key, raw_value = split_key_value(line, str(path))
        if key in top_level:
            raise ValueError(f"Chave de topo duplicada em {path}: {key}")
        top_level[key] = (raw_value, index)

    if set(top_level) - {"name", "on", "permissions", "jobs"}:
        raise ValueError(f"Chaves de topo não suportadas em {path}: {sorted(set(top_level) - {'name', 'on', 'permissions', 'jobs'})}")
    if "on" not in top_level or "permissions" not in top_level or "jobs" not in top_level:
        raise ValueError(f"Workflow incompleto em {path}")

    def section_end(start: int) -> int:
        return next_boundary(lines, start + 1, 0, len(lines))

    on_start = top_level["on"][1]
    on_end = section_end(on_start)
    triggers: dict[str, Any] = {}
    index = on_start + 1
    while index < on_end:
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        if indent_of(line) != 2:
            raise ValueError(f"Trigger YAML inválido em {path}: {line!r}")
        key, raw_value = split_key_value(line[2:], str(path))
        if key in triggers:
            raise ValueError(f"Trigger duplicado em {path}: {key}")
        if raw_value:
            triggers[key] = parse_scalar(raw_value)
            index += 1
        else:
            nested_end = next_boundary(lines, index + 1, 2, on_end)
            triggers[key], index = parse_flat_mapping(lines, index + 1, nested_end, 4, str(path))

    permissions_start = top_level["permissions"][1]
    permissions_end = section_end(permissions_start)
    permissions, _ = parse_flat_mapping(lines, permissions_start + 1, permissions_end, 2, str(path))

    jobs_start = top_level["jobs"][1]
    jobs_end = section_end(jobs_start)
    jobs: dict[str, Any] = {}
    index = jobs_start + 1
    while index < jobs_end:
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        if indent_of(line) != 2:
            raise ValueError(f"Jobs YAML inválido em {path}: {line!r}")
        job_name, raw_value = split_key_value(line[2:], str(path))
        if raw_value:
            raise ValueError(f"Definição de job inválida em {path}: {line!r}")
        if job_name in jobs:
            raise ValueError(f"Job duplicado em {path}: {job_name}")
        job_end = next_boundary(lines, index + 1, 2, jobs_end)
        jobs[job_name] = parse_job(lines, index + 1, job_end, f"{path}:{job_name}")
        index = job_end

    return {"on": triggers, "permissions": permissions, "jobs": jobs}


def as_mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_steps(value: Any) -> list[dict[str, Any]]:
    return value if isinstance(value, list) else []


def job_steps(job: dict[str, Any]) -> list[dict[str, Any]]:
    return as_steps(job.get("steps"))


def uses(step: dict[str, Any]) -> str:
    return str(step.get("uses", "")).lower()


def run(step: dict[str, Any]) -> str:
    return str(step.get("run", ""))


def named_step(steps: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    return next((step for step in steps if step.get("name") == name), None)


def normalized(value: Any) -> str:
    return " ".join(str(value).split())


def expressions_in_context(step: dict[str, Any]) -> list[str]:
    return [
        f"{key}.{name}"
        for key in ("env", "with")
        for name, value in as_mapping(step.get(key)).items()
        if GITHUB_EXPRESSION.search(str(value))
    ]


def require_no_context_expressions(
    steps: list[dict[str, Any]], scope: str, errors: list[str], allowed_steps: set[int] | None = None
) -> None:
    allowed_steps = allowed_steps or set()
    for index, step in enumerate(steps):
        if index in allowed_steps:
            continue
        for context in expressions_in_context(step):
            errors.append(f"{scope}: expressão não permitida em {context}")


def validate_actions_and_runs(workflow_name: str, jobs: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    expected_actions = set(ACTIONS.values())
    for job_name, raw_job in jobs.items():
        job = as_mapping(raw_job)
        for index, step in enumerate(job_steps(job), start=1):
            action = uses(step)
            if action:
                requires(
                    bool(IMMUTABLE_ACTION.fullmatch(action)),
                    f"{workflow_name}:{job_name}: action #{index} precisa estar fixada em SHA completo",
                    errors,
                )
                requires(
                    action in expected_actions,
                    f"{workflow_name}:{job_name}: action #{index} não faz parte da allowlist",
                    errors,
                )
            if action == ACTIONS["checkout"]:
                requires(
                    as_mapping(step.get("with")).get("persist-credentials") == "false",
                    f"{workflow_name}:{job_name}: checkout #{index} precisa usar persist-credentials: false",
                    errors,
                )
            if GITHUB_EXPRESSION.search(run(step)):
                errors.append(
                    f"{workflow_name}:{job_name}: expressão GitHub Actions não pode aparecer em run"
                )
    return errors


def guard_is_exact(job: dict[str, Any], expected: str, job_name: str, errors: list[str]) -> None:
    requires(
        normalized(job.get("if")) == expected,
        f"release.yml:{job_name} precisa usar somente o guard aprovado",
        errors,
    )


def requires(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def validate_publisher_run(release_run: str, errors: list[str]) -> None:
    for required in (
        "$ErrorActionPreference = 'Stop'",
        "$encodedTag = [uri]::EscapeDataString($env:RELEASE_TAG)",
        "git/ref/tags/$encodedTag",
        "git/tags/$tagObjectSha",
        "$tagCommitSha -ne $env:RELEASE_SHA",
        'gh release create "$env:RELEASE_TAG"',
        'artifacts/installer/Whispers-Setup-x64.exe',
        '--repo "$env:GH_REPO"',
        '--target "$env:RELEASE_SHA"',
        "--verify-tag",
    ):
        requires(required in release_run, f"publish-release não valida/publica corretamente: {required}", errors)
    for forbidden in (
        "start-process",
        "invoke-expression",
        "invoke-webrequest",
        "cmd.exe",
        "powershell",
        "pwsh",
        "python",
        "dotnet",
        "choco",
        "msiexec",
        "rundll32",
        "scripts/",
        "installer/whispers.iss",
    ):
        requires(
            forbidden not in release_run.lower(),
            f"publish-release não pode executar código, instalador ou ferramenta de build: {forbidden}",
            errors,
        )
    requires(
        not any("gh api" in line and "--repo" in line for line in release_run.splitlines()),
        "publish-release não pode passar --repo ao gh api",
        errors,
    )


def validate_release(workflow: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    triggers = as_mapping(workflow.get("on"))
    requires(set(triggers) == {"push"}, "release.yml só pode ser acionado por push de tag", errors)
    requires(
        as_mapping(triggers.get("push")).get("tags") == ["v*"],
        "release.yml deve restringir push a tags v*",
        errors,
    )
    requires(
        as_mapping(workflow.get("permissions")) == {"contents": "read"},
        "release.yml precisa iniciar somente com contents: read",
        errors,
    )

    jobs = as_mapping(workflow.get("jobs"))
    requires(
        set(jobs) == {"build-installer", "publish-release"},
        "release.yml deve conter somente build-installer e publish-release",
        errors,
    )
    build = as_mapping(jobs.get("build-installer"))
    publish = as_mapping(jobs.get("publish-release"))
    guard_is_exact(build, BUILD_GUARD, "build-installer", errors)
    guard_is_exact(publish, PUBLISH_GUARD, "publish-release", errors)
    requires(
        as_mapping(build.get("permissions")) == {"contents": "read"},
        "build-installer deve ter somente contents: read",
        errors,
    )
    requires(
        as_mapping(publish.get("permissions")) == {"contents": "write"},
        "publish-release deve ter somente contents: write",
        errors,
    )
    requires(
        publish.get("needs") == "build-installer",
        "publish-release deve depender de build-installer",
        errors,
    )

    build_steps = job_steps(build)
    publish_steps = job_steps(publish)
    version_step = named_step(build_steps, "Define version")
    upload_step = named_step(build_steps, "Upload installer")
    requires(version_step is not None, "build-installer não define a versão", errors)
    if version_step is not None:
        requires(
            as_mapping(version_step.get("env")) == {"RELEASE_TAG": "${{ github.ref_name }}"},
            "Define version deve receber somente RELEASE_TAG via env",
            errors,
        )
        requires(
            'python scripts/validate_release_tag.py "$env:RELEASE_TAG"' in run(version_step),
            "Define version deve validar a tag sem interpolação direta",
            errors,
        )
    requires(
        sum(uses(step) == ACTIONS["checkout"] for step in build_steps) == 1,
        "build-installer deve usar exatamente um checkout fixado",
        errors,
    )
    requires(
        sum(uses(step) == ACTIONS["setup_dotnet"] for step in build_steps) == 1,
        "build-installer deve usar exatamente um setup-dotnet fixado",
        errors,
    )
    requires(upload_step is not None, "build-installer não publica o artifact", errors)
    if upload_step is not None:
        requires(
            uses(upload_step) == ACTIONS["upload_artifact"],
            "Upload installer deve usar a action de artifact fixada",
            errors,
        )
        requires(
            as_mapping(upload_step.get("with"))
            == {
                "name": "whispers-installer",
                "path": "artifacts/installer/Whispers-Setup-x64.exe",
                "if-no-files-found": "error",
            },
            "Upload installer deve publicar somente o instalador esperado",
            errors,
        )
    version_index = build_steps.index(version_step) if version_step in build_steps else -1
    require_no_context_expressions(build_steps, "build-installer", errors, {version_index})

    requires(
        [step.get("name") for step in publish_steps]
        == ["Download installer", "Create GitHub Release"],
        "publish-release deve conter somente download e criação de release",
        errors,
    )
    download_step = named_step(publish_steps, "Download installer")
    release_step = named_step(publish_steps, "Create GitHub Release")
    requires(download_step is not None, "publish-release não baixa o artifact", errors)
    if download_step is not None:
        requires(
            uses(download_step) == ACTIONS["download_artifact"],
            "Download installer deve usar a action de artifact fixada",
            errors,
        )
        requires(
            as_mapping(download_step.get("with"))
            == {"name": "whispers-installer", "path": "artifacts/installer"},
            "Download installer deve baixar somente o artifact esperado",
            errors,
        )
        requires(not run(download_step), "Download installer não pode executar script", errors)
        require_no_context_expressions([download_step], "Download installer", errors)
    requires(release_step is not None, "publish-release não tem etapa de publicação", errors)
    if release_step is not None:
        requires(
            not uses(release_step),
            "Create GitHub Release não pode invocar uma action",
            errors,
        )
        requires(
            as_mapping(release_step.get("env")) == RELEASE_ENV,
            "Create GitHub Release deve receber somente os contextos aprovados",
            errors,
        )
        validate_publisher_run(run(release_step), errors)

    errors.extend(validate_actions_and_runs("release.yml", jobs))
    return errors


def validate_ci(workflow: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    triggers = as_mapping(workflow.get("on"))
    requires(set(triggers) == {"push", "pull_request"}, "ci.yml deve reagir a push e pull_request", errors)
    requires(
        as_mapping(triggers.get("push")).get("branches") == ["main"],
        "ci.yml deve limitar push à main",
        errors,
    )
    requires(
        as_mapping(workflow.get("permissions")) == {"contents": "read"},
        "ci.yml precisa usar somente contents: read",
        errors,
    )

    jobs = as_mapping(workflow.get("jobs"))
    requires(set(jobs) == {"build"}, "ci.yml deve conter somente o job build", errors)
    build = as_mapping(jobs.get("build"))
    requires(
        as_mapping(build.get("permissions")) == {},
        "ci.yml:build não pode ampliar permissões no nível do job",
        errors,
    )
    steps = job_steps(build)
    requires(
        sum(uses(step) == ACTIONS["checkout"] for step in steps) == 1,
        "ci.yml deve usar exatamente um checkout fixado",
        errors,
    )
    requires(
        sum(uses(step) == ACTIONS["setup_dotnet"] for step in steps) == 1,
        "ci.yml deve usar exatamente um setup-dotnet fixado",
        errors,
    )
    for required_name in ("Download verified FFmpeg", "Verify published payload", "Verify installer payload"):
        requires(named_step(steps, required_name) is not None, f"ci.yml não tem etapa {required_name}", errors)
    requires(
        any("python tests/verify_release_tag.py" in run(step) for step in steps),
        "ci.yml deve testar o validador SemVer",
        errors,
    )
    requires(
        any("python tests/verify_release_publish_script.py --require-pwsh" in run(step) for step in steps),
        "ci.yml deve validar a sintaxe PowerShell do publicador",
        errors,
    )
    require_no_context_expressions(steps, "ci.yml:build", errors)
    errors.extend(validate_actions_and_runs("ci.yml", jobs))
    return errors


def parse_fixture(name: str, contents: str) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="whispers-workflow-fixture-") as directory:
        path = Path(directory) / name
        path.write_text(contents, encoding="utf-8")
        return parse_workflow_subset(path)


def assert_regression_fixtures(release: dict[str, Any], ci: dict[str, Any]) -> None:
    bypass_guard = copy.deepcopy(release)
    as_mapping(as_mapping(bypass_guard["jobs"])["build-installer"])["if"] = BUILD_GUARD + " || true"
    assert any("guard aprovado" in error for error in validate_release(bypass_guard))

    extra_writer = copy.deepcopy(release)
    as_mapping(extra_writer["jobs"])["unexpected-writer"] = {
        "permissions": {"contents": "write"},
        "steps": [],
    }
    assert any("somente build-installer" in error for error in validate_release(extra_writer))

    artifact_execution = copy.deepcopy(release)
    as_steps(as_mapping(as_mapping(artifact_execution["jobs"])["publish-release"]).get("steps")).append(
        {"name": "Execute installer", "run": "Start-Process artifacts/installer/Whispers-Setup-x64.exe"}
    )
    artifact_errors = validate_release(artifact_execution)
    assert any("somente download" in error or "start-process" in error for error in artifact_errors)

    bracket_token = copy.deepcopy(release)
    checkout = as_steps(as_mapping(as_mapping(bracket_token["jobs"])["build-installer"]).get("steps"))[0]
    as_mapping(checkout.get("with"))["token"] = "${{ github['token'] }}"
    assert any("expressão não permitida" in error for error in validate_release(bracket_token))

    bracket_secret = copy.deepcopy(release)
    checkout = as_steps(as_mapping(as_mapping(bracket_secret["jobs"])["build-installer"]).get("steps"))[0]
    as_mapping(checkout.get("with"))["token"] = "${{ secrets['RELEASE_TOKEN'] }}"
    assert any("expressão não permitida" in error for error in validate_release(bracket_secret))

    mutable_action = copy.deepcopy(release)
    as_steps(as_mapping(as_mapping(mutable_action["jobs"])["build-installer"]).get("steps"))[0]["uses"] = "actions/checkout@v7"
    assert any("SHA completo" in error for error in validate_release(mutable_action))

    privileged_ci = copy.deepcopy(ci)
    as_mapping(as_mapping(privileged_ci["jobs"])["build"])["permissions"] = {
        "pull-requests": "write",
        "id-token": "write",
    }
    assert any("não pode ampliar permissões" in error for error in validate_ci(privileged_ci))

    release_text = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    guard_line = f"    if: {BUILD_GUARD}"
    assert guard_line in release_text
    try:
        inline_comment = parse_fixture(
            "release.yml",
            release_text.replace(guard_line, f"    if: true # {BUILD_GUARD}", 1),
        )
    except ValueError:
        pass
    else:
        assert any("guard aprovado" in error for error in validate_release(inline_comment))


def main() -> int:
    try:
        release = parse_workflow_subset(RELEASE_WORKFLOW)
        ci = parse_workflow_subset(CI_WORKFLOW)
    except ValueError as error:
        print(f"Workflow security contract: FALHOU\n- YAML não suportado: {error}", file=sys.stderr)
        return 1

    errors = validate_release(release) + validate_ci(ci)
    try:
        assert_regression_fixtures(release, ci)
    except (AssertionError, KeyError, IndexError) as error:
        errors.append(f"fixtures de regressão inválidas: {error}")

    if errors:
        print("Workflow security contract: FALHOU", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print("Workflow security contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
