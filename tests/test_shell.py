"""Tests for :class:`jsoncli.Shell`, driven through its command interface."""

from __future__ import annotations

from tests.conftest import ShellHarness


def test_set_and_show(harness: ShellHarness) -> None:
    harness.run("set interfaces eth2 mtu 1400")
    output = harness.run("show interfaces eth2")
    assert output.strip() == "set interfaces eth2 mtu 1400"


def test_errors_are_printed_not_raised(harness: ShellHarness) -> None:
    assert "expecting a number" in harness.run("set interfaces eth0 mtu many")
    assert "unknown statement" in harness.run("rm users nobody")


def test_cd_makes_commands_relative(harness: ShellHarness) -> None:
    harness.run("cd interfaces eth0")
    assert harness.shell.prompt == "router.json@interfaces eth0# "
    harness.run("set mtu 1280")
    assert harness.document.read(["interfaces", "eth0", "mtu"]) == 1280
    harness.run("cd ..")
    assert harness.shell.edit_root == ["interfaces"]
    harness.run("cd")
    assert harness.shell.prompt == "router.json@ "


def test_cd_into_leaf_is_refused(harness: ShellHarness) -> None:
    assert "cannot cd into leaf" in harness.run("cd hostname")
    assert harness.shell.edit_root == []


def test_abbreviated_commands(harness: ShellHarness) -> None:
    assert harness.run("gr alice").strip() == "\n".join(
        ["set users alice role admin", "set users alice shell /bin/bash"]
    )
    assert "ambiguous" in harness.run("c users")
    assert "unknown command" in harness.run("frobnicate")


def test_rm_and_paste(harness: ShellHarness) -> None:
    harness.run("rm interfaces eth0")
    harness.run("cd interfaces")
    harness.run("paste after eth1")
    assert harness.run("ls").split() == ["eth1", "eth0"]
    assert "clipboard is empty" in harness.run("paste")


def test_cp_and_mv(harness: ShellHarness) -> None:
    harness.run("cd users")
    harness.run("cp alice carol")
    harness.run("mv bob bert")
    assert harness.run("ls").split() == ["alice", "bert", "carol"]
    assert harness.document.read(["users", "carol", "role"]) == "admin"


def test_json_and_schema_commands(harness: ShellHarness) -> None:
    assert '"role": "viewer"' in harness.run("json users bob")
    assert '"integer"' in harness.run("schema interfaces x mtu")
    assert "unknown path" in harness.run("json nothing here")


def test_completion_uses_schema_and_document(harness: ShellHarness) -> None:
    shell = harness.shell
    assert shell.complete_set("", "set ", 4, 4) == ["hostname", "logging", "interfaces", "users"]
    assert shell.complete_set("e", "set interfaces e", 15, 16) == ["eth0", "eth1"]
    assert shell.complete_set("", "set interfaces eth0 ", 20, 20) == [
        "description",
        "mtu",
        "address",
        "enabled",
    ]
    assert shell.complete_set("w", "set logging level w", 18, 19) == ["warning"]
    assert shell.completedefault("a", "us users a", 9, 10) == []
    assert shell.completedefault("a", "se users a", 9, 10) == ["alice"]


def test_save_diff_and_quit(harness: ShellHarness) -> None:
    assert "no differences" in harness.run("diff")
    assert harness.run("quit") == ""
    assert harness.last_stop

    harness.run("set hostname core-1")
    assert "Added statements:\nset hostname core-1" in harness.run("diff")
    harness.run("quit", answer="n")
    assert not harness.last_stop

    assert "saved" in harness.run("save")
    assert "no differences" in harness.run("diff")
    harness.run("exit")
    assert harness.last_stop


def test_load_asks_before_discarding(harness: ShellHarness) -> None:
    harness.run("set hostname core-1")
    harness.run("load", answer="no")
    assert harness.document.read(["hostname"]) == "core-1"
    harness.run("load", answer="yes")
    assert harness.document.read(["hostname"]) == "edge-router-1"


def test_eof_quits_when_clean(harness: ShellHarness) -> None:
    harness.run("EOF")
    assert harness.last_stop
