"""Utility functions for entity lookups."""

import re
from difflib import SequenceMatcher
from typing import Any

from homeassistant.core import HomeAssistant, State
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import intent


class EntityNotFoundError(HomeAssistantError):
    """
    Exception raised when an entity is not found.

    Carries the closest ranked candidates (if any) so the caller can
    present them for an exact retry instead of failing blind.
    """

    def __init__(
        self,
        message: str = "Entity not found",
        candidates: list[dict[str, Any]] | None = None,
    ) -> None:
        """Initialize the exception, optionally with ranked candidates."""
        super().__init__(message)
        self.candidates: list[dict[str, Any]] = candidates or []


# Minimum ranked score for a non-exact match to be accepted, and the
# minimum lead it must hold over the runner-up. Both are deliberately
# conservative: a wrong silent pick is worse than returning candidates
# and letting the caller retry with an exact entity_id.
MIN_MATCH_SCORE = 55.0
MIN_MATCH_MARGIN = 12.0

# Maximum number of candidate entities returned on a failed lookup.
MAX_CANDIDATES = 5

_TOKEN_SPLIT = re.compile(r"[^a-z0-9]+")


def _tokens(text: str) -> list[str]:
    """Split a name into lowercase alphanumeric tokens."""
    return [token for token in _TOKEN_SPLIT.split(text.lower()) if token]


def _normalize(text: str) -> str:
    """Normalize a name for comparison: lowercase, single-spaced tokens."""
    return " ".join(_tokens(text))


def _entity_areas(
    exposed_entities: dict[str, dict[str, Any]], entity_id: str
) -> list[str]:
    """Return the lowercased area names recorded for an exposed entity."""
    entity_info = exposed_entities.get(entity_id) or {}
    areas = entity_info.get("areas")
    if not areas:
        return []
    return [a.lower().strip() for a in areas.split(", ") if a.strip()]


def _score_name(query_norm: str, query_tokens: set[str], candidate_name: str) -> float:
    """Score how well one candidate name matches the query name."""
    candidate_norm = _normalize(candidate_name)
    if not candidate_norm or not query_norm:
        return 0.0
    if candidate_norm == query_norm:
        return 100.0

    candidate_tokens = set(_tokens(candidate_name))
    if query_tokens and candidate_tokens:
        if query_tokens <= candidate_tokens:
            # The query names a subset of the candidate ("dining room
            # temperature" for "Dining room temperature average").
            return 80.0
        if candidate_tokens <= query_tokens:
            return 72.0
        jaccard = len(query_tokens & candidate_tokens) / len(
            query_tokens | candidate_tokens
        )
        token_score = jaccard * 60.0
    else:
        token_score = 0.0

    fuzzy_score = SequenceMatcher(None, query_norm, candidate_norm).ratio() * 55.0
    return max(token_score, fuzzy_score)


def _ranked_matches(
    hass: HomeAssistant,
    entity_name: str,
    domain: str | None,
    area: str | None,
    exposed_entities: dict[str, dict[str, Any]],
) -> list[tuple[float, State, str]]:
    """
    Score every exposed entity against the query name.

    Returns (score, state, display name) tuples, best first. Only
    exposed entities are ever considered — exposure remains the
    permission boundary. Domain and area are scoring boosts here,
    not hard filters: a model that guesses the wrong domain should
    not lose an otherwise unambiguous name match.
    """
    query_norm = _normalize(entity_name)
    query_tokens = set(_tokens(entity_name))
    domain_norm = domain.lower().strip() if domain else None
    area_norm = area.lower().strip() if area else None

    scored: list[tuple[float, State, str]] = []
    for state in hass.states.async_all():
        if state.entity_id not in exposed_entities:
            continue

        entity_entry = er.async_get(hass).async_get(state.entity_id)
        names = intent.async_get_entity_aliases(hass, entity_entry, state=state)
        check_names = [state.entity_id, *names]

        score = max(
            (_score_name(query_norm, query_tokens, name) for name in check_names),
            default=0.0,
        )
        if score <= 0:
            continue

        if domain_norm and state.domain == domain_norm:
            score += 8.0
        areas = _entity_areas(exposed_entities, state.entity_id)
        if area_norm and area_norm in areas:
            score += 8.0
        device_class = state.attributes.get("device_class")
        if device_class and device_class in query_tokens:
            score += 5.0

        display_name = next(
            (name for name in check_names if name != state.entity_id),
            state.entity_id,
        )
        scored.append((score, state, display_name))

    scored.sort(key=lambda item: item[0], reverse=True)
    return scored


def _candidate_dicts(
    ranked: list[tuple[float, State, str]],
    exposed_entities: dict[str, dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    """Format ranked matches as LLM-friendly candidate dicts."""
    candidates: list[dict[str, Any]] = []
    for score, state, display_name in ranked[:limit]:
        entity_info = exposed_entities.get(state.entity_id) or {}
        candidates.append(
            {
                "entity_id": state.entity_id,
                "name": display_name,
                "domain": state.domain,
                "areas": entity_info.get("areas"),
                "score": round(score, 1),
            }
        )
    return candidates


def find_entity_candidates(
    hass: HomeAssistant,
    entity_name: str | None,
    domain: str | None = None,
    area: str | None = None,
    *,
    exposed_entities: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Return the closest exposed entities to a (possibly partial) name.

    With no name, this is a browse: exposed entities matching the
    domain/area filters are returned in state order. Unexposed
    entities are never included.
    """
    if entity_name:
        ranked = _ranked_matches(hass, entity_name, domain, area, exposed_entities)
        return _candidate_dicts(ranked, exposed_entities, MAX_CANDIDATES)

    domain_norm = domain.lower().strip() if domain else None
    area_norm = area.lower().strip() if area else None
    candidates: list[dict[str, Any]] = []
    for state in hass.states.async_all():
        if state.entity_id not in exposed_entities:
            continue
        if domain_norm and state.domain != domain_norm:
            continue
        if area_norm and area_norm not in _entity_areas(
            exposed_entities, state.entity_id
        ):
            continue
        entity_info = exposed_entities.get(state.entity_id) or {}
        candidates.append(
            {
                "entity_id": state.entity_id,
                "name": entity_info.get("names") or state.entity_id,
                "domain": state.domain,
                "areas": entity_info.get("areas"),
            }
        )
        if len(candidates) >= MAX_CANDIDATES:
            break
    return candidates


def find_entity_by_name(
    hass: HomeAssistant,
    entity_name: str,
    domain: str | None = None,
    area: str | None = None,
    *,
    exposed_entities: dict[str, dict[str, Any]],
) -> State:
    """
    Find an entity by its name or aliases.

    Resolution runs in two stages:

    1. Exact normalized match against the entity id, friendly name or
       aliases, within the domain/area filters when given (the
       historical behaviour).
    2. Ranked matching over all exposed entities, where domain/area
       act as boosts rather than hard filters. A ranked match is only
       accepted when it scores at least MIN_MATCH_SCORE and leads the
       runner-up by MIN_MATCH_MARGIN — anything closer is ambiguous
       and raises EntityNotFoundError carrying the ranked candidates
       so the caller can retry with an exact entity_id.
    """
    if not entity_name or not entity_name.strip():
        msg = "No entity name given"
        raise EntityNotFoundError(
            msg,
            candidates=find_entity_candidates(
                hass, None, domain, area, exposed_entities=exposed_entities
            ),
        )

    entity_name_norm = entity_name.lower().strip()
    domain_norm = domain.lower().strip() if domain else None
    area_norm = area.lower().strip() if area else None

    # Stage 1: exact match within the supplied filters.
    for state in hass.states.async_all():
        if state.entity_id not in exposed_entities:
            continue
        if domain_norm and state.domain != domain_norm:
            continue
        if area_norm and area_norm not in _entity_areas(
            exposed_entities, state.entity_id
        ):
            continue

        entity_entry = er.async_get(hass).async_get(state.entity_id)
        names = intent.async_get_entity_aliases(hass, entity_entry, state=state)
        check_names = [state.entity_id, *names]
        for name in check_names:
            if name.lower().strip() == entity_name_norm:
                return state

    # Stage 2: ranked match, filters relaxed to boosts.
    ranked = _ranked_matches(hass, entity_name, domain, area, exposed_entities)
    if ranked:
        top_score, top_state, _ = ranked[0]
        runner_up = ranked[1][0] if len(ranked) > 1 else 0.0
        if top_score >= MIN_MATCH_SCORE and (top_score - runner_up) >= MIN_MATCH_MARGIN:
            return top_state

    msg = f"No exposed entity matched '{entity_name}'"
    raise EntityNotFoundError(
        msg,
        candidates=_candidate_dicts(ranked, exposed_entities, limit=MAX_CANDIDATES),
    )
