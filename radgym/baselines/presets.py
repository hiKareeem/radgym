"""
Preset baseline configurations for v0.1.

The seven baselines that ship pre-populated on the leaderboard at launch.
Each entry is a `BaselineConfig` ready to pass to `run_baseline()`.

To add or modify a baseline, edit this file and add it to `PRESET_BASELINES`.
Custom one-off baselines can be passed directly to `run_baseline()` without
going through this registry.

LiteLLM model identifier format:
    https://docs.litellm.ai/docs/providers
"""

from __future__ import annotations

from radgym.baselines.runner import (
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_USER_PROMPT_TEMPLATE,
    BaselineConfig,
)


# Closed-source frontier baselines (require API keys via env)
GPT_4O = BaselineConfig(
    name="gpt-4o-2024-11-20-default",
    model_identifier="openai/gpt-4o-2024-11-20",
    system_prompt=DEFAULT_SYSTEM_PROMPT,
    user_prompt_template=DEFAULT_USER_PROMPT_TEMPLATE,
    temperature=0.0,
    max_tokens=800,
    api_key_env="OPENAI_API_KEY",
    notes="OpenAI default frontier model, neutral prompt.",
)

CLAUDE_SONNET_4 = BaselineConfig(
    name="claude-sonnet-4-20250514-default",
    model_identifier="anthropic/claude-sonnet-4-20250514",
    system_prompt=DEFAULT_SYSTEM_PROMPT,
    user_prompt_template=DEFAULT_USER_PROMPT_TEMPLATE,
    temperature=0.0,
    max_tokens=800,
    api_key_env="ANTHROPIC_API_KEY",
    notes="Anthropic default frontier model, neutral prompt.",
)

GEMINI_2_5_PRO = BaselineConfig(
    name="gemini-2.5-pro-default",
    model_identifier="gemini/gemini-2.5-pro",
    system_prompt=DEFAULT_SYSTEM_PROMPT,
    user_prompt_template=DEFAULT_USER_PROMPT_TEMPLATE,
    temperature=0.0,
    max_tokens=800,
    api_key_env="GEMINI_API_KEY",
    notes="Google long-context reference.",
)

GPT_35_TURBO = BaselineConfig(
    name="gpt-3.5-turbo-default",
    model_identifier="openai/gpt-3.5-turbo",
    system_prompt=DEFAULT_SYSTEM_PROMPT,
    user_prompt_template=DEFAULT_USER_PROMPT_TEMPLATE,
    temperature=0.0,
    max_tokens=800,
    api_key_env="OPENAI_API_KEY",
    notes="Deliberate floor — ensures leaderboard has visible spread.",
)

# Open-weight baselines (via OpenRouter or HF Inference Endpoints — pick one
# at submission time; OpenRouter is simpler for v0.1)
LLAMA_3_3_70B = BaselineConfig(
    name="llama-3.3-70b-instruct-default",
    model_identifier="openrouter/meta-llama/llama-3.3-70b-instruct",
    system_prompt=DEFAULT_SYSTEM_PROMPT,
    user_prompt_template=DEFAULT_USER_PROMPT_TEMPLATE,
    temperature=0.0,
    max_tokens=800,
    api_key_env="OPENROUTER_API_KEY",
    notes="Open generalist reference (Meta Llama 3.3, via OpenRouter).",
)

MEDGEMMA_27B = BaselineConfig(
    name="medgemma-27b-it-default",
    model_identifier="openrouter/google/medgemma-27b-it",
    system_prompt=DEFAULT_SYSTEM_PROMPT,
    user_prompt_template=DEFAULT_USER_PROMPT_TEMPLATE,
    temperature=0.0,
    max_tokens=800,
    api_key_env="OPENROUTER_API_KEY",
    notes=(
        "Open medical SLM reference (Google MedGemma, via OpenRouter). "
        "If MedGemma is unavailable on OpenRouter at run time, the launch "
        "set may substitute a directly-hosted HF Inference Endpoint."
    ),
)


# The full preset registry. Keys are names suitable for CLI lookup.
PRESET_BASELINES: dict[str, BaselineConfig] = {
    "gpt-4o": GPT_4O,
    "claude-sonnet-4": CLAUDE_SONNET_4,
    "gemini-2.5-pro": GEMINI_2_5_PRO,
    "llama-3.3-70b": LLAMA_3_3_70B,
    "medgemma-27b": MEDGEMMA_27B,
    "gpt-3.5-turbo": GPT_35_TURBO,
}


# Sentinel: includes the oracle, which is dispatched separately because it
# has no BaselineConfig (no LLM call).
ALL_BASELINE_NAMES: list[str] = ["oracle"] + list(PRESET_BASELINES.keys())


__all__ = [
    "PRESET_BASELINES",
    "ALL_BASELINE_NAMES",
    "GPT_4O",
    "CLAUDE_SONNET_4",
    "GEMINI_2_5_PRO",
    "GPT_35_TURBO",
    "LLAMA_3_3_70B",
    "MEDGEMMA_27B",
]
