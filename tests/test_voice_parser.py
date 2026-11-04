"""
Tests for Wispr Flow Voice Command Parser
"""

import pytest
from agent.voice_parser import VoiceCommandParser


def test_parse_rollback_approval():
    parser = VoiceCommandParser()
    transcript = "@triage-commander approve staging rollback for 8f9b2a"
    res = parser.parse_speech_transcript(transcript)

    assert res["intent"] == "APPROVE_ROLLBACK"
    assert res["action"] == "revert"
    assert res["commit_sha"] == "8f9b2a"
    assert res["confidence"] >= 0.90


def test_parse_status_query():
    parser = VoiceCommandParser()
    transcript = "SentinelOps what is the current incident status"
    res = parser.parse_speech_transcript(transcript)

    assert res["intent"] == "QUERY_STATUS"
    assert res["confidence"] >= 0.90

