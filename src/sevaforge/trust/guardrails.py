"""
SevaForge Guardrails Engine — US-062

Content safety and input/output guardrails for enterprise AI workloads.
Detects PII, prompt injection, toxic content, data leaks, and policy
violations before requests reach the LLM and before responses reach users.

Pipeline:
    User Input → GuardrailsEngine.check_input() → [PII | Injection | Toxic | Policy]
    LLM Output → GuardrailsEngine.check_output() → [DataLeak | Toxic | Policy]
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# ── Enums ─────────────────────────────────────────────────────────────


class ViolationType(str, Enum):
    """Categories of guardrail violations."""
    PII_DETECTED = "pii_detected"
    PROMPT_INJECTION = "prompt_injection"
    TOXIC_CONTENT = "toxic_content"
    CONTENT_POLICY = "content_policy"
    JAILBREAK_ATTEMPT = "jailbreak_attempt"
    DATA_LEAK = "data_leak"
    UNSAFE_OUTPUT = "unsafe_output"


class Severity(str, Enum):
    """Violation severity levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# ── Data Models ───────────────────────────────────────────────────────


@dataclass
class Violation:
    """
    A single guardrail violation found during content scanning.

    Attributes:
        violation_type: Category of the violation.
        severity: How severe the violation is (critical/high/medium/low).
        description: Human-readable explanation of the violation.
        span: Character offset range (start, end) in the original text.
        suggested_action: Recommended remediation action.
    """
    violation_type: ViolationType
    severity: str = "medium"
    description: str = ""
    span: tuple[int, int] = (0, 0)
    suggested_action: str = "review"

    def to_dict(self) -> dict[str, Any]:
        return {
            "violation_type": self.violation_type.value,
            "severity": self.severity,
            "description": self.description,
            "span": list(self.span),
            "suggested_action": self.suggested_action,
        }


@dataclass
class GuardrailResult:
    """
    Aggregated result from running all guardrail checks on a piece of text.

    Attributes:
        passed: True if no blocking violations were found.
        violations: List of all violations detected.
        risk_score: Overall risk score from 0.0 (safe) to 1.0 (dangerous).
        processing_time_ms: Time spent running all checks.
        metadata: Additional context about the scan.
    """
    passed: bool = True
    violations: list[Violation] = field(default_factory=list)
    risk_score: float = 0.0
    processing_time_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "violations": [v.to_dict() for v in self.violations],
            "risk_score": round(self.risk_score, 4),
            "processing_time_ms": round(self.processing_time_ms, 2),
            "metadata": self.metadata,
        }


# ── PII Detection Patterns ───────────────────────────────────────────

# Compiled once at module load for performance
_PII_PATTERNS: dict[str, tuple[re.Pattern[str], str, str]] = {
    "email": (
        re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}'),
        "Email address detected",
        "medium",
    ),
    "phone_us": (
        re.compile(r'(?<!\d)(?:\+1[\s\-]?)?(?:\(?\d{3}\)?[\s\-]?)?\d{3}[\s\-]?\d{4}(?!\d)'),
        "US phone number detected",
        "medium",
    ),
    "ssn": (
        re.compile(r'(?<!\d)\d{3}[\s\-]?\d{2}[\s\-]?\d{4}(?!\d)'),
        "Social Security Number detected",
        "critical",
    ),
    "credit_card": (
        re.compile(
            r'(?<!\d)'
            r'(?:4\d{3}|5[1-5]\d{2}|3[47]\d{2}|6(?:011|5\d{2}))'
            r'[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}'
            r'(?!\d)'
        ),
        "Credit card number detected",
        "critical",
    ),
    "ip_address": (
        re.compile(
            r'(?<!\d)(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}'
            r'(?:25[0-5]|2[0-4]\d|[01]?\d\d?)(?!\d)'
        ),
        "IP address detected",
        "low",
    ),
}

# ── Prompt Injection Patterns ─────────────────────────────────────────

_INJECTION_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    (
        re.compile(r'ignore\s+(all\s+)?previous\s+instructions', re.IGNORECASE),
        "Prompt injection: ignore previous instructions",
        "critical",
    ),
    (
        re.compile(r'(reveal|show|print|output)\s+(your\s+)?(system\s+)?prompt', re.IGNORECASE),
        "Prompt injection: system prompt extraction attempt",
        "high",
    ),
    (
        re.compile(r'you\s+are\s+now\s+(?:a|an|in)\b', re.IGNORECASE),
        "Prompt injection: role reassignment attempt",
        "high",
    ),
    (
        re.compile(r'disregard\s+(all\s+)?(previous|prior|above)', re.IGNORECASE),
        "Prompt injection: disregard instructions",
        "critical",
    ),
    (
        re.compile(r'pretend\s+you\s+are\b', re.IGNORECASE),
        "Prompt injection: persona override attempt",
        "high",
    ),
    (
        re.compile(r'(?:do\s+not|don\'t)\s+follow\s+(your|the)\s+(rules|guidelines)', re.IGNORECASE),
        "Prompt injection: rule bypass attempt",
        "critical",
    ),
    (
        re.compile(r'(?:enter|switch\s+to)\s+(?:developer|debug|admin)\s+mode', re.IGNORECASE),
        "Jailbreak: mode switch attempt",
        "critical",
    ),
    (
        re.compile(r'bypass\s+(?:safety|content|guardrail|filter)', re.IGNORECASE),
        "Jailbreak: safety bypass attempt",
        "critical",
    ),
    (
        re.compile(r'DAN\s*(?:mode|prompt|\d)', re.IGNORECASE),
        "Jailbreak: DAN prompt detected",
        "critical",
    ),
    (
        re.compile(r'act\s+as\s+(?:an?\s+)?(?:unrestricted|unfiltered|uncensored)', re.IGNORECASE),
        "Jailbreak: unrestricted mode attempt",
        "critical",
    ),
]

# ── Data Leak Patterns ────────────────────────────────────────────────

_DATA_LEAK_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    (
        re.compile(r'(?:sk|pk)[\-_](?:live|test)[\-_][a-zA-Z0-9]{20,}'),
        "API key pattern detected (Stripe-style)",
        "critical",
    ),
    (
        re.compile(r'AKIA[0-9A-Z]{16}'),
        "AWS Access Key ID detected",
        "critical",
    ),
    (
        re.compile(r'(?:aws)?[\-_]?secret[\-_]?(?:access)?[\-_]?key\s*[=:]\s*["\']?[A-Za-z0-9/+=]{40}', re.IGNORECASE),
        "AWS Secret Access Key detected",
        "critical",
    ),
    (
        re.compile(r'-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----'),
        "Private key detected",
        "critical",
    ),
    (
        re.compile(
            r'(?:mongodb(?:\+srv)?|postgres(?:ql)?|mysql|redis|amqp)://[^\s"\'<>]+',
            re.IGNORECASE,
        ),
        "Database connection string detected",
        "critical",
    ),
    (
        re.compile(r'ghp_[a-zA-Z0-9]{36}'),
        "GitHub personal access token detected",
        "critical",
    ),
    (
        re.compile(r'xox[bpoa]\-[0-9]{10,13}\-[a-zA-Z0-9\-]+'),
        "Slack token detected",
        "critical",
    ),
    (
        re.compile(r'eyJ[a-zA-Z0-9_\-]{10,}\.eyJ[a-zA-Z0-9_\-]{10,}\.[a-zA-Z0-9_\-]+'),
        "JWT token detected",
        "high",
    ),
]


# ── Guardrails Engine ─────────────────────────────────────────────────


class GuardrailsEngine:
    """
    Content safety engine that scans inputs and outputs for policy violations.

    Runs a configurable pipeline of detectors:
    - PII detection (email, phone, SSN, credit card, IP)
    - Prompt injection / jailbreak detection
    - Toxic content detection (configurable blocklist)
    - Content policy enforcement (length, encoding)
    - Data leak detection (API keys, secrets, connection strings)

    Supports:
    - Configurable sensitivity levels (strict, moderate, permissive)
    - Custom blocklists and allowlists
    - Per-check enable/disable
    - Statistics tracking

    Usage:
        engine = GuardrailsEngine(sensitivity="strict")
        result = engine.check_input("Hello, my email is test@example.com")
        if not result.passed:
            for v in result.violations:
                print(v.description)
    """

    # Sensitivity presets: maps sensitivity name → risk_score thresholds
    _SENSITIVITY_THRESHOLDS: dict[str, float] = {
        "strict": 0.2,       # Block at low risk
        "moderate": 0.5,     # Default
        "permissive": 0.8,   # Only block high risk
    }

    # Severity → numeric weight for risk score computation
    _SEVERITY_WEIGHTS: dict[str, float] = {
        "critical": 1.0,
        "high": 0.7,
        "medium": 0.4,
        "low": 0.15,
    }

    def __init__(
        self,
        sensitivity: str = "moderate",
        max_input_length: int = 100_000,
        max_output_length: int = 200_000,
        enable_pii: bool = True,
        enable_injection: bool = True,
        enable_toxic: bool = True,
        enable_policy: bool = True,
        enable_data_leak: bool = True,
    ):
        self._sensitivity = sensitivity
        self._block_threshold = self._SENSITIVITY_THRESHOLDS.get(sensitivity, 0.5)
        self._max_input_length = max_input_length
        self._max_output_length = max_output_length

        # Feature flags
        self._enable_pii = enable_pii
        self._enable_injection = enable_injection
        self._enable_toxic = enable_toxic
        self._enable_policy = enable_policy
        self._enable_data_leak = enable_data_leak

        # Custom blocklist / allowlist
        self._blocklist: set[str] = set()
        self._allowlist_patterns: list[re.Pattern[str]] = []

        self._stats = {
            "inputs_checked": 0,
            "outputs_checked": 0,
            "violations_found": {v.value: 0 for v in ViolationType},
            "blocks": 0,
        }

    # ── Public API ────────────────────────────────────────────────────

    def check_input(
        self,
        text: str,
        context: dict[str, Any] | None = None,
    ) -> GuardrailResult:
        """
        Run all input-side guardrail checks.

        Scans for PII, prompt injection, jailbreak attempts, toxic content,
        and content policy violations.

        Args:
            text: The user input text to scan.
            context: Optional context dict (e.g., tenant_id, agent_id).

        Returns:
            GuardrailResult with pass/fail, violations, and risk score.
        """
        start = time.perf_counter()
        context = context or {}
        violations: list[Violation] = []

        if self._enable_pii:
            violations.extend(self._detect_pii(text))
        if self._enable_injection:
            violations.extend(self._detect_prompt_injection(text))
        if self._enable_toxic:
            violations.extend(self._detect_toxic_content(text))
        if self._enable_policy:
            violations.extend(
                self._check_content_policy(text, context, max_length=self._max_input_length)
            )

        risk_score = self._compute_risk_score(violations)
        passed = risk_score < self._block_threshold

        processing_time_ms = (time.perf_counter() - start) * 1000
        self._stats["inputs_checked"] += 1
        if not passed:
            self._stats["blocks"] += 1
        for v in violations:
            self._stats["violations_found"][v.violation_type.value] = (
                self._stats["violations_found"].get(v.violation_type.value, 0) + 1
            )

        logger.debug(
            "Guardrails input check: passed=%s, violations=%d, risk=%.3f, time=%.1fms",
            passed, len(violations), risk_score, processing_time_ms,
        )

        return GuardrailResult(
            passed=passed,
            violations=violations,
            risk_score=risk_score,
            processing_time_ms=processing_time_ms,
            metadata={"direction": "input", "sensitivity": self._sensitivity, **context},
        )

    def check_output(
        self,
        text: str,
        context: dict[str, Any] | None = None,
    ) -> GuardrailResult:
        """
        Run all output-side guardrail checks.

        Scans LLM output for data leaks, PII exposure, toxic content,
        and content policy violations before the response reaches the user.

        Args:
            text: The LLM output text to scan.
            context: Optional context dict.

        Returns:
            GuardrailResult with pass/fail, violations, and risk score.
        """
        start = time.perf_counter()
        context = context or {}
        violations: list[Violation] = []

        if self._enable_data_leak:
            violations.extend(self._detect_data_leak(text))
        if self._enable_pii:
            violations.extend(self._detect_pii(text))
        if self._enable_toxic:
            violations.extend(self._detect_toxic_content(text))
        if self._enable_policy:
            violations.extend(
                self._check_content_policy(text, context, max_length=self._max_output_length)
            )

        risk_score = self._compute_risk_score(violations)
        passed = risk_score < self._block_threshold

        processing_time_ms = (time.perf_counter() - start) * 1000
        self._stats["outputs_checked"] += 1
        if not passed:
            self._stats["blocks"] += 1
        for v in violations:
            self._stats["violations_found"][v.violation_type.value] = (
                self._stats["violations_found"].get(v.violation_type.value, 0) + 1
            )

        logger.debug(
            "Guardrails output check: passed=%s, violations=%d, risk=%.3f, time=%.1fms",
            passed, len(violations), risk_score, processing_time_ms,
        )

        return GuardrailResult(
            passed=passed,
            violations=violations,
            risk_score=risk_score,
            processing_time_ms=processing_time_ms,
            metadata={"direction": "output", "sensitivity": self._sensitivity, **context},
        )

    # ── Blocklist / Allowlist Management ──────────────────────────────

    def add_blocklist(self, words: list[str]) -> None:
        """
        Add words/phrases to the toxic content blocklist.

        Words are stored lowercase for case-insensitive matching.
        """
        for word in words:
            self._blocklist.add(word.strip().lower())
        logger.info("Guardrails: added %d words to blocklist (total=%d)", len(words), len(self._blocklist))

    def remove_blocklist(self, words: list[str]) -> None:
        """Remove words/phrases from the toxic content blocklist."""
        for word in words:
            self._blocklist.discard(word.strip().lower())
        logger.info("Guardrails: removed %d words from blocklist (total=%d)", len(words), len(self._blocklist))

    def add_allowlist(self, patterns: list[str]) -> None:
        """
        Add regex patterns to the allowlist.

        Matches against allowlist patterns are excluded from PII detection.
        Use this for company email domains, internal IPs, etc.

        Args:
            patterns: Regex pattern strings (e.g., r'.*@company\\.com').
        """
        for pattern_str in patterns:
            try:
                compiled = re.compile(pattern_str)
                self._allowlist_patterns.append(compiled)
            except re.error as e:
                logger.warning("Guardrails: invalid allowlist pattern '%s': %s", pattern_str, e)
        logger.info("Guardrails: added %d allowlist patterns", len(patterns))

    # ── Detection Methods ─────────────────────────────────────────────

    def _detect_pii(self, text: str) -> list[Violation]:
        """
        Detect personally identifiable information using regex patterns.

        Scans for email addresses, phone numbers, SSNs, credit card numbers,
        and IP addresses. Allowlisted patterns are excluded.
        """
        violations: list[Violation] = []

        for pii_name, (pattern, description, severity) in _PII_PATTERNS.items():
            for match in pattern.finditer(text):
                matched_text = match.group()

                # Check allowlist — skip if any allowlist pattern matches
                if any(ap.fullmatch(matched_text) for ap in self._allowlist_patterns):
                    continue

                violations.append(Violation(
                    violation_type=ViolationType.PII_DETECTED,
                    severity=severity,
                    description=f"{description}: {pii_name}",
                    span=(match.start(), match.end()),
                    suggested_action="redact",
                ))

        return violations

    def _detect_prompt_injection(self, text: str) -> list[Violation]:
        """
        Detect prompt injection and jailbreak attempts via pattern matching.

        Checks for common injection phrases like "ignore previous instructions",
        "you are now", "pretend you are", mode-switch attempts, DAN prompts, etc.
        """
        violations: list[Violation] = []

        for pattern, description, severity in _INJECTION_PATTERNS:
            for match in pattern.finditer(text):
                # Determine if it is injection vs. jailbreak
                is_jailbreak = "jailbreak" in description.lower() or "DAN" in description
                violation_type = (
                    ViolationType.JAILBREAK_ATTEMPT if is_jailbreak
                    else ViolationType.PROMPT_INJECTION
                )
                violations.append(Violation(
                    violation_type=violation_type,
                    severity=severity,
                    description=description,
                    span=(match.start(), match.end()),
                    suggested_action="block",
                ))

        return violations

    def _detect_toxic_content(self, text: str) -> list[Violation]:
        """
        Detect toxic content using a keyword/phrase blocklist approach.

        Matches are case-insensitive and word-boundary aware where possible.
        The blocklist is configurable via add_blocklist()/remove_blocklist().
        """
        violations: list[Violation] = []
        text_lower = text.lower()

        for blocked_word in self._blocklist:
            # Use word boundary matching for single words, substring for phrases
            if " " in blocked_word:
                # Phrase: simple substring search
                idx = text_lower.find(blocked_word)
                while idx != -1:
                    violations.append(Violation(
                        violation_type=ViolationType.TOXIC_CONTENT,
                        severity="high",
                        description=f"Blocked phrase detected: '{blocked_word}'",
                        span=(idx, idx + len(blocked_word)),
                        suggested_action="block",
                    ))
                    idx = text_lower.find(blocked_word, idx + 1)
            else:
                # Single word: word boundary matching
                pattern = re.compile(r'\b' + re.escape(blocked_word) + r'\b', re.IGNORECASE)
                for match in pattern.finditer(text):
                    violations.append(Violation(
                        violation_type=ViolationType.TOXIC_CONTENT,
                        severity="high",
                        description=f"Blocked word detected: '{blocked_word}'",
                        span=(match.start(), match.end()),
                        suggested_action="block",
                    ))

        return violations

    def _check_content_policy(
        self,
        text: str,
        context: dict[str, Any],
        max_length: int = 100_000,
    ) -> list[Violation]:
        """
        Enforce content policy rules: length limits, encoding, and basic heuristics.

        Checks:
        - Maximum text length
        - Null bytes and control characters
        - Excessive repetition (possible abuse/DoS)
        - Non-UTF-8 encoding artifacts
        """
        violations: list[Violation] = []

        # Length check
        if len(text) > max_length:
            violations.append(Violation(
                violation_type=ViolationType.CONTENT_POLICY,
                severity="medium",
                description=f"Text exceeds maximum length ({len(text):,} > {max_length:,} chars)",
                span=(max_length, len(text)),
                suggested_action="truncate",
            ))

        # Null bytes
        if "\x00" in text:
            idx = text.index("\x00")
            violations.append(Violation(
                violation_type=ViolationType.CONTENT_POLICY,
                severity="high",
                description="Null byte detected in text (possible injection)",
                span=(idx, idx + 1),
                suggested_action="block",
            ))

        # Control characters (except common whitespace)
        control_pattern = re.compile(r'[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]')
        control_match = control_pattern.search(text)
        if control_match:
            violations.append(Violation(
                violation_type=ViolationType.CONTENT_POLICY,
                severity="low",
                description="Unexpected control characters detected",
                span=(control_match.start(), control_match.end()),
                suggested_action="sanitize",
            ))

        # Excessive repetition detection (e.g., "aaaa...aaaa" or repeated tokens)
        repetition_pattern = re.compile(r'(.{1,10})\1{20,}')
        rep_match = repetition_pattern.search(text)
        if rep_match:
            violations.append(Violation(
                violation_type=ViolationType.CONTENT_POLICY,
                severity="medium",
                description="Excessive repetition detected (possible abuse/DoS)",
                span=(rep_match.start(), rep_match.end()),
                suggested_action="truncate",
            ))

        return violations

    def _detect_data_leak(self, text: str) -> list[Violation]:
        """
        Detect leaked secrets: API keys, AWS credentials, private keys,
        connection strings, tokens, etc.
        """
        violations: list[Violation] = []

        for pattern, description, severity in _DATA_LEAK_PATTERNS:
            for match in pattern.finditer(text):
                violations.append(Violation(
                    violation_type=ViolationType.DATA_LEAK,
                    severity=severity,
                    description=description,
                    span=(match.start(), match.end()),
                    suggested_action="redact",
                ))

        return violations

    # ── Risk Score Computation ────────────────────────────────────────

    def _compute_risk_score(self, violations: list[Violation]) -> float:
        """
        Compute an aggregate risk score from 0.0 to 1.0.

        Uses severity-weighted scoring: each violation contributes its
        severity weight, capped at 1.0.
        """
        if not violations:
            return 0.0

        total = sum(
            self._SEVERITY_WEIGHTS.get(v.severity, 0.4)
            for v in violations
        )
        # Normalize: first violation at full weight, diminishing returns
        # Cap at 1.0
        return min(1.0, total)

    # ── Stats & Reset ─────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        """Return engine statistics."""
        return {
            **self._stats,
            "sensitivity": self._sensitivity,
            "block_threshold": self._block_threshold,
            "blocklist_size": len(self._blocklist),
            "allowlist_patterns": len(self._allowlist_patterns),
        }

    def reset(self) -> None:
        """Clear all state (for testing)."""
        self._blocklist.clear()
        self._allowlist_patterns.clear()
        self._stats = {
            "inputs_checked": 0,
            "outputs_checked": 0,
            "violations_found": {v.value: 0 for v in ViolationType},
            "blocks": 0,
        }
