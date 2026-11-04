"""
End-to-End Incident Lifecycle Test for SentinelOps
Simulates the complete 5-phase incident lifecycle from alert to verified remediation.
"""

import pytest
import asyncio
from agent.triage_commander import TriageCommanderAgent
from agent.voice_parser import VoiceCommandParser
from core.switch_server import store, app
from core.models import SwitchEvent, SwitchMessagePayload


@pytest.mark.asyncio
async def test_full_incident_remediation_lifecycle():
    room_id = "inc-checkout-482"
    agent = TriageCommanderAgent(base_url="http://localhost:8000", app=app)

    # Reset in-memory store for fresh test
    store.events[room_id] = []
    store.roles[room_id] = {}
    store.documents[room_id] = {}

    # 1. Simulate alert event delivered into Switch room
    alert_event = SwitchEvent(
        type="message",
        seq=1,
        room_id=room_id,
        sender_id="usr-mattermost-webhook",
        role="monitoring-alert",
        payload=SwitchMessagePayload(
            content="CRITICAL: HTTP 500 error rate spiked to 14.8% on /checkout endpoint",
            addressed=True
        )
    )

    # Agent processes Phase 1 & 2
    await agent.handle_event(alert_event)

    # Verify Phase 1 & 2 outcomes
    assert agent.current_incident_id == "INC-CHECKOUT-482"
    assert agent.current_diagnostic is not None
    assert agent.current_diagnostic.offending_commit == "8f9b2a"
    assert agent.current_diagnostic.author == "@dev-alice"
    assert store.roles[room_id]["triage-commander"] == agent.client.agent_id
    assert "incident-postmortem.md" in store.documents[room_id]
    doc = store.documents[room_id]["incident-postmortem.md"]
    assert "[DIAGNOSED]" in doc.content

    # 2. Simulate human approval decision via voice command transcribed by Wispr Flow
    voice_parser = VoiceCommandParser()
    dictated_speech = "@triage-commander approve staging rollback for 8f9b2a"
    parsed_command = voice_parser.parse_speech_transcript(dictated_speech)
    assert parsed_command["intent"] == "APPROVE_ROLLBACK"

    # Approval callback event delivered into Switch room
    approval_event = SwitchEvent(
        type="decision_callback",
        seq=2,
        room_id=room_id,
        sender_id="priya",
        role="incident-lead",
        payload=SwitchMessagePayload(
            content=f"Decision: Approved revert for commit #{parsed_command['commit_sha']} by @priya",
            metadata={"action": "revert", "commit_sha": parsed_command["commit_sha"]}
        )
    )

    # Agent processes Phase 4 & 5
    await agent.handle_event(approval_event)

    # Verify Phase 4 & 5 outcomes
    assert agent.is_resolved is True
    assert agent.is_remediating is False
    # Role lease must be released
    assert "triage-commander" not in store.roles.get(room_id, {})

    # Room Document must be updated to RESOLVED with MTTR
    final_doc = store.documents[room_id]["incident-postmortem.md"]
    assert "[RESOLVED]" in final_doc.content
    assert "2m 18s" in final_doc.content
    assert "42/42 Green" in final_doc.content
    assert "0 OWASP LLM vulnerabilities" in final_doc.content
