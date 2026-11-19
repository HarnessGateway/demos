"""The three demo packages are valid harness packages, and each carries what makes it its app's agent."""

import importlib.util
from pathlib import Path

import pytest
from harnessgateway import packaging
from harnessgateway.domain.archive import read_archive
from harnessgateway.domain.environment import Environment

PACKAGES = Path(__file__).parents[1] / "packages"
INSTRUCTIONS = {
    "sales-codex": ("seeds/mind/.codex/AGENTS.md", "crm-drafts"),
    "journalist-pi": ("seeds/mind/.pi/agent/AGENTS.md", "desk-report"),
    "social-claude-code": ("seeds/mind/.claude/CLAUDE.md", "social-plan"),
}


@pytest.mark.parametrize("name", sorted(INSTRUCTIONS))
def test_the_package_is_valid_and_its_recorded_case_translates(name: str) -> None:
    results = packaging.check(PACKAGES / name)
    assert [result.name for result in results] == ["hello"]
    assert read_archive(packaging.pack(PACKAGES / name)).manifest.name == name


@pytest.mark.parametrize("name", sorted(INSTRUCTIONS))
def test_the_agent_s_instructions_define_the_block_its_app_parses(name: str) -> None:
    path, block = INSTRUCTIONS[name]
    instructions = (PACKAGES / name / path).read_text()
    assert f"```{block}" in instructions
    assert "/workspace" not in instructions                    # the work folder is the working directory


def test_what_an_agent_reaches_is_its_environment_s_to_say_and_setup_makes_one_for_each() -> None:
    # A package names no host (a manifest that does is refused), so the hosts the journalist's README lists are
    # allowed by the environment setup.py makes for it, and by nothing else.
    spec = importlib.util.spec_from_file_location("setup", PACKAGES.parent / "scripts" / "setup.py")
    assert spec is not None and spec.loader is not None
    setup = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(setup)
    assert {environment for _, _, environment in setup.APPS.values()} == set(setup.ENVIRONMENTS)
    for environment in setup.ENVIRONMENTS.values():
        Environment.load({"name": "x", **environment})
    assert setup.ENVIRONMENTS["model-only"]["network"] == {"mode": "closed"}
    desk = setup.ENVIRONMENTS["primary-sources"]["network"]
    assert (desk["mode"], desk["package_managers"]) == ("limited", False)
    readme = (PACKAGES / "journalist-pi" / "README.md").read_text()
    assert desk["allow"] and all(f"`{host}`" in readme for host in desk["allow"])
