from pathlib import Path

import pytest

from codereview.corpus_prep import build_corpus

REPO_ROOT = Path(__file__).resolve().parent.parent


def _write_fixture_source(root: Path) -> Path:
    """Write a tiny multi-file source tree and return its root."""
    src = root / "fixture-src"
    (src / "pkg").mkdir(parents=True)
    (src / "pkg" / "b.py").write_text("def b():\n    return 2\n")
    (src / "a.py").write_text("def a():\n    return 1\n")
    (src / "ignored.md").write_text("# not python or ts\n")
    (src / "ui.ts").write_text("export const x = 1;\n")
    return src


def _write_sources_toml(path: Path, source_root: Path, name: str = "fixture") -> None:
    path.write_text(
        f"""
extensions = [".py", ".ts"]

[[sources]]
name = "{name}"
type = "path"
path = "{source_root}"
license = "owner"
""",
        encoding="utf-8",
    )


def test_build_is_deterministic_across_runs(tmp_path: Path) -> None:
    src = _write_fixture_source(tmp_path)
    sources_toml = tmp_path / "sources.toml"
    _write_sources_toml(sources_toml, src)

    out_a = tmp_path / "a.txt"
    out_b = tmp_path / "b.txt"

    build_corpus(sources_toml, out_a)
    build_corpus(sources_toml, out_b)

    assert out_a.read_bytes() == out_b.read_bytes()
    assert out_a.stat().st_size > 0


def test_build_orders_files_by_relative_path(tmp_path: Path) -> None:
    src = _write_fixture_source(tmp_path)
    sources_toml = tmp_path / "sources.toml"
    _write_sources_toml(sources_toml, src)
    out = tmp_path / "corpus.txt"

    build_corpus(sources_toml, out)
    text = out.read_text(encoding="utf-8")

    headers = [line for line in text.splitlines() if line.startswith("# === ")]
    assert headers == [
        "# === fixture/a.py ===",
        "# === fixture/pkg/b.py ===",
        "# === fixture/ui.ts ===",
    ]


def test_build_orders_sources_by_name(tmp_path: Path) -> None:
    src_a = tmp_path / "alpha"
    src_a.mkdir()
    (src_a / "x.py").write_text("# alpha\n")
    src_b = tmp_path / "bravo"
    src_b.mkdir()
    (src_b / "x.py").write_text("# bravo\n")

    sources_toml = tmp_path / "sources.toml"
    sources_toml.write_text(
        f"""
extensions = [".py"]

[[sources]]
name = "bravo"
type = "path"
path = "{src_b}"

[[sources]]
name = "alpha"
type = "path"
path = "{src_a}"
""",
        encoding="utf-8",
    )
    out = tmp_path / "corpus.txt"
    build_corpus(sources_toml, out)
    text = out.read_text(encoding="utf-8")
    assert text.index("alpha") < text.index("bravo")


def test_build_filters_by_extension(tmp_path: Path) -> None:
    src = _write_fixture_source(tmp_path)
    sources_toml = tmp_path / "sources.toml"
    _write_sources_toml(sources_toml, src)
    out = tmp_path / "corpus.txt"

    build_corpus(sources_toml, out)
    text = out.read_text(encoding="utf-8")

    assert "ignored.md" not in text
    assert "# not python or ts" not in text


@pytest.mark.parametrize(
    "ignored_dir",
    [
        "node_modules",
        ".venv",
        "dist",
        "build",
        ".git",
        "__pycache__",
        ".pytest_cache",
        ".next",
        "coverage",
    ],
)
def test_build_prunes_default_ignore_dirs(tmp_path: Path, ignored_dir: str) -> None:
    """Files matching the extension list but living under a default-ignored
    dir name (at any depth) must not appear in the corpus."""
    src = tmp_path / "src"
    (src / "keep").mkdir(parents=True)
    (src / "keep" / "good.py").write_text("# keep this\nKEEP_TOKEN = 1\n")
    # Drop a file with the same extension inside the ignored dir
    (src / ignored_dir).mkdir(parents=True)
    (src / ignored_dir / "trash.py").write_text("# should be pruned\nTRASH_TOKEN = 1\n")
    # And nested deeper
    (src / "pkg" / ignored_dir / "subdir").mkdir(parents=True)
    (src / "pkg" / ignored_dir / "subdir" / "deep.py").write_text("DEEP_TRASH = 1\n")

    sources_toml = tmp_path / "sources.toml"
    _write_sources_toml(sources_toml, src)
    out = tmp_path / "corpus.txt"
    build_corpus(sources_toml, out)
    text = out.read_text(encoding="utf-8")

    assert "KEEP_TOKEN" in text
    assert "TRASH_TOKEN" not in text, f"failed to prune top-level {ignored_dir}/"
    assert "DEEP_TRASH" not in text, f"failed to prune nested */{ignored_dir}/*"
    assert ignored_dir not in text, f"ignored dir name leaked into corpus via {ignored_dir}/"


def test_build_ignore_dirs_override_via_toml(tmp_path: Path) -> None:
    """A sources.toml `ignore_dirs` array replaces the default set."""
    src = tmp_path / "src"
    # Put a .py inside node_modules (would normally be pruned)
    (src / "node_modules").mkdir(parents=True)
    (src / "node_modules" / "package.py").write_text("NODE_PKG = 1\n")
    # And under a custom-ignored dir
    (src / "experiments").mkdir(parents=True)
    (src / "experiments" / "wip.py").write_text("WIP = 1\n")

    sources_toml = tmp_path / "sources.toml"
    sources_toml.write_text(
        f"""
extensions = [".py"]
ignore_dirs = ["experiments"]

[[sources]]
name = "fixture"
type = "path"
path = "{src}"
license = "owner"
""",
        encoding="utf-8",
    )
    out = tmp_path / "corpus.txt"
    build_corpus(sources_toml, out)
    text = out.read_text(encoding="utf-8")

    # node_modules content NOW survives (override replaces default set)
    assert "NODE_PKG" in text, "override should disable default node_modules pruning"
    # experiments/ is the only thing pruned by the override
    assert "WIP" not in text, "explicit override dir was not pruned"


def test_build_owner_corpus_drops_dramatically_with_pruning(tmp_path: Path) -> None:
    """Mimics the real owner-corpus case: a small project tree with a giant
    fake node_modules. Without pruning the corpus is dominated by junk;
    with default pruning, only the real source survives."""
    src = tmp_path / "owner-repo"
    (src / "src").mkdir(parents=True)
    (src / "src" / "main.py").write_text("def main():\n    print('hi')\n" * 5)

    # Fake a node_modules dir with many large .d.ts files
    nm = src / "node_modules" / "@some-org" / "lib" / "src"
    nm.mkdir(parents=True)
    for i in range(20):
        (nm / f"types-{i}.ts").write_text("// junk\n" * 500)

    sources_toml = tmp_path / "sources.toml"
    _write_sources_toml(sources_toml, src)
    out = tmp_path / "corpus.txt"
    size_with_pruning = build_corpus(sources_toml, out)

    # Now turn off pruning explicitly. Write the file from scratch so the
    # top-level ignore_dirs override lands above the [[sources]] table.
    sources_toml.write_text(
        f"""
extensions = [".py", ".ts"]
ignore_dirs = []

[[sources]]
name = "fixture"
type = "path"
path = "{src}"
license = "owner"
""",
        encoding="utf-8",
    )
    out_unpruned = tmp_path / "corpus-unpruned.txt"
    size_without_pruning = build_corpus(sources_toml, out_unpruned)

    # Realistic ratio for the fixture: ~10 KB junk vs ~150 B real source.
    assert size_without_pruning > size_with_pruning * 10


def test_build_with_no_sources_writes_empty_file(tmp_path: Path) -> None:
    sources_toml = tmp_path / "sources.toml"
    sources_toml.write_text('extensions = [".py"]\n', encoding="utf-8")
    out = tmp_path / "empty.txt"
    size = build_corpus(sources_toml, out)
    assert size == 0
    assert out.read_text() == ""


def test_build_rejects_missing_path_source(tmp_path: Path) -> None:
    sources_toml = tmp_path / "sources.toml"
    sources_toml.write_text(
        f"""
extensions = [".py"]

[[sources]]
name = "missing"
type = "path"
path = "{tmp_path / 'does-not-exist'}"
""",
        encoding="utf-8",
    )
    with pytest.raises(FileNotFoundError):
        build_corpus(sources_toml, tmp_path / "out.txt")


def test_real_sources_toml_parses_with_owner_and_public_entries() -> None:
    """The committed sources.toml should parse cleanly and contain both
    license-exempt owner entries and MIT/Apache-2.0 public entries
    (ADR-018). This is a structural check — it does not actually run
    build_corpus, because that would clone large repos in CI."""
    import tomllib

    real_toml = REPO_ROOT / "data" / "scripts" / "sources.toml"
    data = tomllib.loads(real_toml.read_text(encoding="utf-8"))

    assert ".py" in data["extensions"]
    assert ".ts" in data["extensions"]

    sources = data["sources"]
    assert len(sources) > 0

    licenses = {s["license"] for s in sources}
    # Owner entries are license-exempt; public entries must be MIT or Apache-2.0
    public_licenses = licenses - {"owner"}
    assert public_licenses.issubset({"MIT", "Apache-2.0"}), (
        f"sources.toml has non-permissive public licenses: {public_licenses}"
    )

    # Every entry has the required fields for its type
    for s in sources:
        assert "name" in s and "type" in s and "license" in s
        if s["type"] == "path":
            assert "path" in s
        elif s["type"] == "git":
            assert "url" in s and "ref" in s
        else:
            raise AssertionError(f"unknown source type: {s['type']}")
