"""Multi-Agent Consensus subsystem with disagreement detection and adversarial critique (Section 35).

Section 35: Multi-Agent Consensus
For genuinely ambiguous tasks:
Agent A -> proposal
Agent B -> independent proposal
Agent C -> critique
Lead -> synthesis

Features:
- independent solutions
- adversarial review
- quorum
- judge
- disagreement detection
- measurable expected benefit gate: do not use multiple agents simply because they are available.
"""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("polyphony.consensus")


@dataclass
class Proposal:
    agent_id: str
    title: str
    solution: str
    tradeoffs: List[str] = field(default_factory=list)
    confidence: float = 0.85


@dataclass
class Critique:
    critic_id: str
    target_agent_id: str
    flaws: List[str] = field(default_factory=list)
    strengths: List[str] = field(default_factory=list)
    risk_score: float = 0.2  # 0.0 to 1.0


@dataclass
class ConsensusSynthesis:
    lead_id: str
    chosen_proposal_id: Optional[str]
    synthesis: str
    quorum_reached: bool
    agreement_score: float  # 0.0 to 1.0
    disagreements: List[str] = field(default_factory=list)
    mitigations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ConsensusBenefitEstimator:
    """Gates multi-agent consensus by requiring a measurable expected benefit (Section 35).

    'Do not use multiple agents simply because they are available.
     Parallel reasoning should have a measurable expected benefit.'
    """

    @staticmethod
    def evaluate_benefit(
        goal: str,
        is_ambiguous: bool = False,
        stake_level: str = "medium",  # "low", "medium", "high"
    ) -> Tuple[bool, float, str]:
        """Returns: (should_use_consensus, expected_benefit_score, rationale)."""
        goal_lower = goal.lower()
        ambiguous_signals = [
            "architect", "design", "evaluate tradeoff", "alternative",
            "which approach", "migrate", "consensus", "ambiguous", "redesign"
        ]
        detected_ambiguity = is_ambiguous or any(sig in goal_lower for sig in ambiguous_signals)

        if not detected_ambiguity and stake_level in ("low", "medium"):
            return (
                False,
                0.2,
                "Task is deterministic or low-ambiguity. Single agent sufficient; avoids token waste.",
            )

        if stake_level == "high" or detected_ambiguity:
            benefit_score = 0.9 if stake_level == "high" else 0.75
            return (
                True,
                benefit_score,
                f"High-stakes or ambiguous architectural task justifies multi-agent deliberation (benefit score {benefit_score}).",
            )

        return (False, 0.4, "Expected benefit does not exceed token expenditure.")


class DisagreementDetector:
    """Analyzes divergence and conflicting assumptions across independent proposals."""

    @staticmethod
    def detect_disagreements(proposals: List[Proposal]) -> List[str]:
        if len(proposals) < 2:
            return []

        disagreements = []
        p1 = proposals[0]
        p2 = proposals[1]

        # Check key technology / design mentions
        keywords_1 = set(re.findall(r"\b[A-Za-z0-9_-]{4,}\b", p1.solution.lower()))
        keywords_2 = set(re.findall(r"\b[A-Za-z0-9_-]{4,}\b", p2.solution.lower()))

        divergent_terms = (keywords_1 ^ keywords_2)
        key_tech = [t for t in divergent_terms if t in {"sqlite", "postgres", "redis", "asyncio", "threading", "rest", "grpc", "cache"}]
        if key_tech:
            disagreements.append(f"Divergence in core technical components: {', '.join(sorted(key_tech))}")

        # Check tradeoffs
        if p1.tradeoffs and p2.tradeoffs:
            t1 = set(p1.tradeoffs)
            t2 = set(p2.tradeoffs)
            diff = t1 ^ t2
            if diff:
                disagreements.append(f"Contrasting tradeoff priorities: {list(diff)[:2]}")

        return disagreements


class ConsensusJudge:
    """Evaluates proposals, adversarial critiques, and leads synthesis."""

    def __init__(self, quorum_threshold: float = 0.5):
        self.quorum_threshold = quorum_threshold

    def evaluate_and_synthesize(
        self,
        lead_id: str,
        proposals: List[Proposal],
        critiques: List[Critique],
    ) -> ConsensusSynthesis:
        """Section 35:
        Agent A -> proposal
        Agent B -> independent proposal
        Agent C -> critique
        Lead -> synthesis
        """
        if not proposals:
            return ConsensusSynthesis(
                lead_id=lead_id,
                chosen_proposal_id=None,
                synthesis="No proposals received.",
                quorum_reached=False,
                agreement_score=0.0,
            )

        disagreements = DisagreementDetector.detect_disagreements(proposals)

        # Score proposals based on confidence and critiques
        scores: Dict[str, float] = {}
        for p in proposals:
            score = p.confidence
            relevant_critiques = [c for c in critiques if c.target_agent_id == p.agent_id]
            for c in relevant_critiques:
                score -= (c.risk_score * 0.4)
                score += (len(c.strengths) * 0.05)
            scores[p.agent_id] = max(0.0, score)

        # Select best proposal
        sorted_proposals = sorted(proposals, key=lambda p: scores.get(p.agent_id, 0.0), reverse=True)
        winner = sorted_proposals[0]

        # Gather mitigations from critiques
        mitigations = []
        winner_critiques = [c for c in critiques if c.target_agent_id == winner.agent_id]
        for c in winner_critiques:
            for flaw in c.flaws:
                mitigations.append(f"Mitigate '{flaw}' identified in adversarial review")

        agreement_score = 1.0 - (len(disagreements) * 0.25)
        agreement_score = max(0.2, min(1.0, agreement_score))
        quorum_reached = agreement_score >= self.quorum_threshold

        synthesis_text = (
            f"Synthesized approach based on '{winner.agent_id}' ({winner.title}). "
            f"Adversarial review by critic incorporated {len(mitigations)} mitigations."
        )

        return ConsensusSynthesis(
            lead_id=lead_id,
            chosen_proposal_id=winner.agent_id,
            synthesis=synthesis_text,
            quorum_reached=quorum_reached,
            agreement_score=round(agreement_score, 2),
            disagreements=disagreements,
            mitigations=mitigations,
        )
