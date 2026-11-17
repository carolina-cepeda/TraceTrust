# TraceTrust

TraceTrust es un MVP de producto para convertir datos operacionales dispersos
en trazabilidad consultable, explicable y auditable sin modificar el sistema
fuente. Normaliza eventos, reconcilia exportaciones, detecta anomalías, calcula
confianza explicable y proyecta la trazabilidad en un grafo consultable.

## Demo rápida

```powershell
python -m tracetrust.generator data/demo --lots 10 --seed 42
python -m tracetrust.demo data/demo
python -m unittest discover -s tests -v
uvicorn tracetrust.api:app --reload
```

Abrir `http://127.0.0.1:8000/` para el dashboard. El guion completo está en
[`docs/demo-runbook.md`](docs/demo-runbook.md).

Para ver una cadena operacional más rica:

```powershell
python -m tracetrust.complex_demo data/demo-complex-84 --lots 12 --seed 84
python -m tracetrust.demo data/demo-complex-84
$env:TRACETRUST_DATA_ROOT = "data/demo-complex-84"
uvicorn tracetrust.api:app --reload
```

Para una demo adversarial con inconsistencias intencionales:

```powershell
python -m tracetrust.robust_demo data/demo-robust-126 --lots 16 --seed 126
python -m tracetrust.demo data/demo-robust-126
$env:TRACETRUST_DATA_ROOT = "data/demo-robust-126"
uvicorn tracetrust.api:app --reload
```

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

La proyección opcional para explorar el grafo en Neo4j Browser está documentada
en docs/neo4j-browser.md.

## Alcance y límites

La versión actual implementa procesamiento offline/batch, reglas deterministas,
Isolation Forest, Trust Score y almacenamiento orientado a consultas. Los datos
de data/demo son sintéticos y los adaptadores externos no implican que exista
una infraestructura PostgreSQL/Neo4j desplegada en vivo. La evolución prevista
incluye conectores empresariales, operación continua, controles de acceso,
observabilidad y modelos relacionales.

En despliegues protegidos configurar `TRACETRUST_API_KEY` y enviar `X-API-Key`.
En desarrollo la autenticación está desactivada.
