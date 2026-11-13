"""The three demo packages are valid harness packages, and each carries what makes it its app's agent."""

from pathlib import Path

import pytest
from harnessgateway import packaging
from harnessgateway.domain.archive import read_archive

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


def test_the_journalist_may_reach_its_primary_sources_and_nothing_else_is_named() -> None:
    manifest = read_archive(packaging.pack(PACKAGES / "journalist-pi")).manifest
    assert "www.eia.gov" in [str(host) for host in manifest.run.egress]
    for name in ("sales-codex", "social-claude-code"):
        assert not read_archive(packaging.pack(PACKAGES / name)).manifest.run.egress
