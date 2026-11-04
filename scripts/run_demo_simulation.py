"""
SentinelOps - Deterministic 90-Second Demo Simulation
Executes the complete incident triage and verified rollback lifecycle:
1. Alert Intake & Room Creation (seq 42)
2. Switch Trust Zero-PII Log Scrubbing
3. Autonomous Git Bisect Root Cause Isolation (#8f9b2a by @dev-alice)
4. Mattermost Interactive Decision Card & Wispr Flow Voice Input
5. Sandboxed Revert, 42/42 Regression Suite, and SARIF Security Scan
6. Living Post-Mortem Update & MTTR Calculation (2m 18s)
"""

import sys
import os
import time
import asyncio
from datetime import datetime, timezone

# Ensure UTF-8 output encoding on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.switch_server import store, app
from core.models import SwitchEvent, SwitchMessagePayload
from agent.triage_commander import TriageCommanderAgent
from agent.voice_parser import VoiceCommandParser


def log_step(phase: str, title: str, details: str, symbol: str = "[>]"):
    now = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    print(f"\n\033[1;36m[{now}] {symbol} {phase}: {title}\033[0m")
    for line in details.strip().split("\n"):
        print(f"  \033[0;37m{line}\033[0m")


async def run_simulation():
    print("=" * 80)
    print("\033[1;32m      SENTINELOPS: AUTONOMOUS INCIDENT COMMANDER & HOTFIX ENGINE\033[0m")
    print("\033[1;33m       WeMakeDevs x DevTools Academy x Switch AI / SandboxAQ Hackathon\033[0m")
    print("=" * 80)

    room_id = "inc-checkout-482"
    agent = TriageCommanderAgent(base_url="http://localhost:8000", app=app)

    # -------------------------------------------------------------
    # Beat 1: The Alert & Room Creation
    # -------------------------------------------------------------
    log_step(
        "BEAT 1",
        "Alert Intake & Switch Room Provisioning",
        "PagerDuty/Sentry Webhook fires HTTP 500 error spike.\n"
        "Room: inc-checkout-482 | Service: checkout-service-api | Error Rate: 14.8%"
    )
    time.sleep(1.0)

    alert_event = SwitchEvent(
        type="message",
        seq=42,
        room_id=room_id,
        sender_id="usr-mattermost-webhook",
        role="monitoring-alert",
        payload=SwitchMessagePayload(
            content="CRITICAL: HTTP 500 error rate spiked to 14.8% on /checkout endpoint",
            addressed=True
        )
    )
    await agent.handle_event(alert_event)

    # -------------------------------------------------------------
    # Beat 2: Switch Trust Scrubbing & Autonomous Bisect
    # -------------------------------------------------------------
    log_step(
        "BEAT 2",
        "Switch Trust PII Sanitization & Autonomous Git Bisect",
        f"Switch Trust Guard wrapped telemetry: 3 sensitive tokens scrubbed (zero PII leaks).\n"
        f"Root Cause Isolated: NullPointerException at PaymentProcessor.ts:142\n"
        f"Breaking Commit SHA: #8f9b2a by @dev-alice ('Add expedited billing flag')\n"
        f"Living Post-Mortem Runbook created in Switch Room Document storage."
    )
    time.sleep(1.2)

    # -------------------------------------------------------------
    # Beat 3: Wispr Flow Voice Input & Interactive Approval Gate
    # -------------------------------------------------------------
    log_step(
        "BEAT 3",
        "Wispr Flow Voice Command & Mattermost Decision Gate",
        "On-Call SRE (Priya) reviews Diagnostic Briefing in Mattermost.\n"
        "Priya dictates voice command via Wispr Flow Desktop (Ctrl+Space):\n"
        "  [VOICE] Dictation: '@triage-commander approve staging rollback'\n"
        "Wispr Parser Intent: APPROVE_ROLLBACK (confidence: 98%)\n"
        "Priya clicks interactive Mattermost card button: [Approve Staging Rollback]\n"
        "Mattermost dispatches HTTP callback to Port :8081."
    )
    time.sleep(1.5)

    # Simulate Port :8081 callback event
    decision_event = SwitchEvent(
        type="decision_callback",
        seq=55,
        room_id=room_id,
        sender_id="priya-sre",
        role="incident-lead",
        payload=SwitchMessagePayload(
            content="Decision: Approved rollback for commit #8f9b2a by @priya-sre",
            metadata={"action": "revert", "commit_sha": "8f9b2a"}
        )
    )
    await agent.handle_event(decision_event)

    # -------------------------------------------------------------
    # Beat 4: Sandboxed Revert, 42 Tests & SARIF Static Scan
    # -------------------------------------------------------------
    log_step(
        "BEAT 4",
        "Sandboxed Remediation & Security Compliance",
        "Executing: git revert --no-edit 8f9b2a\n"
        "Automated Test Suite: pytest target_service/tests/test_payment.py\n"
        "  [+] 42/42 tests PASSED (100% Green)\n"
        "Static Security Scan: switch-trust scan --format sarif\n"
        "  [+] SARIF 2.1.0 output: 0 OWASP LLM vulnerabilities"
    )
    time.sleep(1.2)

    # -------------------------------------------------------------
    # Beat 5: Audit Finalization & Resolution
    # -------------------------------------------------------------
    doc = store.documents[room_id]["incident-postmortem.md"]
    log_step(
        "BEAT 5",
        "Incident Closed & Living Post-Mortem Generated",
        f"Target container redeployed with clean commit #7c41e0.\n"
        f"Error rate restored to 0.01%.\n"
        f"Mean Time to Remediate (MTTR): 2m 18s (down from 45m manual).\n"
        f"Exclusive role lease @triage-commander released.\n"
        f"Living Room Document 'incident-postmortem.md' status: RESOLVED."
    )
    time.sleep(0.5)

    print("\n" + "=" * 80)
    print("\033[1;32m   SUCCESS: DEMO SIMULATION COMPLETED IN UNDER 90 SECONDS (100% RELIABLE)\033[0m")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    asyncio.run(run_simulation())
