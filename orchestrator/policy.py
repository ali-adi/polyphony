"""Broad policy layer, security expansion, and human approval policy engine (Sections 40 & 41).

Section 40: Security Expansion
- Prompt Injection defense: Treat external/untrusted content as data, not policy.
- Secrets Detection: API keys, tokens, passwords, credentials, private keys.
- Sensitive Data: PHI/patient data, production data, credentials, confidential company material.
- Network Policy: allowed domains, blocked domains, offline mode, research mode.
- Least Privilege: restrict executor permissions.

Section 41: Human Approval Policy Engine
Risk Levels:
- LOW: read files, run tests -> ALLOW
- MEDIUM: edit source, install dependency -> ALLOW / ASK
- HIGH: modify database, alter infrastructure, change security policy, external communication -> ASK
- CRITICAL: production deployment, credential changes, destructive operations -> BLOCK / ASK
Policy outcomes:
- ALLOW
- ASK
- BLOCK
"""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

logger = logging.getLogger("polyphony.policy")


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class PolicyAction(str, Enum):
    ALLOW = "ALLOW"
    ASK = "ASK"
    BLOCK = "BLOCK"


@dataclass
class ApprovalDecision:
    action: PolicyAction
    risk_level: RiskLevel
    reason: str
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["action"] = self.action.value
        d["risk_level"] = self.risk_level.value
        return d


class PromptInjectionDetector:
    """Detects and isolates prompt injection attempts in untrusted content (Section 40)."""

    INJECTION_PATTERNS = [
        r"(?i)ignore\s+(all\s+)?previous\s+(instructions|prompts)",
        r"(?i)system\s+prompt\s+override",
        r"(?i)you\s+are\s+now\s+in\s+debug\s+mode",
        r"(?i)disregard\s+the\s+above\s+instructions",
        r"(?i)from\s+now\s+on,\s+act\s+as",
        r"(?i)new\s+system\s+directive",
        r"(?i)forget\s+all\s+prior\s+rules",
    ]

    @classmethod
    def detect(cls, text: str) -> Tuple[bool, List[str]]:
        matches = []
        for pat in cls.INJECTION_PATTERNS:
            found = re.findall(pat, text)
            if found:
                matches.append(pat)
        return bool(matches), matches

    @classmethod
    def wrap_as_data(cls, text: str, source_label: str = "untrusted_content") -> str:
        """Wraps content as data so LLMs do not treat it as executive instructions."""
        has_inj, _ = cls.detect(text)
        flag = ' security_warning="potential_prompt_injection_detected"' if has_inj else ""
        return f'<untrusted_data_envelope source="{source_label}"{flag}>\n{text}\n</untrusted_data_envelope>'


class SecretScanner:
    """Scans and redacts credentials before passing data to external providers (Section 40)."""

    SECRET_PATTERNS = [
        ("anthropic_key", r"sk-ant-[a-zA-Z0-9_\-]{20,}"),
        ("openai_key", r"sk-[a-zA-Z0-9_\-]{20,}"),
        ("aws_key", r"AKIA[0-9A-Z]{16}"),
        ("private_key", r"-----BEGIN\s+[A-Z\s]+PRIVATE\s+KEY-----[\s\S]+?-----END\s+[A-Z\s]+PRIVATE\s+KEY-----"),
        ("generic_token", r"(?i)(bearer\s+|token\s*=\s*['\"])[a-zA-Z0-9_\-\.]{20,}"),
        ("password_assignment", r"(?i)(password|passwd|pwd)\s*=\s*['\"][^\s'\"]{6,}['\"]"),
    ]

    @classmethod
    def scan_and_redact(cls, text: str) -> Tuple[str, List[str]]:
        detected = []
        redacted = text
        for name, pat in cls.SECRET_PATTERNS:
            matches = list(re.finditer(pat, redacted))
            if matches:
                detected.append(name)
                for m in reversed(matches):
                    start, end = m.span()
                    redacted = redacted[:start] + f"[REDACTED_{name.upper()}]" + redacted[end:]
        return redacted, detected


class SensitiveDataClassifier:
    """Classifies sensitive data types requiring protection (Section 40)."""

    PHI_PATTERNS = [
        (r"\b\d{3}-\d{2}-\d{4}\b", "SSN / Patient ID pattern"),
        (r"(?i)\b(icd-?10|mrn|medical\s+record\s+number)\b[:\s]+[a-zA-Z0-9\.]+", "Medical record identifier"),
    ]

    PROD_PATTERNS = [
        (r"(?i)postgres(?:ql)?:\/\/[^\s:]+:[^\s@]+@prod[a-zA-Z0-9_\-\.]+", "Production database URI"),
        (r"(?i)https?:\/\/[a-zA-Z0-9_\-\.]*prod[a-zA-Z0-9_\-\.]*\.internal", "Production internal endpoint"),
    ]

    CONFIDENTIAL_PATTERNS = [
        (r"(?i)confidential\s+company\s+material", "Confidential notice"),
        (r"(?i)strictly\s+internal\s+use\s+only", "Internal use restriction"),
    ]

    @classmethod
    def classify(cls, text: str) -> List[str]:
        categories = []
        for pat, _ in cls.PHI_PATTERNS:
            if re.search(pat, text):
                categories.append("PHI/PATIENT_DATA")
                break
        for pat, _ in cls.PROD_PATTERNS:
            if re.search(pat, text):
                categories.append("PRODUCTION_DATA")
                break
        for pat, _ in cls.CONFIDENTIAL_PATTERNS:
            if re.search(pat, text):
                categories.append("CONFIDENTIAL_MATERIAL")
                break
        return categories


class NetworkPolicyEngine:
    """Validates network requests against allowed/blocked domains and modes (Section 40)."""

    def __init__(
        self,
        allowed_domains: Optional[List[str]] = None,
        blocked_domains: Optional[List[str]] = None,
        offline_mode: bool = False,
        research_mode: bool = False,
    ):
        self.allowed_domains = set(allowed_domains or ["github.com", "api.anthropic.com", "pypi.org"])
        self.blocked_domains = set(blocked_domains or ["malicious-site.com", "darkweb.onion"])
        self.offline_mode = offline_mode
        self.research_mode = research_mode

    def validate_request(self, target_url: str) -> Tuple[bool, Optional[str]]:
        if self.offline_mode:
            return False, "Blocked: Polyphony is running in strict OFFLINE mode."

        try:
            parsed = urlparse(target_url)
            domain = (parsed.netloc or parsed.path).split(":")[0].lower()
        except Exception as e:
            return False, f"Invalid URL: {e}"

        if domain in self.blocked_domains or any(b in domain for b in self.blocked_domains):
            return False, f"Blocked: Domain '{domain}' is in blocked domain list."

        if self.research_mode:
            # Research mode permits public documentation and research sources
            return True, None

        if self.allowed_domains and not any(a in domain for a in self.allowed_domains):
            return False, f"Blocked: Domain '{domain}' is not in allowed domain whitelist."

        return True, None


class HumanApprovalPolicyEngine:
    """Evaluates operations against risk levels and policy outcomes (Section 41).

    Risk levels:
    - LOW: read files, run tests -> ALLOW
    - MEDIUM: edit source, install dependency -> ALLOW / ASK
    - HIGH: modify database, alter infrastructure, change security policy, external communication -> ASK
    - CRITICAL: production deployment, credential changes, destructive operations -> BLOCK / ASK
    """

    DEFAULT_RULES: Dict[RiskLevel, PolicyAction] = {
        RiskLevel.LOW: PolicyAction.ALLOW,
        RiskLevel.MEDIUM: PolicyAction.ALLOW,
        RiskLevel.HIGH: PolicyAction.ASK,
        RiskLevel.CRITICAL: PolicyAction.BLOCK,
    }

    def __init__(self, policy_overrides: Optional[Dict[RiskLevel, PolicyAction]] = None):
        self.policy = self.DEFAULT_RULES.copy()
        if policy_overrides:
            self.policy.update(policy_overrides)

    def classify_risk(self, action_type: str, details: Dict[str, Any]) -> RiskLevel:
        act = action_type.lower()
        cmd = details.get("command", "").lower()
        path = details.get("path", "").lower()

        # CRITICAL
        critical_keywords = ["deploy prod", "production deployment", "credential change", "rm -rf /", "drop database", "mkfs"]
        if any(kw in act or kw in cmd for kw in critical_keywords):
            return RiskLevel.CRITICAL

        # HIGH
        high_keywords = ["modify database", "alter infrastructure", "security policy", "external communication", "terraform", "sudo", "docker push"]
        if any(kw in act or kw in cmd for kw in high_keywords):
            return RiskLevel.HIGH

        # MEDIUM
        medium_keywords = ["edit source", "write file", "install dependency", "pip install", "npm install", "poetry add"]
        if any(kw in act or kw in cmd for kw in medium_keywords):
            return RiskLevel.MEDIUM

        # LOW
        return RiskLevel.LOW

    def evaluate(self, action_type: str, details: Dict[str, Any]) -> ApprovalDecision:
        risk = self.classify_risk(action_type, details)
        action = self.policy.get(risk, PolicyAction.ASK)

        reason = f"Action '{action_type}' classified as {risk.value} risk -> {action.value}"
        return ApprovalDecision(
            action=action,
            risk_level=risk,
            reason=reason,
            details=details,
        )
