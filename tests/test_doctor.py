"""Tests for polyphony doctor diagnostic subsystem (Section 11)."""

from click.testing import CliRunner
import pytest

from orchestrator.cli import cli
from orchestrator.doctor import CheckStatus, DoctorReport, PolyphonyDoctor


def test_doctor_runs_16_checks():
    doctor = PolyphonyDoctor()
    report = doctor.run_all_checks()
    assert len(report.checks) == 16

    names = [c.name for c in report.checks]
    assert "Polyphony Installation" in names
    assert "Python Environment" in names
    assert "Git" in names
    assert "Claude CLI" in names
    assert "AGY CLI" in names
    assert "Cursor CLI" in names
    assert "Authentication" in names
    assert "Model Configuration" in names
    assert "Project Registration" in names
    assert "State Directory" in names
    assert "Permissions" in names
    assert "Disk Space" in names
    assert "Hooks" in names
    assert "Safety Configuration" in names
    assert "Migration State" in names
    assert "Executor Health" in names


def test_doctor_report_counts():
    doctor = PolyphonyDoctor()
    report = doctor.run_all_checks()
    counts = report.summary_counts
    assert "OK" in counts
    assert "WARNING" in counts
    assert "ERROR" in counts
    assert "BLOCKED" in counts
    assert sum(counts.values()) == 16


def test_doctor_cli():
    runner = CliRunner()
    res = runner.invoke(cli, ["doctor"])
    assert "Running Polyphony System Doctor" in res.output
    assert "Summary:" in res.output
    assert "[OK" in res.output or "[WARN" in res.output
