# TraceTrust

TraceTrust es un MVP académico para analizar snapshots operacionales sin
modificar el sistema fuente. Normaliza eventos, reconcilia exportaciones,
detecta anomalías, calcula confianza explicable y proyecta la trazabilidad en
un grafo consultable.

## Demo rápida

```powershell
python -m tracetrust.generator data/demo --lots 10 --seed 42
python -m tracetrust.demo data/demo
python -m unittest discover -s tests -v
uvicorn tracetrust.api:app --reload
```

Abrir `http://127.0.0.1:8000/` para el dashboard. El guion completo está en
[`docs/demo-runbook.md`](docs/demo-runbook.md).

## Flujo técnico

`manifiesto validado → eventos canónicos → reconciliación explicable → reglas +
Isolation Forest → Trust Score → grafo → API v1/dashboard`

El pipeline deja artefactos reproducibles en `data/demo/`: reconciliación,
hallazgos, anomalías, evaluaciones, benchmarks, calibración, Trust Scores y
export Cypher. La persistencia local usa SQLite como read model; PostgreSQL y
Neo4j cuentan con adaptadores opcionales para despliegue.

## Comandos individuales

```powershell
python -m tracetrust.pipeline data/demo
python -m tracetrust.graph query data/demo/trace_graph.json lot:observed-42:lot-00001 --direction ancestors
python -m tracetrust.neo4j data/demo/trace_graph.json data/demo/trace_graph.cypher
python -m tracetrust.benchmarks data/demo/observed/events.jsonl data/demo/reconciliation.jsonl data/demo/ground_truth.json data/demo/benchmarks.json
```

Para el adaptador PostgreSQL: `pip install -e ".[postgres]"`. Para Neo4j:
`pip install -e ".[neo4j]"`.

## Alcance y límites

La demo implementa la Arquitectura A del paper: procesamiento offline/batch,
reglas deterministas, Isolation Forest, Trust Score y almacenamiento orientado a
consultas. GraphSAGE/RAG queda como línea experimental posterior. Los datos de
`data/demo` son sintéticos y los adaptadores externos no implican que exista una
infraestructura PostgreSQL/Neo4j desplegada en vivo.

En despliegues protegidos configurar `TRACETRUST_API_KEY` y enviar `X-API-Key`.
En desarrollo la autenticación está desactivada.
