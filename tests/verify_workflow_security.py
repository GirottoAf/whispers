"""Valida a estrutura de segurança dos workflows de CI e release."""

from __future__ import annotations

import copy
import re
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ModuleNotFoundError as error:
    raise SystemExit("PyYAML é necessário para validar os workflows: " + str(error))

ROOT = Path(__file__).resolve().parents[1]
RELEASE_WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
GITHUB_EXPRESSION = re.compile(r"\$\{\{\s*github(?:\.|\s)", re.IGNORECASE)


def as_mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_steps(value: Any) -> list[dict[str, Any]]:
    return value if isinstance(value, list) else []


def load_workflow(path: Path) -> dict[str, Any]:
    data = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    if not isinstance(data, dict):
        raise AssertionError(f"Workflow YAML inválido: {path}")
    return data


def job_steps(job: dict[str, Any]) -> list[dict[str, Any]]:
    return as_steps(job.get("steps"))


def uses(step: dict[str, Any]) -> str:
    return str(step.get("uses", "")).lower()


def run(step: dict[str, Any]) -> str:
    return str(step.get("run", ""))


def named_step(steps: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    return next((step for step in steps if step.get("name") == name), None)


def validate_checkout_and_runs(workflow_name: str, jobs: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for job_name, raw_job in jobs.items():
        job = as_mapping(raw_job)
        for index, step in enumerate(job_steps(job), start=1):
            if uses(step).startswith("actions/checkout@"):
                checkout_options = as_mapping(step.get("with"))
                if checkout_options.get("persist-credentials") != "false":
                    errors.append(
                        f"{workflow_name}:{job_name}: checkout #{index} precisa usar persist-credentials: false"
                    )
            if GITHUB_EXPRESSION.search(run(step)):
                errors.append(
                    f"{workflow_name}:{job_name}: expressão github.* não pode aparecer em run"
                )
    return errors


def requires(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def guard_is_strict(job: dict[str, Any], job_name: str, errors: list[str]) -> None:
    guard = str(job.get("if", ""))
    for required in (
        "github.event_name == 'push'",
        "github.event.deleted == false",
        "github.ref_type == 'tag'",
        "startsWith(github.ref_name, 'v')",
    ):
        requires(required in guard, f"release.yml:{job_name} não exige {required}", errors)


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
        as_mapping(workflow.get("permissions")).get("contents") == "read",
        "release.yml precisa iniciar com contents: read",
        errors,
    )

    jobs = as_mapping(workflow.get("jobs"))
    build = as_mapping(jobs.get("build-installer"))
    publish = as_mapping(jobs.get("publish-release"))
    requires(bool(build), "release.yml não tem job build-installer", errors)
    requires(bool(publish), "release.yml não tem job publish-release", errors)

    for job_name, job in (("build-installer", build), ("publish-release", publish)):
        guard_is_strict(job, job_name, errors)

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
    requires(
        any(uses(step).startswith("actions/upload-artifact@") for step in build_steps),
        "build-installer deve publicar o instalador como artifact",
        errors,
    )
    requires(
        any(uses(step).startswith("actions/download-artifact@") for step in publish_steps),
        "publish-release deve baixar o artifact validado",
        errors,
    )
    requires(
        not any(uses(step).startswith("actions/checkout@") for step in publish_steps),
        "publish-release não pode executar checkout",
        errors,
    )
    requires(
        "GH_TOKEN" not in as_mapping(build.get("env"))
        and not any("GH_TOKEN" in as_mapping(step.get("env")) for step in build_steps),
        "build-installer não pode receber GH_TOKEN explícito",
        errors,
    )

    version_step = named_step(build_steps, "Define version")
    requires(version_step is not None, "build-installer não define a versão", errors)
    if version_step is not None:
        requires(
            as_mapping(version_step.get("env")).get("RELEASE_TAG") == "${{ github.ref_name }}",
            "Define version deve receber RELEASE_TAG via env",
            errors,
        )
        requires(
            'python scripts/validate_release_tag.py "$env:RELEASE_TAG"' in run(version_step),
            "Define version deve validar a tag sem interpolação direta",
            errors,
        )

    release_step = named_step(publish_steps, "Create GitHub Release")
    requires(release_step is not None, "publish-release não tem etapa de publicação", errors)
    if release_step is not None:
        requires(
            as_mapping(release_step.get("env")).get("GH_TOKEN") == "${{ github.token }}",
            "Create GitHub Release deve receber GH_TOKEN somente na etapa de publicação",
            errors,
        )
        requires(
            as_mapping(release_step.get("env")).get("RELEASE_TAG") == "${{ github.ref_name }}",
            "Create GitHub Release deve receber RELEASE_TAG via env",
            errors,
        )

    publish_runs = "\n".join(run(step) for step in publish_steps)
    requires(
        'gh release create "$env:RELEASE_TAG"' in publish_runs,
        "publish-release deve publicar somente o artifact validado",
        errors,
    )
    for forbidden in ("scripts/", "dotnet", "installer/Whispers.iss", "choco"):
        requires(
            forbidden not in publish_runs,
            f"publish-release não pode executar código de build: {forbidden}",
            errors,
        )

    errors.extend(validate_checkout_and_runs("release.yml", jobs))
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
        as_mapping(workflow.get("permissions")).get("contents") == "read",
        "ci.yml precisa usar contents: read",
        errors,
    )

    jobs = as_mapping(workflow.get("jobs"))
    for job_name, raw_job in jobs.items():
        permissions = as_mapping(as_mapping(raw_job).get("permissions"))
        requires(
            permissions.get("contents") != "write",
            f"ci.yml:{job_name} não pode ter contents: write",
            errors,
        )

    build = as_mapping(jobs.get("build"))
    steps = job_steps(build)
    for required_name in ("Download verified FFmpeg", "Verify published payload", "Verify installer payload"):
        requires(named_step(steps, required_name) is not None, f"ci.yml não tem etapa {required_name}", errors)
    requires(
        any("python tests/verify_release_tag.py" in run(step) for step in steps),
        "ci.yml deve testar o validador SemVer",
        errors,
    )
    errors.extend(validate_checkout_and_runs("ci.yml", jobs))
    return errors


def assert_regression_fixtures(release: dict[str, Any], ci: dict[str, Any]) -> None:
    insecure_ci = copy.deepcopy(ci)
    as_steps(as_mapping(as_mapping(insecure_ci["jobs"])["build"]).get("steps")).append(
        {"uses": "actions/checkout@v7"}
    )
    assert any("persist-credentials" in error for error in validate_ci(insecure_ci))

    insecure_release = copy.deepcopy(release)
    as_steps(as_mapping(as_mapping(insecure_release["jobs"])["build-installer"]).get("steps")).append(
        {"run": 'echo "${{ github.ref }}"'}
    )
    assert any("expressão github" in error for error in validate_release(insecure_release))

    token_release = copy.deepcopy(release)
    as_steps(as_mapping(as_mapping(token_release["jobs"])["build-installer"]).get("steps"))[0]["env"] = {
        "GH_TOKEN": "${{ github.token }}"
    }
    assert any("GH_TOKEN" in error for error in validate_release(token_release))


def main() -> int:
    release = load_workflow(RELEASE_WORKFLOW)
    ci = load_workflow(CI_WORKFLOW)
    errors = validate_release(release) + validate_ci(ci)

    try:
        assert_regression_fixtures(release, ci)
    except (AssertionError, KeyError) as error:
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
