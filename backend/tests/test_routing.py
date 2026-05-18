from __future__ import annotations

import pytest

from gateway.routing.policy import candidates_for, known_models


def test_known_aliases_resolve() -> None:
    chain = candidates_for("default-fast")
    assert len(chain) >= 2
    assert chain[0].provider == "openai"


def test_smart_chain_has_bedrock_in_middle() -> None:
    chain = candidates_for("default-smart")
    providers = [c.provider for c in chain]
    assert "bedrock" in providers


def test_provider_colon_model_passthrough() -> None:
    chain = candidates_for("anthropic:claude-haiku-4-5")
    assert len(chain) == 1
    assert chain[0].provider == "anthropic"
    assert chain[0].model == "claude-haiku-4-5"


def test_unknown_alias_rejected() -> None:
    with pytest.raises(ValueError):
        candidates_for("totally-unknown-alias")


def test_known_models_includes_defaults() -> None:
    aliases = set(known_models())
    assert "default-fast" in aliases
    assert "default-smart" in aliases
