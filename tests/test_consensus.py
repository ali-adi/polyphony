"""Tests for Multi-Agent Consensus (Section 35: Multi-Agent Consensus)."""

import pytest
from orchestrator.consensus import (
    ConsensusBenefitEstimator,
    ConsensusJudge,
    Critique,
    DisagreementDetector,
    Proposal,
)


def test_consensus_benefit_estimator():
    """Verify Section 35:
    'Do not use multiple agents simply because they are available.
     Parallel reasoning should have a measurable expected benefit.'
    """
    # Simple bugfix: no consensus needed
    should_use, benefit, reason = ConsensusBenefitEstimator.evaluate_benefit(
        goal="Fix typo in README",
        is_ambiguous=False,
        stake_level="low",
    )
    assert should_use is False
    assert benefit < 0.5
    assert "avoids token waste" in reason

    # High-stakes architectural task: consensus approved
    should_use, benefit, reason = ConsensusBenefitEstimator.evaluate_benefit(
        goal="Redesign database storage from SQLite to distributed Postgres",
        is_ambiguous=True,
        stake_level="high",
    )
    assert should_use is True
    assert benefit >= 0.75
    assert "justifies multi-agent deliberation" in reason


def test_section_35_consensus_workflow():
    """Verify Section 35 flow:
    Agent A → proposal
    Agent B → independent proposal
    Agent C → critique
    Lead → synthesis
    """
    # 1. Agent A proposal
    prop_a = Proposal(
        agent_id="agent_a",
        title="In-Memory Cache with Redis Fallback",
        solution="Implement local LRU with Redis remote sync",
        tradeoffs=["Low latency", "High memory footprint"],
        confidence=0.90,
    )

    # 2. Agent B independent proposal
    prop_b = Proposal(
        agent_id="agent_b",
        title="SQLite Disk Cache",
        solution="Implement SQLite database backed cache with WAL mode",
        tradeoffs=["Durable across restarts", "Disk I/O latency"],
        confidence=0.85,
    )

    # 3. Disagreement detection
    disagreements = DisagreementDetector.detect_disagreements([prop_a, prop_b])
    assert len(disagreements) > 0
    assert any("technical components" in d for d in disagreements)

    # 4. Agent C adversarial critique
    critiques = [
        Critique(
            critic_id="agent_c",
            target_agent_id="agent_a",
            flaws=["Redis remote connection can cause network latency spikes"],
            strengths=["Blazing fast for local hits"],
            risk_score=0.25,
        ),
        Critique(
            critic_id="agent_c",
            target_agent_id="agent_b",
            flaws=["Concurrent lock contention under multi-process load"],
            strengths=["Simple deployment with no external daemon"],
            risk_score=0.45,
        ),
    ]

    # 5. Lead synthesis
    judge = ConsensusJudge(quorum_threshold=0.5)
    synthesis = judge.evaluate_and_synthesize(
        lead_id="lead_reasoner",
        proposals=[prop_a, prop_b],
        critiques=critiques,
    )

    assert synthesis.lead_id == "lead_reasoner"
    assert synthesis.chosen_proposal_id == "agent_a"  # lower risk score from critic
    assert synthesis.quorum_reached is True
    assert len(synthesis.mitigations) > 0
    assert "Redis remote connection" in synthesis.mitigations[0]
    assert "Synthesized approach" in synthesis.synthesis
