"""
SevaForge Knowledge Graph — US-045

Entity extraction and relationship-aware retrieval.
Stores entities (services, APIs, configs, agents) and their relationships
as a directed graph for context-enriched search.

Architecture:
    Documents → Entity Extraction → Graph Storage
    Query → Graph Traversal → Related Entities → Enriched Context
"""

from __future__ import annotations

import logging
import re
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ── Enums ─────────────────────────────────────────────────────────────


class EntityType(str, Enum):
    SERVICE = "service"
    API = "api"
    AGENT = "agent"
    CONFIG = "config"
    DATABASE = "database"
    MODEL = "model"
    PIPELINE = "pipeline"
    DOCUMENT = "document"
    CONCEPT = "concept"
    PERSON = "person"
    TOOL = "tool"
    CUSTOM = "custom"


class RelationshipType(str, Enum):
    DEPENDS_ON = "depends_on"
    CALLS = "calls"
    PRODUCES = "produces"
    CONSUMES = "consumes"
    CONTAINS = "contains"
    PART_OF = "part_of"
    RELATED_TO = "related_to"
    CONFIGURED_BY = "configured_by"
    DEPLOYED_ON = "deployed_on"
    TESTED_BY = "tested_by"
    DOCUMENTED_IN = "documented_in"
    EXTENDS = "extends"


# ── Data Models ───────────────────────────────────────────────────────


@dataclass
class Entity:
    """A node in the knowledge graph."""
    entity_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    entity_type: EntityType = EntityType.CONCEPT
    description: str = ""
    properties: dict[str, Any] = field(default_factory=dict)
    source_doc_id: str = ""         # Which document this was extracted from
    aliases: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "name": self.name,
            "type": self.entity_type.value,
            "description": self.description,
            "properties": self.properties,
            "aliases": self.aliases,
        }


@dataclass
class Relationship:
    """A directed edge in the knowledge graph."""
    relationship_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source_id: str = ""              # Source entity ID
    target_id: str = ""              # Target entity ID
    relationship_type: RelationshipType = RelationshipType.RELATED_TO
    weight: float = 1.0              # Strength/confidence of relationship
    properties: dict[str, Any] = field(default_factory=dict)
    source_doc_id: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "relationship_id": self.relationship_id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "type": self.relationship_type.value,
            "weight": self.weight,
            "properties": self.properties,
        }


@dataclass
class GraphQueryResult:
    """Result of a graph traversal query."""
    entities: list[Entity] = field(default_factory=list)
    relationships: list[Relationship] = field(default_factory=list)
    paths: list[list[str]] = field(default_factory=list)  # Paths as entity ID sequences
    query_depth: int = 0
    total_nodes_visited: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "entities": [e.to_dict() for e in self.entities],
            "relationships": [r.to_dict() for r in self.relationships],
            "paths": self.paths,
            "query_depth": self.query_depth,
            "total_nodes_visited": self.total_nodes_visited,
        }


# ── Knowledge Graph ──────────────────────────────────────────────────


class KnowledgeGraph:
    """
    In-memory knowledge graph for entity-relationship storage and traversal.

    Supports:
    - Entity CRUD with type classification and aliases
    - Relationship creation with typed edges and weights
    - BFS/DFS traversal with depth limits
    - Subgraph extraction around a focal entity
    - Shortest path between entities
    - Entity search by name, type, or pattern
    - Rule-based entity extraction from text
    """

    def __init__(self):
        self._entities: dict[str, Entity] = {}
        self._relationships: dict[str, Relationship] = {}
        self._outgoing: dict[str, list[str]] = defaultdict(list)  # entity → [rel_ids]
        self._incoming: dict[str, list[str]] = defaultdict(list)  # entity → [rel_ids]
        self._name_index: dict[str, str] = {}  # lowercase name → entity_id
        self._alias_index: dict[str, str] = {}  # lowercase alias → entity_id

    # ── Entity CRUD ───────────────────────────────────────────────────

    def add_entity(self, entity: Entity) -> str:
        """Add an entity to the graph."""
        self._entities[entity.entity_id] = entity
        self._name_index[entity.name.lower()] = entity.entity_id
        for alias in entity.aliases:
            self._alias_index[alias.lower()] = entity.entity_id
        logger.debug("KG: added entity '%s' (%s)", entity.name, entity.entity_type.value)
        return entity.entity_id

    def get_entity(self, entity_id: str) -> Entity | None:
        return self._entities.get(entity_id)

    def find_entity(self, name: str) -> Entity | None:
        """Find entity by name or alias (case-insensitive)."""
        name_lower = name.lower()
        eid = self._name_index.get(name_lower) or self._alias_index.get(name_lower)
        return self._entities.get(eid) if eid else None

    def remove_entity(self, entity_id: str) -> bool:
        """Remove an entity and all its relationships."""
        if entity_id not in self._entities:
            return False

        entity = self._entities[entity_id]
        # Remove name/alias indexes
        self._name_index.pop(entity.name.lower(), None)
        for alias in entity.aliases:
            self._alias_index.pop(alias.lower(), None)

        # Remove all connected relationships
        rel_ids = list(self._outgoing.get(entity_id, [])) + list(self._incoming.get(entity_id, []))
        for rid in rel_ids:
            self._remove_relationship_internal(rid)

        del self._entities[entity_id]
        self._outgoing.pop(entity_id, None)
        self._incoming.pop(entity_id, None)
        return True

    def list_entities(
        self,
        entity_type: EntityType | None = None,
        limit: int = 100,
    ) -> list[Entity]:
        """List entities with optional type filter."""
        entities = list(self._entities.values())
        if entity_type:
            entities = [e for e in entities if e.entity_type == entity_type]
        return entities[:limit]

    def search_entities(self, query: str, limit: int = 20) -> list[Entity]:
        """Search entities by name/alias/description substring."""
        query_lower = query.lower()
        results = []
        for entity in self._entities.values():
            if (
                query_lower in entity.name.lower()
                or query_lower in entity.description.lower()
                or any(query_lower in a.lower() for a in entity.aliases)
            ):
                results.append(entity)
                if len(results) >= limit:
                    break
        return results

    # ── Relationship CRUD ─────────────────────────────────────────────

    def add_relationship(self, rel: Relationship) -> str:
        """Add a relationship between two entities."""
        if rel.source_id not in self._entities:
            raise ValueError(f"Source entity '{rel.source_id}' not found")
        if rel.target_id not in self._entities:
            raise ValueError(f"Target entity '{rel.target_id}' not found")

        self._relationships[rel.relationship_id] = rel
        self._outgoing[rel.source_id].append(rel.relationship_id)
        self._incoming[rel.target_id].append(rel.relationship_id)

        src = self._entities[rel.source_id].name
        tgt = self._entities[rel.target_id].name
        logger.debug("KG: %s -[%s]-> %s", src, rel.relationship_type.value, tgt)
        return rel.relationship_id

    def get_relationships(
        self,
        entity_id: str,
        direction: str = "both",
        rel_type: RelationshipType | None = None,
    ) -> list[Relationship]:
        """Get relationships for an entity."""
        rel_ids: list[str] = []
        if direction in ("out", "both"):
            rel_ids.extend(self._outgoing.get(entity_id, []))
        if direction in ("in", "both"):
            rel_ids.extend(self._incoming.get(entity_id, []))

        rels = [self._relationships[rid] for rid in rel_ids if rid in self._relationships]
        if rel_type:
            rels = [r for r in rels if r.relationship_type == rel_type]
        return rels

    def _remove_relationship_internal(self, rel_id: str) -> None:
        """Internal removal without entity existence check."""
        rel = self._relationships.get(rel_id)
        if not rel:
            return
        if rel_id in self._outgoing.get(rel.source_id, []):
            self._outgoing[rel.source_id].remove(rel_id)
        if rel_id in self._incoming.get(rel.target_id, []):
            self._incoming[rel.target_id].remove(rel_id)
        del self._relationships[rel_id]

    def remove_relationship(self, rel_id: str) -> bool:
        if rel_id not in self._relationships:
            return False
        self._remove_relationship_internal(rel_id)
        return True

    # ── Graph Traversal ───────────────────────────────────────────────

    def get_neighbors(
        self,
        entity_id: str,
        depth: int = 1,
        rel_types: list[RelationshipType] | None = None,
    ) -> GraphQueryResult:
        """BFS traversal to get neighbors up to a certain depth."""
        if entity_id not in self._entities:
            return GraphQueryResult()

        visited: set[str] = set()
        entities: list[Entity] = []
        relationships: list[Relationship] = []
        queue: deque[tuple[str, int]] = deque([(entity_id, 0)])

        while queue:
            current_id, current_depth = queue.popleft()
            if current_id in visited:
                continue
            visited.add(current_id)

            entity = self._entities.get(current_id)
            if entity:
                entities.append(entity)

            if current_depth >= depth:
                continue

            # Traverse outgoing edges
            for rel_id in self._outgoing.get(current_id, []):
                rel = self._relationships.get(rel_id)
                if not rel:
                    continue
                if rel_types and rel.relationship_type not in rel_types:
                    continue
                relationships.append(rel)
                if rel.target_id not in visited:
                    queue.append((rel.target_id, current_depth + 1))

            # Traverse incoming edges
            for rel_id in self._incoming.get(current_id, []):
                rel = self._relationships.get(rel_id)
                if not rel:
                    continue
                if rel_types and rel.relationship_type not in rel_types:
                    continue
                relationships.append(rel)
                if rel.source_id not in visited:
                    queue.append((rel.source_id, current_depth + 1))

        return GraphQueryResult(
            entities=entities,
            relationships=relationships,
            query_depth=depth,
            total_nodes_visited=len(visited),
        )

    def shortest_path(
        self,
        source_id: str,
        target_id: str,
        max_depth: int = 10,
    ) -> list[str] | None:
        """BFS shortest path between two entities. Returns entity ID list or None."""
        if source_id not in self._entities or target_id not in self._entities:
            return None
        if source_id == target_id:
            return [source_id]

        visited: set[str] = {source_id}
        queue: deque[list[str]] = deque([[source_id]])

        while queue:
            path = queue.popleft()
            if len(path) > max_depth + 1:
                return None

            current = path[-1]
            # Check all neighbors
            neighbor_ids: set[str] = set()
            for rel_id in self._outgoing.get(current, []):
                rel = self._relationships.get(rel_id)
                if rel:
                    neighbor_ids.add(rel.target_id)
            for rel_id in self._incoming.get(current, []):
                rel = self._relationships.get(rel_id)
                if rel:
                    neighbor_ids.add(rel.source_id)

            for neighbor in neighbor_ids:
                if neighbor == target_id:
                    return path + [neighbor]
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(path + [neighbor])

        return None

    def get_subgraph(
        self,
        center_id: str,
        radius: int = 2,
    ) -> GraphQueryResult:
        """Extract a subgraph centered on an entity within a radius."""
        return self.get_neighbors(center_id, depth=radius)

    # ── Entity Extraction ─────────────────────────────────────────────

    def extract_entities(
        self,
        text: str,
        source_doc_id: str = "",
    ) -> list[Entity]:
        """
        Rule-based entity extraction from text.

        Identifies:
        - PascalCase class/service names
        - UPPER_CASE constants
        - URL-like API references
        - Known technology terms
        """
        entities: list[Entity] = []
        seen_names: set[str] = set()

        # PascalCase identifiers (e.g., PromptEngine, AIGateway)
        for match in re.finditer(r'\b([A-Z][a-z]+(?:[A-Z][a-z]+)+)\b', text):
            name = match.group(1)
            if name not in seen_names:
                seen_names.add(name)
                entities.append(Entity(
                    name=name,
                    entity_type=EntityType.SERVICE,
                    description=f"Extracted from text: {name}",
                    source_doc_id=source_doc_id,
                ))

        # Technology/tool terms
        tech_patterns = {
            EntityType.DATABASE: r'\b(PostgreSQL|Redis|MongoDB|SQLite|Elasticsearch)\b',
            EntityType.MODEL: r'\b(Claude|Gemini|GPT-4|CodeLlama|Mistral)\b',
            EntityType.TOOL: r'\b(Docker|Kubernetes|Terraform|Helm|ArgoCD)\b',
            EntityType.PIPELINE: r'\b(CI/CD|GitHub Actions|Jenkins|GitOps)\b',
        }

        for etype, pattern in tech_patterns.items():
            for match in re.finditer(pattern, text, re.IGNORECASE):
                name = match.group(1)
                if name not in seen_names:
                    seen_names.add(name)
                    entities.append(Entity(
                        name=name,
                        entity_type=etype,
                        description=f"Technology reference: {name}",
                        source_doc_id=source_doc_id,
                    ))

        # API endpoints
        for match in re.finditer(r'(?:GET|POST|PUT|DELETE|PATCH)\s+(/[\w/{}.-]+)', text):
            path = match.group(1)
            name = f"API:{path}"
            if name not in seen_names:
                seen_names.add(name)
                entities.append(Entity(
                    name=name,
                    entity_type=EntityType.API,
                    description=f"API endpoint: {path}",
                    source_doc_id=source_doc_id,
                ))

        return entities

    # ── Stats ─────────────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        type_counts = defaultdict(int)
        for entity in self._entities.values():
            type_counts[entity.entity_type.value] += 1
        rel_type_counts = defaultdict(int)
        for rel in self._relationships.values():
            rel_type_counts[rel.relationship_type.value] += 1

        return {
            "total_entities": len(self._entities),
            "total_relationships": len(self._relationships),
            "entity_types": dict(type_counts),
            "relationship_types": dict(rel_type_counts),
        }

    def reset(self) -> None:
        """Clear the entire graph."""
        self._entities.clear()
        self._relationships.clear()
        self._outgoing.clear()
        self._incoming.clear()
        self._name_index.clear()
        self._alias_index.clear()
