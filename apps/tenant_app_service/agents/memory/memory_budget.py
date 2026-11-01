"""Token and field budgets for agent harness and thread roll-up. Not environment flags."""

# Model output cap (``max_tokens``) is separate. This is the input window used
# when a profile does not publish its own context length.
DEFAULT_MODEL_INPUT_TOKEN_LIMIT = 128_000
MODEL_OUTPUT_HEADROOM_TOKENS = 4_096
THREAD_SUMMARY_MAX_TOKENS = 2_000
# Bound each aged-out turn field before it is sent to the thread summarizer.
THREAD_SUMMARY_TURN_FIELD_CHARS = 4_000
# Fold at least this many aged-out pair turns in one LLM call unless pressure forces earlier.
THREAD_SUMMARY_MIN_AGED_PAIRS = 2
# When summary + verbatim tail estimate exceeds this, flush pending delta even if batch is small.
THREAD_SUMMARY_CONTEXT_PRESSURE_RATIO = 0.75


def input_token_budget() -> int:
    """Tokens available for the assembled prompt, leaving room for the model reply."""
    return DEFAULT_MODEL_INPUT_TOKEN_LIMIT - MODEL_OUTPUT_HEADROOM_TOKENS


def thread_summary_context_pressure_tokens() -> int:
    """Estimated prompt size above which aged-out pairs should be folded into the summary."""
    return int(input_token_budget() * THREAD_SUMMARY_CONTEXT_PRESSURE_RATIO)
