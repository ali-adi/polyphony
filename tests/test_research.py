"""Tests for Research Workflows, Experiment Registry, and Reproducibility (Sections 37, 38, & 39)."""

import tempfile
from pathlib import Path
import yaml
import pytest

from orchestrator.research import (
    ExperimentRecord,
    ExperimentRegistry,
    ReproducibilityPackage,
    ResearchProvenanceClaim,
    ResearchWorkflow,
)


def test_section_37_research_pipeline_and_provenance():
    """Verify Section 37 workflow:
    RESEARCH
    → query decomposition
    → source discovery
    → source extraction
    → evidence normalization
    → synthesis
    → uncertainty
    → recommendations for implementation
    """
    sources = [
        {"uri": "https://github.com/astral-sh/uv/releases/v0.3.0", "type": "changelogs", "title": "UV 0.3.0"},
        {"uri": "https://docs.pytest.org/en/stable/how-to/fixtures.html", "type": "documentation", "title": "Pytest Fixtures"},
        {"uri": "https://github.com/pytest-dev/pytest/issues/123", "type": "issues", "title": "Fixture scope issue"},
    ]

    report = ResearchWorkflow.run_pipeline(
        query="Migrate to fast package manager and modernize test fixtures",
        sources_provider=sources,
    )

    # 1. Query decomposition
    assert len(report.subqueries) >= 3
    # 2. Source discovery
    assert len(report.sources_discovered) == 3
    # 3. Source extraction with provenance
    assert len(report.provenance_claims) == 3
    for claim in report.provenance_claims:
        assert claim.source_uri, "Claim must have source URI"
        assert claim.source_type in {"changelogs", "documentation", "issues"}
        assert claim.extracted_text, "Claim must have extracted text"
    # 4. Evidence normalization
    assert len(report.normalized_evidence) == 3
    # 5. Synthesis
    assert "Synthesized research" in report.synthesis
    # 6. Uncertainty
    assert len(report.uncertainties) > 0
    # 7. Recommendations
    assert len(report.implementation_recommendations) > 0


def test_section_38_and_39_experiment_registry_and_reproducibility():
    """Verify Section 38 YAML format & Section 39 reproducibility:
    experiment:
      name:
      hypothesis:
      baseline:
      candidates:
      configuration:
      model:
      dataset:
      metrics:
      runtime:
      executor:
      result:
      artifacts:
      reproducibility:
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_path = Path(tmpdir)
        registry = ExperimentRegistry(storage_dir=storage_path)

        exp = registry.register(
            name="exp_tree_sitter_chunking",
            hypothesis="AST chunking improves lead reasoner recall by 15%",
            baseline="naive_sliding_window",
            candidates=["tree_sitter_python", "tree_sitter_ast_smart"],
            configuration={"max_chunk_tokens": 512, "overlap": 64},
            model="claude-3-7-sonnet",
            dataset="swe_bench_lite_subset",
            metrics={"recall": 0.88, "precision": 0.92, "f1": 0.90},
            runtime=14.2,
            executor="claude",
            result="Hypothesis confirmed: 18% improvement over baseline",
            artifacts=["benchmarks/results/recall_curve.png"],
            source_references=["https://arxiv.org/abs/2401.00000"],
            random_seeds={"seed": 42, "torch_seed": 1337},
        )

        yaml_str = exp.to_yaml()
        data = yaml.safe_load(yaml_str)
        e = data["experiment"]

        expected_fields = [
            "name", "hypothesis", "baseline", "candidates", "configuration",
            "model", "dataset", "metrics", "runtime", "executor", "result",
            "artifacts", "reproducibility"
        ]
        for field in expected_fields:
            assert field in e, f"Missing field {field} in experiment YAML"

        repro = e["reproducibility"]
        repro_fields = [
            "code_version", "config", "model", "dataset", "dependencies",
            "random_seeds", "environment", "executor", "metrics",
            "artifacts", "source_references"
        ]
        for r_field in repro_fields:
            assert r_field in repro, f"Missing reproducibility field {r_field}"

        # Verify reload from disk
        reloaded_registry = ExperimentRegistry(storage_dir=storage_path)
        loaded = reloaded_registry.get("exp_tree_sitter_chunking")
        assert loaded is not None
        assert loaded.metrics["recall"] == 0.88
        assert loaded.reproducibility.random_seeds["seed"] == 42
