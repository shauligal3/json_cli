"""Tests for :class:`jsoncli.Document`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jsoncli import Document, JsonCliError, Schema


def test_statements_flatten_document(document: Document) -> None:
    statements = document.statements()
    assert "set hostname edge-router-1" in statements
    assert "set logging remote-host 10.0.0.6" in statements
    assert "set interfaces eth0 mtu 1500" in statements
    assert "set users alice role admin" in statements
    assert not any(s.startswith("set schema") for s in statements)


def test_statements_of_subtree(document: Document) -> None:
    assert document.statements(["users", "bob"]) == ["set users bob role viewer"]
    assert document.statements(["missing"]) == []


def test_statements_keep_named_element_without_children() -> None:
    doc = Document({"interfaces": [{"name": "lo"}]})
    assert doc.statements() == ["set interfaces lo"]


def test_set_creates_path(document: Document, schema: Schema) -> None:
    document.set_value("interfaces eth2 mtu 1400".split(), schema)
    assert document.read(["interfaces", "eth2"]) == {"name": "eth2", "mtu": 1400}
    document.set_value("users carol role operator".split(), schema)
    assert document.read(["users", "carol"]) == {"role": "operator"}


def test_set_validates_values(document: Document, schema: Schema) -> None:
    with pytest.raises(JsonCliError, match="number"):
        document.set_value("interfaces eth0 mtu big".split(), schema)
    with pytest.raises(JsonCliError, match="expecting one of"):
        document.set_value("logging level loud".split(), schema)
    with pytest.raises(JsonCliError, match="missing value"):
        document.set_value(["hostname"], schema)
    with pytest.raises(JsonCliError, match="unknown statement"):
        document.set_value(["nonsense"], schema)


def test_set_negative_integer_and_bool(document: Document, schema: Schema) -> None:
    document.set_value("interfaces eth1 mtu -1".split(), schema)
    document.set_value("logging verbose".split(), schema)
    assert document.read(["interfaces", "eth1", "mtu"]) == -1
    assert document.read(["logging", "verbose"]) == 1


def test_set_multi_accumulates_distinct_values(document: Document, schema: Schema) -> None:
    document.set_value("interfaces eth1 address 198.51.100.1/24".split(), schema)
    assert document.read(["interfaces", "eth1", "address"]) == "198.51.100.1/24"
    document.set_value("interfaces eth1 address 203.0.113.9/24".split(), schema)
    document.set_value("interfaces eth1 address 203.0.113.9/24".split(), schema)
    assert document.read(["interfaces", "eth1", "address"]) == [
        "198.51.100.1/24",
        "203.0.113.9/24",
    ]


def test_set_value_with_spaces(document: Document, schema: Schema) -> None:
    document.set_value("interfaces eth0 description link to core".split(), schema)
    assert document.read(["interfaces", "eth0", "description"]) == "link to core"


def test_remove_object_member_returns_clip(document: Document) -> None:
    clip = document.remove(["users", "alice", "shell"])
    assert clip == {"shell": "/bin/bash"}
    assert "shell" not in document.read(["users", "alice"])


def test_remove_list_element(document: Document) -> None:
    clip = document.remove(["interfaces", "eth1"])
    assert clip["name"] == "eth1"
    assert document.children(document.read(["interfaces"])) == ["eth0"]


def test_remove_multi_value_and_prune(document: Document) -> None:
    assert document.remove(["logging", "remote-host", "10.0.0.5"]) is None
    assert document.read(["logging", "remote-host"]) == ["10.0.0.6"]
    document.remove(["logging", "remote-host", "10.0.0.6"])
    document.remove(["logging", "level", "info"])
    # Every branch emptied by the removals is gone.
    assert document.read(["logging"]) is None


def test_remove_prunes_empty_named_element(document: Document) -> None:
    document.remove(["users", "bob", "role"])
    assert document.read(["users", "bob"]) is None


def test_remove_errors(document: Document) -> None:
    with pytest.raises(JsonCliError, match="unknown statement"):
        document.remove(["users", "nobody"])
    with pytest.raises(JsonCliError, match="unknown statement"):
        document.remove(["hostname", "wrong-value"])
    with pytest.raises(JsonCliError, match="reserved"):
        document.remove(["interfaces", "eth0", "name"])


def test_paste_into_list_positions(document: Document, schema: Schema) -> None:
    clip = document.remove(["interfaces", "eth1"])
    document.paste(["interfaces"], schema, clip, anchor="eth0", before=True)
    assert document.children(document.read(["interfaces"])) == ["eth1", "eth0"]
    clip = document.copy(["interfaces"], "eth0")
    document.paste(["interfaces"], schema, clip, new_key="eth9", before=True)
    assert document.children(document.read(["interfaces"])) == ["eth9", "eth1", "eth0"]


def test_paste_rejects_duplicates_and_illegal_keys(document: Document, schema: Schema) -> None:
    clip = document.copy(["users"], "alice")
    with pytest.raises(JsonCliError, match="already exists"):
        document.paste(["users"], schema, clip)
    with pytest.raises(JsonCliError, match="illegal"):
        document.paste([], schema, {"bogus": 1})


def test_rename_keeps_position(document: Document, schema: Schema) -> None:
    document.rename(["users"], schema, "alice", "ann")
    assert document.children(document.read(["users"])) == ["ann", "bob"]
    document.rename(["interfaces"], schema, "eth1", "eth5")
    assert document.children(document.read(["interfaces"])) == ["eth0", "eth5"]
    with pytest.raises(JsonCliError, match="already exists"):
        document.rename(["interfaces"], schema, "eth0", "eth5")
    with pytest.raises(JsonCliError, match="unknown key"):
        document.rename(["users"], schema, "zed", "zoe")


def test_copy_is_deep(document: Document) -> None:
    clip = document.copy(["users"], "alice")
    clip["alice"]["role"] = "viewer"
    assert document.read(["users", "alice", "role"]) == "admin"


def test_diff(document: Document, schema: Schema) -> None:
    original = Document(json.loads(json.dumps(document.root)))
    document.set_value("hostname edge-router-2".split(), schema)
    removed, added = document.diff(original)
    assert removed == ["set hostname edge-router-1"]
    assert added == ["set hostname edge-router-2"]


def test_save_and_reload_round_trip(document: Document, tmp_path: Path) -> None:
    target = tmp_path / "copy.json"
    document.save(target)
    assert document.path == target
    assert Document.load(target).root == document.root
    assert target.read_text().endswith("}\n")


def test_save_without_path_fails() -> None:
    with pytest.raises(JsonCliError, match="missing file name"):
        Document().save()


def test_load_errors(tmp_path: Path) -> None:
    with pytest.raises(JsonCliError, match="cannot open"):
        Document.load(tmp_path / "missing.json")
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    with pytest.raises(JsonCliError, match="bad JSON"):
        Document.load(bad)
