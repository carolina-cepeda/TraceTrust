# Visualización opcional con Neo4j

TraceTrust mantiene el dashboard local como interfaz principal. Neo4j se utiliza
como proyección opcional para explorar el grafo en Neo4j Browser, con etiquetas
visuales para lotes, eventos, evidencias y hallazgos.

## Preparar la proyección

Instalar el adaptador:

`powershell
pip install -e ".[neo4j]"
`

Iniciar una instancia local de Neo4j Desktop o Neo4j Docker y aplicar primero:

`text
schemas/tracetrust-neo4j/001_constraints.cypher
`

Después ejecutar:

`powershell
python -c "import json; from tracetrust.graph import TraceGraphArtifact; from tracetrust.neo4j import push_neo4j; a=TraceGraphArtifact.model_validate_json(open('data/demo-robust-126/trace_graph.json', encoding='utf-8').read()); push_neo4j(a, 'bolt://localhost:7687', 'neo4j', 'TU_PASSWORD')"
`

## Consultas para la demo

Vista general del snapshot:

`cypher
MATCH (n:TraceNode {snapshot_id: 'observed-126'})
OPTIONAL MATCH (n)-[r]-(m:TraceNode {snapshot_id: 'observed-126'})
RETURN n, r, m
LIMIT 300
`

Cadena de un lote:

`cypher
MATCH p=(l:Lot {id: 'lot:observed-126:lot-00004'})-[*1..4]-(n)
RETURN p
LIMIT 100
`

Hallazgos y eventos afectados:

`cypher
MATCH p=(f:Finding)-[*1..2]-(n:TraceNode)
WHERE f.snapshot_id = 'observed-126'
RETURN p
LIMIT 100
`

La aplicación local continúa consultando SQLite y su proyección JSON. Neo4j no
es obligatorio para ejecutar el MVP; funciona como proyección visual y motor de
recorridos relacionales cuando se necesita una exploración más rica.
