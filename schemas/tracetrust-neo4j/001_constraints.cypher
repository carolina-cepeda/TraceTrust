// TraceTrust graph projection constraints.
CREATE CONSTRAINT tracetrust_node_id IF NOT EXISTS
FOR (node:TraceNode) REQUIRE node.id IS UNIQUE;

CREATE INDEX tracetrust_node_snapshot IF NOT EXISTS
FOR (node:TraceNode) ON (node.snapshot_id);

CREATE INDEX tracetrust_node_type IF NOT EXISTS
FOR (node:TraceNode) ON (node.node_type);
