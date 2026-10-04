"""Tests for :class:`jsoncli.Schema`."""

from __future__ import annotations

from pathlib import Path

import pytest

from jsoncli import JsonCliError, Schema


def test_lookup_fixed_and_collection_keys(schema: Schema) -> None:
    assert schema.lookup(["hostname"]) == {"type": "string"}
    assert schema.lookup(["interfaces", "anything", "mtu"]) == {"type": "integer"}
    assert schema.lookup(["users", "carol", "role"])["type"] == "enum"
    assert schema.lookup([]) is schema.root


def test_lookup_unknown_returns_empty(schema: Schema) -> None:
    assert schema.lookup(["nope"]) == {}
    assert schema.lookup(["hostname", "extra", "words"]) == {}


def test_step_ignores_non_object_values(schema: Schema) -> None:
    # "is-schema" maps to 1 and "type" maps to a string: neither is a keyword.
    assert schema.step(schema.root, "is-schema") == {}
    assert schema.step({"type": "string"}, "type") == {}


def test_parse_splits_path_key_and_value(schema: Schema) -> None:
    parsed = schema.parse(["interfaces", "eth2", "description", "to", "core"])
    assert parsed is not None
    node, path, key, value = parsed
    assert node == {"type": "string"}
    assert path == ["interfaces", "eth2"]
    assert key == "description"
    assert value == "to core"


def test_parse_branch_and_invalid(schema: Schema) -> None:
    assert schema.parse(["interfaces", "eth2"]) == (
        schema.lookup(["interfaces", "x"]),
        ["interfaces", "eth2"],
        None,
        None,
    )
    assert schema.parse(["bogus"]) is None


def test_keywords_hide_reserved_and_private_keys(schema: Schema) -> None:
    assert Schema.keywords(schema.root) == ["hostname", "logging", "interfaces", "users"]


def test_resolve_search_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lib = tmp_path / "lib"
    lib.mkdir()
    (lib / "s.json").write_text("{}")
    monkeypatch.chdir(tmp_path)
    assert Schema.resolve("s.json", search_path=str(lib)) == lib / "s.json"
    assert Schema.resolve("s.json", base_dir=lib, search_path="") == lib / "s.json"
    monkeypatch.setenv("JSONCLI_SCHEMA_PATH", str(lib))
    assert Schema.resolve("s.json") == lib / "s.json"


def test_resolve_missing_schema_explains_env_var(tmp_path: Path) -> None:
    with pytest.raises(JsonCliError, match="JSONCLI_SCHEMA_PATH"):
        Schema.resolve("missing.json", base_dir=tmp_path, search_path="")


def test_from_file_rejects_non_object(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("[1, 2]")
    with pytest.raises(JsonCliError, match="JSON object"):
        Schema.from_file(path)
