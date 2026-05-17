"""Baseline agents for RadGym v0.1.

A "baseline" is a (model_identifier, system_prompt, decoding_params) triple
that produces an AgentResponse for each case. v0.1 ships seven baselines:

  - oracle_rules_engine    : the deterministic Fleischner 2017 algorithm
                             (no LLM call; this is the leaderboard floor)
  - gpt-4o-2024-11-20      : OpenAI default
  - claude-sonnet-4        : Anthropic default
  - gemini-2.5-pro         : Google long-context default
  - llama-3.3-70b-instruct : open generalist
  - medgemma-27b-it        : open medical SLM
  - gpt-3.5-turbo          : deliberate low-floor for leaderboard spread

External submissions follow the same baseline contract.

See `radgym/baselines/runner.py` for the execution engine and
`radgym/baselines/oracle_baseline.py` for the rules-engine wrapper.
"""
