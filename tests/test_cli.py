"""Tests for the command-line entry point."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jsoncli.cli import main, open_session


def test_init_creates_document(tmp_path: Path) -> None:
    target = tmp_path / "new.json"
    assert main(["--init", "--schema", "router.schema.json", str(target)]) == 0
    assert json.loads(target.read_text()) == {"schema": "router.schema.json"}
    assert main(["--init", "--schema", "router.schema.json", str(target)]) == 1


def test_init_requires_schema(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        main(["--init", str(tmp_path / "new.json")])


def test_open_document_resolves_schema_next_to_it(
    example_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(example_dir.parent)
    schema, document = open_session(example_dir / "router.json")
    assert schema.name == "router.schema.json"
    assert document.read(["hostname"]) == "edge-router-1"


def test_open_schema_starts_new_document(example_dir: Path) -> None:
    schema_file = example_dir / "router.schema.json"
    schema, document = open_session(schema_file)
    assert document.path is None
    assert document.root == {"schema": str(schema_file)}
    assert "hostname" in schema.root


def test_open_invalid_file_reports_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "plain.json"
    path.write_text("{}")
    assert main([str(path)]) == 1
    assert "neither a schema" in capsys.readouterr().err
