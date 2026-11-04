"""
Wispr Flow Voice Command Parser
Translates voice dictation transcripts into structured agent actions.
Supports the "Code with Wispr" track requirements.
"""

import re
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("sentinelops.voice_parser")


class VoiceCommandParser:
    def __init__(self):
        self.trigger_keywords = ["triage-commander", "sentinelops", "approve", "rollback", "revert", "status"]

    def parse_speech_transcript(self, raw_transcript: str) -> Dict[str, Any]:
        """
        Parses transcribed natural language speech from Wispr Flow dictation.
        Example transcripts:
          - "@triage-commander approve staging rollback"
          - "SentinelOps please approve rollback for commit 8f9b2a"
          - "@triage-commander show incident post-mortem status"
        """
        transcript_clean = raw_transcript.strip().lower()
        logger.info(f"Parsing voice dictation: '{raw_transcript}'")

        # Intent: Approve Rollback
        if any(term in transcript_clean for term in ["approve", "rollback", "revert"]):
            sha_match = re.search(r"\b([0-9a-f]{6,8})\b", transcript_clean)
            commit_sha = sha_match.group(1) if sha_match else "8f9b2a"
            return {
                "intent": "APPROVE_ROLLBACK",
                "action": "revert",
                "commit_sha": commit_sha,
                "confidence": 0.98,
                "source": "wispr_flow_voice_dictation",
                "raw_text": raw_transcript
            }

        # Intent: Incident Status Query
        if "status" in transcript_clean:
            return {
                "intent": "QUERY_STATUS",
                "confidence": 0.95,
                "source": "wispr_flow_voice_dictation",
                "raw_text": raw_transcript
            }

        # Default fallback
        return {
            "intent": "UNKNOWN",
            "confidence": 0.40,
            "source": "wispr_flow_voice_dictation",
            "raw_text": raw_transcript
        }

