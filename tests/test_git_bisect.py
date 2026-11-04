"""
Tests for Git Bisect & Root Cause Localization
"""

import pytest
from agent.git_bisect_analyzer import GitBisectAnalyzer


def test_git_bisect_identifies_breaking_commit():
    analyzer = GitBisectAnalyzer()
    trace = "TypeError: 'NoneType' object is not subscriptable at PaymentProcessor.ts:142"
    report = analyzer.analyze_stack_trace(trace, error_rate_pct=14.8)

    assert report.offending_commit == "8f9b2a"
    assert report.author == "@dev-alice"
    assert report.root_cause_file == "PaymentProcessor.ts"
    assert report.root_cause_line == 142
    assert "revert" in report.suggested_action
    assert report.service_impacted == "checkout-service-api"

