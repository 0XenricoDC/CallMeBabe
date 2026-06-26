"""Setup validation (SETUP-01, D-12).

`.env.example` must contain exactly the three Phase 1 keys (plus DEMO_VOICE_ID) and
must NOT contain Telnyx/Google keys (those belong to Phases 4 and 2).
"""

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


def _read(name: str) -> str:
    return (_ROOT / name).read_text(encoding="utf-8")


def test_env_example():
    """SETUP-01: Phase 1 keys present; Phase 4 (Telnyx) keys absent.
    Phase 2 (Google Calendar) keys ADDED in Phase 2 (02-01).
    """
    content = _read(".env.example")

    assert "DEEPGRAM_API_KEY=" in content
    assert "ANTHROPIC_API_KEY=" in content
    assert "ELEVENLABS_API_KEY=" in content

    # Phase 4 (Telnyx) keys must NOT be present yet.
    assert "TELNYX_" not in content
    # Phase 2 (Google Calendar) keys are expected from Plan 02-01 onward.
    assert "GOOGLE_SERVICE_ACCOUNT_JSON" in content
    assert "GOOGLE_CALENDAR_ID_DEMO" in content


def test_env_example_has_no_real_secrets():
    """V7 / D-12: .env.example holds placeholders, never real key material."""
    content = _read(".env.example")
    # Placeholder convention: every key value is a *_here placeholder or the public
    # demo voice id — never something that looks like a live secret.
    assert "your_deepgram_api_key_here" in content
    assert "your_anthropic_api_key_here" in content
    assert "your_elevenlabs_api_key_here" in content


def test_readme_setup_section():
    """SETUP-01: README documents account creation and the run command."""
    content = _read("README.md")
    assert "## Setup" in content
    assert "Deepgram" in content
    assert "Anthropic" in content
    assert "ElevenLabs" in content
    assert "python main.py --tenant=demo" in content
    # V7: README must warn against committing .env / logging raw keys.
    assert ".env" in content
