"""Deterministic graph projection and genealogy/impact queries."""

from __future__ import annotations

import argparse
import json
from collections import deque
from pathlib import Path
from typing import Any

import networkx as nx

from .models import (
    CanonicalTraceabilityEvent,
    Finding,
    GraphEdge,
    GraphNode,
    ReconciliationMatch,
    TraceGraphArtifact,
    TrustAssessment,
)
from .reconciliation import load_events
from .rules import load_matches
from .trust_score import load_findings


GRAPH_VERSION = "trace-graph-v1"


def _node_id(kind: str, snapshot_id: str, entity_id: str) -> str:
    return f"{kind}:{snapshot_id}:{entity_id}"


def _event_id(event: CanonicalTraceabilityEvent) -> str:
    return _node_id("event", event.snapshot_id, event.event_id)


def project_graph(
    events: list[CanonicalTraceabilityEvent],
    matches: list[ReconciliationMatch] | None = None,
    findings: list[Finding] | None = None,
    assessments: list[TrustAssessment] | None = None,
) -> TraceGraphArtifact:
    """Build a graph where provenance and analytical results remain properties."""
    nodes: dict[str, GraphNode] = {}
    edges: dict[tuple[str, str, str], GraphEdge] = {}

    def add_node(node: GraphNode) -> None:
        nodes[node.id] = node

    def add_edge(source: str, target: str, relation: str, properties: dict[str, Any] | None = None) -> None:
        # Reconciliation may connect events from two snapshots while the caller
        # projects only one snapshot's event list. Keep the artifact structurally
        # valid by representing the missing side as an external reference.
        for endpoint in (source, target):
            if endpoint not in nodes:
                kind, snapshot_id, entity_id = endpoint.split(":", 2)
                add_node(GraphNode(
                    id=endpoint, node_type=f"{kind}_reference", label=entity_id,
                    properties={"snapshot_id": snapshot_id, "external": True},
                ))
        key = (source, target, relation)
        edges[key] = GraphEdge(source=source, target=target, relation=relation, properties=properties or {})

    for event in events:
        event_node = _event_id(event)
        add_node(GraphNode(
            id=event_node, node_type="event", label=event.event_id,
            properties={"event_type": event.event_type.value, "timestamp": event.timestamp.isoformat(),
                        "source_system": event.source_system, "source_record_id": event.source_record_id,
                        "snapshot_id": event.snapshot_id, "quantity": event.quantity, "unit": event.unit},
        ))
        actor_node = _node_id("actor", event.snapshot_id, event.actor)
        org_node = _node_id("organization", event.snapshot_id, event.organization)
        add_node(GraphNode(id=actor_node, node_type="actor", label=event.actor,
                           properties={"snapshot_id": event.snapshot_id}))
        add_node(GraphNode(id=org_node, node_type="organization", label=event.organization,
                           properties={"snapshot_id": event.snapshot_id}))
        add_edge(event_node, actor_node, "performed_by")
        add_edge(event_node, org_node, "recorded_by")
        for lot_id in event.input_lots:
            lot_node = _node_id("lot", event.snapshot_id, lot_id)
            add_node(GraphNode(id=lot_node, node_type="lot", label=lot_id,
                               properties={"snapshot_id": event.snapshot_id}))
            add_edge(lot_node, event_node, "input_to", {"source_event_id": event.event_id})
        for lot_id in event.output_lots:
            lot_node = _node_id("lot", event.snapshot_id, lot_id)
            add_node(GraphNode(id=lot_node, node_type="lot", label=lot_id,
                               properties={"snapshot_id": event.snapshot_id}))
            add_edge(event_node, lot_node, "produces", {"source_event_id": event.event_id})
        for evidence in event.evidence_refs:
            evidence_node = _node_id("evidence", evidence.snapshot_id, evidence.source_record_id)
            add_node(GraphNode(id=evidence_node, node_type="evidence", label=evidence.source_record_id,
                               properties={"evidence_type": evidence.evidence_type,
                                           "snapshot_id": evidence.snapshot_id,
                                           "source_system": evidence.source_system}))
            add_edge(event_node, evidence_node, "supported_by")

    for match in matches or []:
        left = _node_id("event", match.left_snapshot_id, match.left_event_id)
        right = _node_id("event", match.right_snapshot_id, match.right_event_id)
        add_edge(left, right, "reconciles_with", {
            "match_id": match.match_id, "status": match.status.value,
            "relation_kind": match.relation_kind.value, "score": match.score,
            "algorithm_version": match.algorithm_version,
        })

    for finding in findings or []:
        finding_node = _node_id("finding", finding.snapshot_id, finding.finding_id)
        add_node(GraphNode(id=finding_node, node_type="finding", label=finding.rule_id,
                           properties={"severity": finding.severity.value, "rule_id": finding.rule_id,
                                       "explanation": finding.explanation,
                                       "snapshot_id": finding.snapshot_id}))
        for event_id in finding.source_event_ids:
            event_node = _node_id("event", finding.snapshot_id, event_id)
            if event_node in nodes:
                add_edge(finding_node, event_node, "concerns")
        for entity_id in finding.entity_ids:
            lot_node = _node_id("lot", finding.snapshot_id, entity_id)
            if lot_node in nodes:
                add_edge(finding_node, lot_node, "concerns")

    for assessment in assessments or []:
        assessment_node = _node_id("trust", assessment.snapshot_id, assessment.entity_id)
        add_node(GraphNode(id=assessment_node, node_type="trust_assessment", label=assessment.entity_id,
                           properties={"score": assessment.score, "uncapped_score": assessment.uncapped_score,
                                       "algorithm_version": assessment.algorithm_version,
                                       "critical_penalties": assessment.critical_penalties}))
        lot_node = _node_id("lot", assessment.snapshot_id, assessment.entity_id)
        if lot_node in nodes:
            add_edge(assessment_node, lot_node, "assesses")

    return TraceGraphArtifact(graph_version=GRAPH_VERSION, nodes=list(nodes.values()), edges=list(edges.values()))


def _network(artifact: TraceGraphArtifact) -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()
    for node in artifact.nodes:
        graph.add_node(node.id, **node.model_dump())
    for edge in artifact.edges:
        graph.add_edge(edge.source, edge.target, key=edge.relation, **edge.model_dump())
    return graph


def _resolve(graph: nx.MultiDiGraph, query: str) -> str:
    if query in graph:
        return query
    candidates = [node for node, data in graph.nodes(data=True) if data.get("label") == query]
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise ValueError(f"No graph node matched: {query}")
    raise ValueError(f"Ambiguous graph node {query}; use a fully qualified node id: {candidates}")


def traverse(artifact: TraceGraphArtifact, query: str, *, direction: str = "ancestors", depth: int = 20) -> dict[str, Any]:
    graph = _network(artifact)
    node = _resolve(graph, query)
    visited = {node: 0}
    queue = deque([node])
    while queue:
        current = queue.popleft()
        if visited[current] >= depth:
            continue
        neighbors = graph.predecessors(current) if direction == "ancestors" else graph.successors(current)
        for neighbor in neighbors:
            if neighbor not in visited:
                visited[neighbor] = visited[current] + 1
                queue.append(neighbor)
    return {"query": node, "direction": direction,
            "nodes": [graph.nodes[item] for item in visited],
            "distances": {item: distance for item, distance in visited.items()}}


def impact(artifact: TraceGraphArtifact, query: str, *, depth: int = 20) -> dict[str, Any]:
    """Return downstream nodes affected by a lot, event or finding."""
    return traverse(artifact, query, direction="descendants", depth=depth)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    project = subparsers.add_parser("project")
    project.add_argument("events", type=Path)
    project.add_argument("matches", type=Path)
    project.add_argument("findings", type=Path)
    project.add_argument("assessments", type=Path)
    project.add_argument("output", type=Path)
    query = subparsers.add_parser("query")
    query.add_argument("graph", type=Path)
    query.add_argument("entity")
    query.add_argument("--direction", choices=["ancestors", "descendants"], default="ancestors")
    query.add_argument("--depth", type=int, default=20)
    args = parser.parse_args()
    if args.command == "project":
        artifact = project_graph(
            load_events(args.events), load_matches(args.matches), load_findings(args.findings),
            [TrustAssessment.model_validate_json(line) for line in args.assessments.read_text(encoding="utf-8").splitlines() if line.strip()],
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(artifact.model_dump_json(indent=2), encoding="utf-8")
        print(json.dumps({"nodes": len(artifact.nodes), "edges": len(artifact.edges)}, indent=2))
    else:
        artifact = TraceGraphArtifact.model_validate_json(args.graph.read_text(encoding="utf-8"))
        print(json.dumps(traverse(artifact, args.entity, direction=args.direction, depth=args.depth), indent=2))


if __name__ == "__main__":
    main()
