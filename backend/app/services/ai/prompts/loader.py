"""
Prompt template loader — reads YAML files and formats them with context variables.

Prompts are stored as YAML files (editable without code deploys).
Each prompt has: name, version, system, user, temperature, max_tokens.
The `user` field is a Python format string — {variable} placeholders are filled at runtime.
"""
import json
from functools import lru_cache
from pathlib import Path

import yaml

PROMPTS_DIR = Path(__file__).parent


@lru_cache(maxsize=50)
def load_prompt(name: str) -> dict:
    """
    Load and cache a prompt template by name.
    e.g., load_prompt("summary") → reads summary.yaml

    Returns dict with: name, version, system, user, temperature, max_tokens
    """
    prompt_path = PROMPTS_DIR / f"{name}.yaml"
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt template not found: {prompt_path}")

    with open(prompt_path) as f:
        prompt = yaml.safe_load(f)

    return prompt


def build_messages(
    prompt_name: str,
    variables: dict,
) -> tuple[list[dict], dict]:
    """
    Build the messages list for an AI completion call.

    Args:
        prompt_name: Name of the YAML prompt file (without extension)
        variables:   Dict of {variable: value} to substitute into the user template

    Returns:
        (messages, prompt_config) where:
          messages = [{"role": "system", ...}, {"role": "user", ...}]
          prompt_config = {temperature, max_tokens, version, name}

    Raises:
        KeyError: if a required template variable is missing
    """
    prompt = load_prompt(prompt_name)

    # Format both system and user templates with provided variables.
    # The system template may reference {language} to instruct the model
    # which language to respond in. Unknown {variables} in the template
    # that are not provided will raise KeyError (fail-fast on misconfiguration).
    system_content = prompt["system"].strip().format(**variables)
    user_content = prompt["user"].format(**variables)

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content.strip()},
    ]

    config = {
        "temperature": prompt.get("temperature", 0.3),
        "max_tokens": prompt.get("max_tokens", 2000),
        "prompt_version": f"{prompt['name']}_{prompt['version']}",
        "prompt_name": prompt["name"],
    }

    return messages, config


def get_prompt_version(name: str) -> str:
    """Get the version string for a prompt (e.g., 'summary_v1')."""
    prompt = load_prompt(name)
    return f"{prompt['name']}_{prompt['version']}"
