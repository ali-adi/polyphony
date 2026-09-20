"""Prompt and context regression testing framework (Section 45).

Tests that context builders and prompt constructors treat context construction like code:
- required information is present
- irrelevant information is excluded
- budgets are respected
- structured outputs remain valid
- sensitive information is redacted
- context compression preserves important facts
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
import yaml


# Secret detection regexes
SECRET_PATTERNS = [
    re.compile(r"sk-[a-zA-Z0-9]{20,}"),                          # OpenAI-style keys
    re.compile(r"AKIA[0-9A-Z]{16}"),                             # AWS access keys
    re.compile(r"(?i)bearer\s+[a-zA-Z0-9_\-\.]{20,}"),           # Bearer tokens
    re.compile(r"(?i)(?:password|secret|api[_-]?key)\s*[:=]\s*['\"][^'\"]{6,}['\"]"),  # Explicit passwords/secrets
    re.compile(r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----"),      # Private keys
]


@dataclass
class PromptTestSpec:
    name: str
    required_sections: List[str] = field(default_factory=list)
    required_substrings: List[str] = field(default_factory=list)
    forbidden_substrings: List[str] = field(default_factory=list)
    max_tokens: Optional[int] = None
    max_characters: Optional[int] = None
    require_redacted_secrets: bool = True
    required_facts_preserved: List[str] = field(default_factory=list)
    structured_keys: List[str] = field(default_factory=list)


@dataclass
class PromptValidationResult:
    spec_name: str
    passed: bool
    violations: List[str] = field(default_factory=list)
    estimated_tokens: int = 0
    preserved_facts: List[str] = field(default_factory=list)
    lost_facts: List[str] = field(default_factory=list)


class PromptContextValidator:
    """Validates constructed prompts and contexts against quality, safety, and budget rules."""

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Heuristic token estimate based on word and character counts."""
        words = text.split()
        return max(len(words), int(len(text) / 4))

    @classmethod
    def validate(cls, text: str, spec: PromptTestSpec) -> PromptValidationResult:
        violations: List[str] = []
        estimated_tokens = cls.estimate_tokens(text)

        # 1. Check required sections
        for section in spec.required_sections:
            pattern = re.compile(rf"#+\s+{re.escape(section)}", re.IGNORECASE)
            if not pattern.search(text):
                violations.append(f"Missing required section: '{section}'")

        # 2. Check required substrings
        for sub in spec.required_substrings:
            if sub not in text:
                violations.append(f"Missing required content: '{sub}'")

        # 3. Check forbidden / irrelevant substrings
        for forbidden in spec.forbidden_substrings:
            if forbidden in text:
                violations.append(f"Contains forbidden/irrelevant content: '{forbidden}'")

        # 4. Budget constraints
        if spec.max_characters is not None and len(text) > spec.max_characters:
            violations.append(
                f"Character budget exceeded: {len(text)} chars (limit: {spec.max_characters})"
            )
        if spec.max_tokens is not None and estimated_tokens > spec.max_tokens:
            violations.append(
                f"Token budget exceeded: ~{estimated_tokens} tokens (limit: {spec.max_tokens})"
            )

        # 5. Sensitive information redaction
        if spec.require_redacted_secrets:
            for pattern in SECRET_PATTERNS:
                match = pattern.search(text)
                if match:
                    violations.append(f"Unredacted sensitive credential detected matching pattern: {pattern.pattern}")

        # 6. Fact preservation check
        preserved: List[str] = []
        lost: List[str] = []
        for fact in spec.required_facts_preserved:
            if fact.lower() in text.lower():
                preserved.append(fact)
            else:
                lost.append(fact)
                violations.append(f"Important fact lost in context: '{fact}'")

        # 7. Structured output check
        if spec.structured_keys:
            try:
                parsed = yaml.safe_load(text)
                if not isinstance(parsed, dict):
                    violations.append("Structured output is not a valid YAML dictionary")
                else:
                    for key in spec.structured_keys:
                        if key not in parsed:
                            violations.append(f"Missing required key: '{key}'")
            except Exception as e:
                violations.append(f"Failed to parse structured output: {e}")

        return PromptValidationResult(
            spec_name=spec.name,
            passed=len(violations) == 0,
            violations=violations,
            estimated_tokens=estimated_tokens,
            preserved_facts=preserved,
            lost_facts=lost,
        )

    @classmethod
    def test_compression_fidelity(
        cls,
        original_context: str,
        compressed_context: str,
        key_facts: List[str],
        max_compressed_ratio: float = 0.5,
    ) -> PromptValidationResult:
        """Tests that a compression step achieves budget reduction while preserving core facts."""
        violations = []
        original_len = len(original_context)
        compressed_len = len(compressed_context)

        if original_len > 0:
            compression_ratio = compressed_len / original_len
            if compression_ratio > max_compressed_ratio:
                violations.append(
                    f"Compression ratio too high: {compression_ratio:.2f} (expected <= {max_compressed_ratio})"
                )

        preserved = []
        lost = []
        for fact in key_facts:
            if fact.lower() in compressed_context.lower():
                preserved.append(fact)
            else:
                lost.append(fact)
                violations.append(f"Fact lost during compression: '{fact}'")

        return PromptValidationResult(
            spec_name="compression_fidelity_test",
            passed=len(violations) == 0,
            violations=violations,
            estimated_tokens=cls.estimate_tokens(compressed_context),
            preserved_facts=preserved,
            lost_facts=lost,
        )
