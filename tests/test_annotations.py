"""Type annotations must actually resolve.

`from __future__ import annotations` defers evaluation, so an undefined
name in a signature is invisible until something introspects it. These
functions are the ones most likely to be introspected, and
StateManager.create_task runs on every task.
"""

import typing

import pytest

from executors.router import ExecutorRouter
from orchestrator.main import _is_underspecified_delegation
from orchestrator.state import StateManager


@pytest.mark.parametrize(
    "func",
    [
        StateManager.create_task,
        ExecutorRouter.bind_role,
        ExecutorRouter.execute_role,
        _is_underspecified_delegation,
    ],
    ids=["create_task", "bind_role", "execute_role", "is_underspecified_delegation"],
)
def test_annotations_resolve(func):
    typing.get_type_hints(func)


def test_cli_version_matches_package_metadata():
    """The CLI must not hardcode a version that can drift from pyproject."""
    from importlib.metadata import version as pkg_version

    from click.testing import CliRunner

    from orchestrator.cli import cli

    result = CliRunner().invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert pkg_version("polyphony") in result.output
