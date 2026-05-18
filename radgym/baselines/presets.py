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


# ---------------------------------------------------------------------------
# Two baseline tiers (see METHODOLOGY §5):
#
# SNAPSHOT BASELINES — frozen at the v0.1 launch date. Date-pinned model
#   IDs where available. These are the reproducibility anchors. Once a
#   submission has scored against them, the scores never change.
#
# CURRENT FRONTIER BASELINES — refreshed when a new flagship ships. The
#   "what is SOTA today" view. Previous current-frontier rolls into
#   snapshot when the next refresh happens.
# ---------------------------------------------------------------------------

# === SNAPSHOT BASELINES (frozen at launch) =================================

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
    # Gemini 2.5 Pro is a reasoning model. With max_tokens=2048 and no
    # thinking budget cap, 20% of cases hit the limit with the entire
    # budget consumed by hidden reasoning (output_tokens=2045, visible
    # text=""). Capping thinking to 1024 leaves the remaining 1024 for
    # the JSON answer, which is more than enough for v0.1's short output.
    max_tokens=2048,
    extra_params={"reasoning_effort": "low"},  # LiteLLM passes through to thinking_config
    api_key_env="GEMINI_API_KEY",
    notes=(
        "Google reasoning model reference. reasoning_effort='low' caps "
        "the hidden thinking budget so the visible JSON response isn't "
        "starved of tokens."
    ),
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

# MedGemma deferred to v0.2 — OpenRouter does not host it (returns
# "google/medgemma-27b-it is not a valid model ID" at run time). The
# preset remains defined here for documentation, but is NOT registered
# in PRESET_BASELINES below, so `--baseline all` skips it. v0.2 will
# stand up a local serving harness (Ollama or vLLM) and re-enable.
MEDGEMMA_27B = BaselineConfig(
    name="medgemma-27b-it-default",
    model_identifier="openrouter/google/medgemma-27b-it",
    system_prompt=DEFAULT_SYSTEM_PROMPT,
    user_prompt_template=DEFAULT_USER_PROMPT_TEMPLATE,
    temperature=0.0,
    max_tokens=800,
    api_key_env="OPENROUTER_API_KEY",
    notes=(
        "Open medical SLM reference (Google MedGemma). DEFERRED to v0.2: "
        "OpenRouter does not host this model. Re-enable once a local "
        "Ollama or vLLM endpoint is set up, or HF Inference Endpoints "
        "are configured."
    ),
)


# The full snapshot preset registry. Keys are names suitable for CLI lookup.
# MedGemma is intentionally absent; see comment above.
PRESET_BASELINES: dict[str, BaselineConfig] = {
    "gpt-4o": GPT_4O,
    "claude-sonnet-4": CLAUDE_SONNET_4,
    "gemini-2.5-pro": GEMINI_2_5_PRO,
    "llama-3.3-70b": LLAMA_3_3_70B,
    "gpt-3.5-turbo": GPT_35_TURBO,
}


# === CURRENT FRONTIER BASELINES (refresh-on-flagship) =======================
#
# These represent state-of-the-art as of the date in the registry tag below.
# When a new flagship ships, current-frontier gets refreshed: the previous
# current-frontier rolls into PRESET_BASELINES with a date tag, and the new
# flagship takes its place here.
#
# The bare model identifiers (no date stamp) follow the model alias as it
# is listed on each provider's API. This is deliberately non-pinned —
# current-frontier exists to track moving SOTA, not for reproducibility.
# When the provider deprecates the alias, the score gets archived to
# PRESET_BASELINES with whatever date stamp the API exposed.

CURRENT_FRONTIER_REGISTRY_TAG = "frontier-as-of-2026-05-18"


GPT_5_5 = BaselineConfig(
    name="gpt-5.5-current-frontier",
    model_identifier="openai/gpt-5.5",
    system_prompt=DEFAULT_SYSTEM_PROMPT,
    user_prompt_template=DEFAULT_USER_PROMPT_TEMPLATE,
    # GPT-5.5 family rejects temperature != 1 with BadRequestError. The
    # provider's stance is that reasoning models are deterministic-ish
    # internally and the temperature knob no longer applies. The
    # leaderboard surfaces the actual temperature per baseline so this
    # asymmetry is visible to readers (see METHODOLOGY §5.3).
    temperature=1.0,
    max_tokens=2048,
    api_key_env="OPENAI_API_KEY",
    notes=(
        "OpenAI current frontier as of 2026-05-18. temperature=1 is "
        "provider-mandated for this model class (rejects temp=0)."
    ),
)

GPT_5_5_PRO = BaselineConfig(
    name="gpt-5.5-pro-current-frontier",
    model_identifier="openai/gpt-5.5-pro",
    system_prompt=DEFAULT_SYSTEM_PROMPT,
    user_prompt_template=DEFAULT_USER_PROMPT_TEMPLATE,
    # Same provider constraint as gpt-5.5 — see comment above.
    temperature=1.0,
    max_tokens=4096,
    api_key_env="OPENAI_API_KEY",
    notes=(
        "OpenAI current frontier (pro tier) as of 2026-05-18. "
        "temperature=1 is provider-mandated. Higher max_tokens for "
        "likely-reasoning extended outputs."
    ),
)

CLAUDE_OPUS_4_7 = BaselineConfig(
    name="claude-opus-4-7-current-frontier",
    model_identifier="anthropic/claude-opus-4-7",
    system_prompt=DEFAULT_SYSTEM_PROMPT,
    user_prompt_template=DEFAULT_USER_PROMPT_TEMPLATE,
    # Opus 4.7 rejects temperature=0 ("temperature is deprecated for this
    # model"). Same provider-mandate pattern as GPT-5.5 family; see §5.3
    # in METHODOLOGY for the disclosure.
    temperature=1.0,
    max_tokens=2048,
    api_key_env="ANTHROPIC_API_KEY",
    notes=(
        "Anthropic current frontier (Opus tier) as of 2026-05-18. "
        "temperature=1 is provider-mandated for this reasoning model."
    ),
)

CLAUDE_SONNET_4_6 = BaselineConfig(
    name="claude-sonnet-4-6-current-frontier",
    model_identifier="anthropic/claude-sonnet-4-6",
    system_prompt=DEFAULT_SYSTEM_PROMPT,
    user_prompt_template=DEFAULT_USER_PROMPT_TEMPLATE,
    temperature=0.0,
    max_tokens=2048,
    api_key_env="ANTHROPIC_API_KEY",
    notes="Anthropic current frontier (Sonnet tier) as of 2026-05-18.",
)

GEMINI_3_1_PRO = BaselineConfig(
    name="gemini-3.1-pro-preview-current-frontier",
    model_identifier="gemini/gemini-3.1-pro-preview",
    system_prompt=DEFAULT_SYSTEM_PROMPT,
    user_prompt_template=DEFAULT_USER_PROMPT_TEMPLATE,
    temperature=0.0,
    # Reasoning model — same hidden-thinking-budget concern as 2.5 Pro.
    # Smoke test returned empty visible content at max_tokens=40; capping
    # reasoning_effort and giving 2048 visible-output budget.
    max_tokens=2048,
    extra_params={"reasoning_effort": "low"},
    api_key_env="GEMINI_API_KEY",
    notes=(
        "Google current frontier (preview) as of 2026-05-18. "
        "reasoning_effort='low' to cap hidden thinking budget."
    ),
)

DEEPSEEK_V4_PRO = BaselineConfig(
    name="deepseek-v4-pro-current-frontier",
    model_identifier="openrouter/deepseek/deepseek-v4-pro",
    system_prompt=DEFAULT_SYSTEM_PROMPT,
    user_prompt_template=DEFAULT_USER_PROMPT_TEMPLATE,
    temperature=0.0,
    # DeepSeek V4 Pro is a reasoning model that burns ~2000-2600 hidden
    # tokens per Fleischner case even at reasoning_effort=low. At the
    # default 2048 cap the visible JSON gets truncated mid-rationale,
    # producing a 16% malformed rate. 4096 gives ~1500 tokens of headroom
    # for the visible response after reasoning settles.
    max_tokens=4096,
    extra_params={"reasoning_effort": "low"},
    api_key_env="OPENROUTER_API_KEY",
    notes=(
        "DeepSeek current frontier (open-weight reasoning) as of 2026-05-18, "
        "via OpenRouter. The strongest non-Western frontier reference. "
        "Higher max_tokens to accommodate the model's reasoning budget."
    ),
)

LLAMA_4_MAVERICK = BaselineConfig(
    name="llama-4-maverick-current-frontier",
    model_identifier="openrouter/meta-llama/llama-4-maverick",
    system_prompt=DEFAULT_SYSTEM_PROMPT,
    user_prompt_template=DEFAULT_USER_PROMPT_TEMPLATE,
    temperature=0.0,
    max_tokens=2048,
    api_key_env="OPENROUTER_API_KEY",
    notes=(
        "Meta current frontier (open-weight) as of 2026-05-18, via OpenRouter. "
        "Successor to the Llama 3.3 snapshot baseline; the 'open generalist' "
        "frontier reference."
    ),
)


CURRENT_FRONTIER_BASELINES: dict[str, BaselineConfig] = {
    "gpt-5.5": GPT_5_5,
    "gpt-5.5-pro": GPT_5_5_PRO,
    "claude-opus-4-7": CLAUDE_OPUS_4_7,
    "claude-sonnet-4-6": CLAUDE_SONNET_4_6,
    "gemini-3.1-pro-preview": GEMINI_3_1_PRO,
    "deepseek-v4-pro": DEEPSEEK_V4_PRO,
    "llama-4-maverick": LLAMA_4_MAVERICK,
}


# Sentinel: includes the oracle, which is dispatched separately because it
# has no BaselineConfig (no LLM call). Also includes current-frontier names.
ALL_BASELINE_NAMES: list[str] = (
    ["oracle"]
    + list(PRESET_BASELINES.keys())
    + list(CURRENT_FRONTIER_BASELINES.keys())
)


# Unified lookup: snapshot + current-frontier. CLI/runner uses this so
# either name resolves transparently.
ALL_BASELINES: dict[str, BaselineConfig] = {
    **PRESET_BASELINES,
    **CURRENT_FRONTIER_BASELINES,
}


__all__ = [
    "PRESET_BASELINES",
    "CURRENT_FRONTIER_BASELINES",
    "CURRENT_FRONTIER_REGISTRY_TAG",
    "ALL_BASELINE_NAMES",
    "ALL_BASELINES",
    "GPT_4O",
    "CLAUDE_SONNET_4",
    "GEMINI_2_5_PRO",
    "GPT_35_TURBO",
    "LLAMA_3_3_70B",
    "MEDGEMMA_27B",
    "GPT_5_5",
    "GPT_5_5_PRO",
    "CLAUDE_OPUS_4_7",
    "CLAUDE_SONNET_4_6",
    "GEMINI_3_1_PRO",
    "DEEPSEEK_V4_PRO",
    "LLAMA_4_MAVERICK",
]
