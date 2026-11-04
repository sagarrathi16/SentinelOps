"""
Wispr Flow Voice Command Simulation Helper
Allows user or presenter to simulate Wispr Flow voice dictation in real-time.
"""

import sys
import os

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.voice_parser import VoiceCommandParser


def run_voice_cli():
    parser = VoiceCommandParser()
    print("=" * 60)
    print("  [VOICE] Wispr Flow Speech Dictation Simulator")
    print("  Type any simulated voice dictation or press Enter for default:")
    print("  Default: '@triage-commander approve staging rollback'")
    print("=" * 60)

    sample = input("\nEnter voice text: ").strip()
    if not sample:
        sample = "@triage-commander approve staging rollback"

    print(f"\n[>] Transcribed Speech: \"{sample}\"")
    parsed = parser.parse_speech_transcript(sample)
    print(f"[+] Parsed Intent:    {parsed['intent']}")
    print(f"[+] Action:           {parsed.get('action', 'N/A')}")
    print(f"[+] Target Commit:    #{parsed.get('commit_sha', 'N/A')}")
    print(f"[+] Confidence:       {parsed['confidence'] * 100:.1f}%\n")


if __name__ == "__main__":
    run_voice_cli()

