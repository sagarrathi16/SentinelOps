"""
Tests for Switch Trust Guard & PII Sanitizer
"""

import pytest
from agent.switch_trust_guard import SwitchTrustGuard


def test_scrub_credit_card():
    guard = SwitchTrustGuard()
    raw = "User paid with 4111-2222-3333-4444 on checkout"
    cleaned, count = guard.scrub_text(raw)
    assert "[REDACTED_CREDIT_CARD]" in cleaned
    assert "4111-2222-3333-4444" not in cleaned
    assert count == 1


def test_scrub_email():
    guard = SwitchTrustGuard()
    raw = "Customer email is priya.engineer@sre-team.internal"
    cleaned, count = guard.scrub_text(raw)
    assert "@sanitized.domain" in cleaned
    assert "priya.engineer@sre-team.internal" not in cleaned
    assert count == 1


def test_scrub_bearer_token():
    guard = SwitchTrustGuard()
    raw = "Header Authorization: Bearer sk_live_demo_prod_secret_token_12345"
    cleaned, count = guard.scrub_text(raw)
    assert "[REDACTED_SECRET_TOKEN]" in cleaned
    assert "sk_live_demo_prod_secret_token_12345" not in cleaned


def test_wrap_log_payload():
    guard = SwitchTrustGuard()
    payload = {
        "event": "error_log",
        "card": "5500-0000-0000-0004",
        "email": "lead@company.com",
        "status": "failed"
    }
    wrapped = guard.wrap_log_payload(payload)
    assert wrapped["_switch_trust_audit"]["verified"] is True
    assert wrapped["_switch_trust_audit"]["guardrail_status"] == "ENFORCED"
    assert wrapped["_switch_trust_audit"]["redacted_count"] >= 2
    assert "5500-0000-0000-0004" not in str(wrapped)


def test_sarif_scanner_clean():
    guard = SwitchTrustGuard()
    report = guard.generate_sarif_report()
    assert report["version"] == "2.1.0"
    assert len(report["runs"]) > 0
    assert len(report["runs"][0]["results"]) == 0  # 0 vulnerabilities

