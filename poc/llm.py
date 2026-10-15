"""LLM cleanup of messy voice transcripts before the Nutritionix lookup."""
import os

import anthropic

MODEL = "claude-sonnet-5-5"  # brief: Bedrock / Sonnet

SYSTEM = (
    "You clean up voice transcripts of what a person ate so a food database can parse them. "
    "Remove filler words, false starts and self-corrections (keep the corrected version). "
    "Keep every food, quantity and unit exactly as stated; do not invent portions or foods. "
    "Return only the cleaned food list as one line, items separated by commas."
)


def _client():
    if os.getenv("ANTHROPIC_API_KEY"):
        return anthropic.Anthropic(), MODEL, True
    region = os.getenv("BEDROCK_AWS_REGION")
    if region:
        return anthropic.AnthropicBedrockMantle(aws_region=region), f"anthropic.{MODEL}", False
    return None, None, False


def llm_configured():
    return _client()[0] is not None


def clean_transcript(text):
    client, model, first_party = _client()
    if client is None:
        raise RuntimeError("Set ANTHROPIC_API_KEY or BEDROCK_AWS_REGION in .env for LLM cleanup")
    kwargs = dict(
        model=model,
        max_tokens=1024,
        system=SYSTEM,
        output_config={"effort": "low"},
        messages=[{"role": "user", "content": text}],
    )
    if first_party:
        # Server-side refusal fallback (Claude API only)
        resp = client.beta.messages.create(
            betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs
        )
    else:
        resp = client.messages.create(**kwargs)
    if resp.stop_reason == "refusal":
        return text
    cleaned = "".join(b.text for b in resp.content if b.type == "text").strip()
    return cleaned or text
