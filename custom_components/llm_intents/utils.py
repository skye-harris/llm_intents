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


def _passes_filters(
    state: State,
    domain_norm: str | None,
    area_norm: str | None,
    exposed_entities: dict[str, dict[str, Any]],
) -> bool:
    """
    Apply the domain/area filters exactly as the exact-match stage does.

    Both are hard filters, matching Home Assistant's own Assist
    behavior: when a domain is given, only that domain passes; when an
    area is given, an entity with recorded areas passes only if the
    area is among them (an entity with no recorded areas is not
    excluded, as in upstream's exact-match implementation).
    """
    if domain_norm is not None and state.domain != domain_norm:
        return False
    if area_norm is not None:
        entity_areas = _entity_areas(exposed_entities, state.entity_id)
        if entity_areas and area_norm not in entity_areas:
            return False
    return True


def _ranked_matches(
    hass: HomeAssistant,
    entity_name: str,
    domain: str | None,
    area: str | None,
    exposed_entities: dict[str, dict[str, Any]],
) -> list[tuple[float, State, str]]:
    """
    Score the exposed entities that pass the filters against the name.

    Returns (score, state, display name) tuples, best first. Domain
    and area are hard filters, applied before scoring: an entity
    outside the requested domain or area is never scored, picked, or
    returned as a candidate. Only the name match is scored — the
    small boosts below only order entities that already passed the
    filters (an entity confirmed in the requested area ranks above
    one with no recorded area); they cannot pull an out-of-filter
    entity into the results. Only exposed entities are ever
    considered — exposure remains the permission boundary.
    """
    query_norm = _normalize(entity_name)
    query_tokens = set(_tokens(entity_name))
    domain_norm = domain.lower().strip() if domain else None
    area_norm = area.lower().strip() if area else None

    scored: list[tuple[float, State, str]] = []
    for state in hass.states.async_all():
        if state.entity_id not in exposed_entities:
            continue
        if not _passes_filters(state, domain_norm, area_norm, exposed_entities):
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

    Candidates only ever come from the entities that pass the
    domain/area filters. With no name, this is a browse: exposed
    entities passing the filters are returned in state order.
    Unexposed entities are never included.
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
        if not _passes_filters(state, domain_norm, area_norm, exposed_entities):
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
       aliases — upstream's implementation, unchanged. Domain and
       area are hard filters, as they are there.
    2. Ranked matching, but only over the entities that pass the
       same filters: a partial or near-miss *name* is forgiven, a
       wrong domain or area is not. A ranked match is only accepted
       when it scores at least MIN_MATCH_SCORE and leads the
       runner-up by MIN_MATCH_MARGIN — anything closer is ambiguous
       and raises EntityNotFoundError carrying the ranked candidates
       (from the filtered set only) so the caller can retry with an
       exact entity_id.
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

    # Stage 1: exact match — upstream's implementation. (Domain is
    # optional in this tool's schema, so its check is skipped when no
    # domain was supplied; when one is, the logic is upstream's.)
    for state in hass.states.async_all():
        # Exposed entities filter
        if state.entity_id not in exposed_entities:
            continue

        # Domain filter
        if domain_norm is not None and state.domain != domain_norm:
            continue

        # Area filter
        if area_norm is not None:
            entity_info = exposed_entities[state.entity_id]
            entity_areas = entity_info.get("areas")
            if entity_areas:
                area_list = [a.lower().strip() for a in entity_areas.split(", ")]
                if area_norm not in area_list:
                    continue

        # Name matching
        entity_entry = er.async_get(hass).async_get(state.entity_id)
        names = intent.async_get_entity_aliases(hass, entity_entry, state=state)
        check_names = [state.entity_id, *names]
        for name in check_names:
            if name.lower().strip() == entity_name_norm:
                return state

    # Stage 2: ranked match over the filtered set only.
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
