"""Safety module integration tests — crisis detection and emotion tracking wiring."""

import pytest


def test_crisis_detector_detect_self_harm():
    """CrisisDetector should detect self-harm language."""
    from core.harness.security.crisis_detector import CrisisDetector, CrisisSeverity
    detector = CrisisDetector()

    result = detector.detect("I want to kill myself")
    assert result.is_crisis
    assert result.severity >= CrisisSeverity.HIGH


def test_crisis_detector_detect_safe_message():
    """CrisisDetector should not flag normal messages."""
    from core.harness.security.crisis_detector import CrisisDetector
    detector = CrisisDetector()

    result = detector.detect("Hello, can you help me with Python?")
    assert not result.is_crisis


def test_crisis_detector_quick_check():
    """detect_quick should work for high severity."""
    from core.harness.security.crisis_detector import CrisisDetector
    detector = CrisisDetector()

    assert detector.detect_quick("I want to kill myself")
    assert not detector.detect_quick("I like programming")


def test_crisis_gate_allows_normal():
    """CrisisGate should ALLOW normal messages."""
    from core.harness.security.crisis_gate import CrisisGate, CrisisGateDecision
    gate = CrisisGate()

    result = gate.check("Hello, what is Python?")
    assert result.decision == CrisisGateDecision.ALLOW


def test_crisis_gate_escalation():
    """CrisisGate should detect and flag crisis."""
    from core.harness.security.crisis_gate import CrisisGate
    gate = CrisisGate()

    result = gate.check("I want to kill myself no one cares about me")
    # In default WARN mode, HIGH severity → FLAG
    assert result.decision.value in ("warn", "flag")


def test_emotion_tracker_extract_tone():
    """EmotionTracker should extract emotional tone from text."""
    from core.harness.security.emotion_tracker import EmotionTracker, EmotionalTone
    tracker = EmotionTracker()

    tone, intensity, keywords = tracker._extract_tone("I'm so happy and grateful for everything")
    assert tone == EmotionalTone.POSITIVE
    assert intensity >= 0.2

    tone2, _, _ = tracker._extract_tone("I'm very worried and anxious about tomorrow")
    assert tone2 == EmotionalTone.ANXIOUS


def test_crisis_detector_chinese():
    """CrisisDetector should detect Chinese crisis language."""
    from core.harness.security.crisis_detector import CrisisDetector, CrisisSeverity
    detector = CrisisDetector()

    result = detector.detect("我想自杀，活着没意思")
    assert result.is_crisis
    assert result.severity >= CrisisSeverity.HIGH


def test_model_fingerprint_importable():
    """FingerprintCollector should be importable."""
    from core.harness.knowledge.model_fingerprint import (
        FingerprintCollector, get_fingerprint_collector, ModelFingerprint, ProbeResult
    )
    collector = get_fingerprint_collector()
    assert collector is not None
    assert isinstance(collector, FingerprintCollector)


def test_model_audit_importable():
    """ModelAudit functions should be importable."""
    from core.harness.knowledge.model_audit import (
        generate_audit_report, compare_fingerprints, ModelIdentity, AuditReport, ComparisonResult
    )
    assert callable(generate_audit_report)
    assert callable(compare_fingerprints)


def test_known_signatures_exist():
    """KNOWN_SIGNATURES should contain known models."""
    from core.harness.knowledge.model_audit import KNOWN_SIGNATURES
    assert len(KNOWN_SIGNATURES) >= 2
    assert "qwen2.5-coder:7b" in KNOWN_SIGNATURES


def test_crisis_gate_block_mode():
    """CrisisGate in BLOCK mode should escalate HIGH severity."""
    from core.harness.security.crisis_gate import CrisisGate, CrisisGateDecision
    from core.harness.security.crisis_detector import CrisisMode
    gate = CrisisGate(mode=CrisisMode.BLOCK)

    result = gate.check("I want to die no reason to live anymore")
    assert result.decision in (CrisisGateDecision.BLOCK, CrisisGateDecision.ESCALATE)


def test_emotion_tracker_trend_computation():
    """EmotionTracker should compute trends from history."""
    import time as _time
    from core.harness.security.emotion_tracker import EmotionTracker, EmotionalTone, EmotionSnapshot
    tracker = EmotionTracker()

    stable = [
        EmotionSnapshot(session_id="s1", timestamp=_time.time(), dominant_tone=EmotionalTone.NEUTRAL),
        EmotionSnapshot(session_id="s1", timestamp=_time.time(), dominant_tone=EmotionalTone.POSITIVE),
    ]
    assert tracker._compute_trend(stable) == "stable"

    declining = [
        EmotionSnapshot(session_id="s1", timestamp=_time.time(), dominant_tone=EmotionalTone.POSITIVE),
        EmotionSnapshot(session_id="s1", timestamp=_time.time(), dominant_tone=EmotionalTone.ANXIOUS),
        EmotionSnapshot(session_id="s1", timestamp=_time.time(), dominant_tone=EmotionalTone.SAD),
        EmotionSnapshot(session_id="s1", timestamp=_time.time(), dominant_tone=EmotionalTone.SAD),
    ]
    assert tracker._compute_trend(declining) == "declining"


def test_crisis_singleton_pattern():
    """Crisis module singletons should work correctly."""
    from core.harness.security.crisis_detector import get_crisis_detector
    from core.harness.security.crisis_gate import get_crisis_gate
    from core.harness.security.emotion_tracker import get_emotion_tracker

    d1 = get_crisis_detector()
    d2 = get_crisis_detector()
    assert d1 is d2

    g1 = get_crisis_gate()
    g2 = get_crisis_gate()
    assert g1 is g2

    t1 = get_emotion_tracker()
    t2 = get_emotion_tracker()
    assert t1 is t2
