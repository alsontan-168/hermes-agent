"""Registry for agent-backed model clients.

Most providers are an HTTP endpoint, so ``create_openai_client`` can build an
``OpenAI`` client for them from ``client_kwargs``. A few are not: the model
lives behind a local agent subprocess (Copilot ACP, Claude Code) or behind a
pure in-process facade (MoA). For those, *the facade is the client* — there is
no wire endpoint for httpx to talk to.

``create_openai_client`` already hard-codes three such branches (``moa``,
``copilot-acp``, ``gemini``). This registry is the same idea made extensible,
so an out-of-tree provider plugin can supply one without editing core: the
plugin calls ``register_model_client_factory`` at import time, and
``create_openai_client`` consults the registry before its built-in chain.

Provider plugins are imported from ``$HERMES_HOME/plugins/model-providers/``
(see ``providers/_import_plugin_dir``), so a factory registered from there
survives ``hermes update`` — nothing about the provider needs to live in this
repository.

Deliberately NOT a general-purpose hook: it can only be consulted at client
construction. Nothing here can intercept a turn, own the agent loop, or see
tool results. Hermes keeps ownership of the conversation and of tool
execution; the factory only decides what object ``.chat.completions.create()``
gets called on.

A factory is called as::

    factory(agent=agent, client_kwargs=client_kwargs, reason=reason, shared=shared)

and must return an object exposing at least ``.chat.completions.create(**kw)``,
``.close()`` and ``.is_closed`` — the same duck type
``agent/copilot_acp_client.py`` implements.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

ModelClientFactory = Callable[..., Any]

# provider name (lowercased) -> factory
_BY_PROVIDER: dict[str, ModelClientFactory] = {}
# base_url scheme (no "://") -> factory
_BY_SCHEME: dict[str, ModelClientFactory] = {}


def register_model_client_factory(
    factory: ModelClientFactory,
    *,
    provider: Optional[str] = None,
    base_url_scheme: Optional[str] = None,
) -> None:
    """Register ``factory`` for a provider name and/or a base_url scheme.

    Both keys are matched, because Hermes reaches the same provider by either
    route: ``agent.provider`` is set from config, while a ``custom_providers:``
    entry only carries ``base_url``. Registering both is what makes the
    provider selectable through the model picker *and* through a raw base_url.

    Later registrations for the same key win, so a user plugin in
    ``$HERMES_HOME`` can deliberately shadow a bundled one.
    """
    if provider is None and base_url_scheme is None:
        raise ValueError("register_model_client_factory needs provider= or base_url_scheme=")
    if provider:
        _BY_PROVIDER[provider.strip().lower()] = factory
    if base_url_scheme:
        _BY_SCHEME[base_url_scheme.strip().lower().rstrip(":/")] = factory


def resolve_model_client_factory(
    provider: Optional[str],
    base_url: Optional[str],
) -> Optional[ModelClientFactory]:
    """Return the factory for this provider/base_url, or None.

    None is the overwhelmingly common answer, so this stays allocation-free
    and never raises: it sits on the hot path of every client construction,
    and a bug here would break every provider rather than just one.
    """
    if _BY_PROVIDER:
        key = (provider or "").strip().lower()
        if key:
            factory = _BY_PROVIDER.get(key)
            if factory is not None:
                return factory
    if _BY_SCHEME:
        url = str(base_url or "").strip().lower()
        head = url.split("://", 1)[0] if "://" in url else ""
        if head:
            return _BY_SCHEME.get(head)
    return None


def registered_model_client_factories() -> dict[str, list[str]]:
    """Introspection for ``hermes doctor`` and tests."""
    return {
        "providers": sorted(_BY_PROVIDER),
        "schemes": sorted(_BY_SCHEME),
    }
