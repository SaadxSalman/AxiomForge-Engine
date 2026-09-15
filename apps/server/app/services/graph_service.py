# -*- coding: utf-8 -*-
from __future__ import annotations
import json
import logging
from typing import Any
from app.config import settings
from app.database import get_neo4j_driver

logger = logging.getLogger(__name__)


class GraphService:
    def __init__(self) -> None:
        self.driver = get_neo4j_driver()

    def ensure_faction(self, faction_id: str, name: str, metadata: dict[str, Any] | None = None) -> None:
        with self.driver.session(database=settings.neo4j_db) as session:
            session.run("MERGE (f:Faction {id: $faction_id}) SET f.name = $name, f.metadata = $metadata, f.updated_at = datetime()", faction_id=faction_id, name=name, metadata=json.dumps(metadata or {}))

    def relate_factions(self, source: str, target: str, relation: str, weight: float = 1.0, metadata: dict[str, Any] | None = None) -> None:
        with self.driver.session(database=settings.neo4j_db) as session:
            session.run(f"MATCH (a:Faction {{id: $source}}) MATCH (b:Faction {{id: $target}}) MERGE (a)-[r:{relation}]->(b) SET r.weight = $weight, r.metadata = $metadata, r.updated_at = datetime()", source=source, target=target, weight=weight, metadata=json.dumps(metadata or {}))

    def get_faction_context(self, faction_id: str) -> dict[str, Any]:
        with self.driver.session(database=settings.neo4j_db) as session:
            result = session.run("MATCH (f:Faction {id: $faction_id})-[rels]->(other) RETURN f, type(rels) as rel_type, other, rels.weight as weight, rels.metadata as metadata", faction_id=faction_id)
            rows = [record.data() for record in result]
            relations = []
            for r in rows:
                other_node = r["other"]
                relations.append({"target": other_node.get("id"), "type": r["rel_type"], "weight": r.get("weight"), "metadata": json.loads(r.get("metadata") or "{}")})
            return {"faction_id": faction_id, "relations": relations}

    def ensure_item(self, item_id: str, name: str, item_type: str = "resource", metadata: dict[str, Any] | None = None) -> None:
        with self.driver.session(database=settings.neo4j_db) as session:
            session.run("MERGE (i:Item {id: $item_id}) SET i.name = $name, i.item_type = $item_type, i.metadata = $metadata, i.updated_at = datetime()", item_id=item_id, name=name, item_type=item_type, metadata=json.dumps(metadata or {}))

    def depends_on(self, item_id: str, depends_on_id: str, quantity: float = 1.0) -> None:
        with self.driver.session(database=settings.neo4j_db) as session:
            session.run("MATCH (a:Item {id: $item_id}) MATCH (b:Item {id: $depends_on_id}) MERGE (a)-[r:DEPENDS_ON]->(b) SET r.quantity = $quantity, r.updated_at = datetime()", item_id=item_id, depends_on_id=depends_on_id, quantity=quantity)

    def get_item_dependency_tree(self, item_id: str, depth: int = 2) -> dict[str, Any]:
        with self.driver.session(database=settings.neo4j_db) as session:
            result = session.run("MATCH path = (root:Item {id: $item_id})-[:DEPENDS_ON*..$depth]->(leaf) RETURN nodes(path) as path", item_id=item_id, depth=depth)
            paths = [record.data()["path"] for record in result]
            def node_map(node):
                return {"id": node.get("id"), "name": node.get("name"), "item_type": node.get("item_type")}
            return {"item_id": item_id, "depth": depth, "paths": [[node_map(n) for n in p] for p in paths]}

    def teardown(self) -> None:
        self.driver.close()
