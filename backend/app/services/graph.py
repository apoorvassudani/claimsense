"""Relationship graph stored in PostgreSQL (graph_nodes / graph_edges).
Every edge starts at a CLAIM node, so 'claims sharing an identifier' is a two-hop query."""
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Claim, Extraction, GraphEdge, GraphNode

SHARED_TYPES = ("PHONE", "ADDRESS", "PROVIDER", "VEHICLE")


def norm(node_type: str, value: str) -> str:
    v = value.strip().lower()
    if node_type == "PHONE":
        return re.sub(r"\D", "", v)[-10:]
    if node_type == "VEHICLE":
        return re.sub(r"[^a-z0-9]", "", v)
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", "", v))


def _node(db: Session, node_type: str, raw: str, label: str | None = None) -> GraphNode:
    key = norm(node_type, raw) if node_type in SHARED_TYPES else raw
    node = db.scalar(select(GraphNode).where(GraphNode.node_type == node_type, GraphNode.node_key == key))
    if not node:
        node = GraphNode(node_type=node_type, node_key=key, label=label or raw)
        db.add(node)
        db.flush()
    return node


def _edge(db: Session, src: GraphNode, dst: GraphNode, relation: str) -> None:
    exists = db.scalar(select(GraphEdge).where(GraphEdge.src_node_id == src.node_id,
                                               GraphEdge.dst_node_id == dst.node_id,
                                               GraphEdge.relation == relation))
    if not exists:
        db.add(GraphEdge(src_node_id=src.node_id, dst_node_id=dst.node_id, relation=relation))
        db.flush()


def build_claim_graph(db: Session, claim: Claim, extractions: list[Extraction]) -> None:
    c = _node(db, "CLAIM", claim.claim_number)
    _edge(db, c, _node(db, "CLAIMANT", claim.claimant.claimant_code, claim.claimant.full_name), "FILED_BY")
    _edge(db, c, _node(db, "POLICY", claim.policy.policy_number), "UNDER_POLICY")
    # Phone/address shown as masked labels in the graph UI
    _edge(db, c, _node(db, "PHONE", claim.claimant.phone, "phone ••" + claim.claimant.phone[-4:]), "CONTACT_PHONE")
    _edge(db, c, _node(db, "ADDRESS", claim.claimant.address, "address (masked)"), "CONTACT_ADDRESS")
    for ex in extractions:
        f = ex.fields
        if f.get("provider_name"):
            _edge(db, c, _node(db, "PROVIDER", f["provider_name"]), "SERVICED_BY")
        if f.get("vehicle_registration"):
            _edge(db, c, _node(db, "VEHICLE", f["vehicle_registration"]), "INVOLVES_VEHICLE")
    db.flush()


def shared_identifiers(db: Session, claim: Claim) -> dict[str, list[str]]:
    """identifier label -> other claim numbers linked to the same identifier."""
    c = db.scalar(select(GraphNode).where(GraphNode.node_type == "CLAIM", GraphNode.node_key == claim.claim_number))
    if not c:
        return {}
    out: dict[str, list[str]] = {}
    ids = db.execute(select(GraphNode).join(GraphEdge, GraphEdge.dst_node_id == GraphNode.node_id)
                     .where(GraphEdge.src_node_id == c.node_id, GraphNode.node_type.in_(SHARED_TYPES))).scalars()
    for ident in ids:
        others = db.execute(select(GraphNode.node_key).join(GraphEdge, GraphEdge.src_node_id == GraphNode.node_id)
                            .where(GraphEdge.dst_node_id == ident.node_id, GraphNode.node_id != c.node_id)).scalars().all()
        if others:
            out[f"{ident.node_type}:{ident.label}"] = sorted(others)
    return out


def neighborhood(db: Session, claim_number: str) -> dict:
    """Claim -> identifiers -> other claims (2 hops) for the graph explorer."""
    c = db.scalar(select(GraphNode).where(GraphNode.node_type == "CLAIM", GraphNode.node_key == claim_number))
    if not c:
        return {"nodes": [], "edges": []}
    nodes = {c.node_id: c}
    edges = list(db.scalars(select(GraphEdge).where(GraphEdge.src_node_id == c.node_id)))
    for e in list(edges):
        dst = db.get(GraphNode, e.dst_node_id)
        nodes[dst.node_id] = dst
        if dst.node_type in SHARED_TYPES:
            for e2 in db.scalars(select(GraphEdge).where(GraphEdge.dst_node_id == dst.node_id,
                                                         GraphEdge.src_node_id != c.node_id)):
                edges.append(e2)
                nodes.setdefault(e2.src_node_id, db.get(GraphNode, e2.src_node_id))
    return {
        "nodes": [{"id": n.node_id, "type": n.node_type, "label": n.label if n.node_type in SHARED_TYPES else n.node_key}
                  for n in nodes.values()],
        "edges": [{"source": e.src_node_id, "target": e.dst_node_id, "relation": e.relation} for e in edges],
    }
