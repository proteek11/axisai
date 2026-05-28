"""
Token cost estimation.
Prices are approximate and should be updated as providers change pricing.
All costs in USD.
"""

# Price per 1M tokens: {provider: {model_pattern: (input_cost, output_cost)}}
# Update these as provider pricing changes
PRICING: dict[str, dict[str, tuple[float, float]]] = {
    "openai": {
        "gpt-4o":                   (5.00,   15.00),
        "gpt-4o-mini":              (0.15,    0.60),
        "gpt-4-turbo":             (10.00,   30.00),
        "gpt-4":                   (30.00,   60.00),
        "gpt-3.5-turbo":            (0.50,    1.50),
        "text-embedding-3-small":   (0.02,    0.00),
        "text-embedding-3-large":   (0.13,    0.00),
        "text-embedding-ada-002":   (0.10,    0.00),
        "o1":                      (15.00,   60.00),
        "o1-mini":                  (3.00,   12.00),
    },
    "anthropic": {
        "claude-opus-4":           (15.00,   75.00),
        "claude-sonnet-4":          (3.00,   15.00),
        "claude-haiku-4":           (0.25,    1.25),
        "claude-3-5-sonnet":        (3.00,   15.00),
        "claude-3-5-haiku":         (0.80,    4.00),
        "claude-3-opus":           (15.00,   75.00),
    },
    "mistral": {
        "mistral-large":            (2.00,    6.00),
        "mistral-small":            (0.20,    0.60),
        "mistral-nemo":             (0.15,    0.15),
        "codestral":                (0.20,    0.60),
        "mistral-embed":            (0.10,    0.00),
    },
}


def estimate_cost(
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> float | None:
    """
    Estimate cost in USD for an AI call.
    Returns None if pricing is unknown for the provider/model.
    """
    provider_pricing = PRICING.get(provider.lower())
    if not provider_pricing:
        return None

    # Find matching model (partial match, longest match wins)
    model_lower = model.lower()
    best_match = None
    best_match_len = 0

    for model_pattern, (input_price, output_price) in provider_pricing.items():
        if model_pattern in model_lower and len(model_pattern) > best_match_len:
            best_match = (input_price, output_price)
            best_match_len = len(model_pattern)

    if best_match is None:
        return None

    input_price, output_price = best_match
    cost = (prompt_tokens * input_price + completion_tokens * output_price) / 1_000_000
    return round(cost, 8)


def format_cost(cost_usd: float | None) -> str:
    """Format cost for display (e.g., '$0.000123')."""
    if cost_usd is None:
        return "unknown"
    if cost_usd < 0.001:
        return f"${cost_usd:.6f}"
    return f"${cost_usd:.4f}"
