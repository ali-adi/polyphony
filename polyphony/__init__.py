"""Polyphony: an MCP server that hands isolated coding tasks to agent CLIs."""

from importlib.metadata import PackageNotFoundError, version as _pkg_version

try:
    __version__ = _pkg_version("polyphony")
except PackageNotFoundError:  # a source checkout that was never pip installed
    __version__ = "0.0.0+unknown"
