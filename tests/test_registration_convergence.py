import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = "https://github.com/oxydavid-maxx/travelwork"


def _load(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def test_codex_and_claude_manifests_name_the_canonical_fork() -> None:
    for relative in (".codex-plugin/plugin.json", ".claude-plugin/plugin.json"):
        manifest = _load(relative)
        assert manifest["repository"] == CANONICAL
        assert manifest["homepage"] == CANONICAL
        assert manifest["author"]["url"] == "https://github.com/oxydavid-maxx"

    marketplace = _load(".claude-plugin/marketplace.json")
    assert marketplace["plugins"][0]["homepage"] == CANONICAL


def test_installation_docs_use_the_canonical_fork() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "github.com/oxydavid-maxx/travelwork" in readme
    assert "marketplace add git@github.com:helping-ai-workflow/tripwork.git" not in readme
