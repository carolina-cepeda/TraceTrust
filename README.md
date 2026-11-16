# TraceTrust

TraceTrust es un repositorio independiente para análisis offline/batch de datos
operacionales exportados. No se conecta en vivo a TRACOP y no escribe en su base
de datos.

## Primer prototipo

El núcleo inicial define el evento canónico auditable y genera datasets
reproducibles `gold`/`observed` con ground truth:

```powershell
python -m tracetrust.generator data/demo --lots 10 --seed 42
python -m tracetrust.reconciliation data/demo/gold/events.jsonl data/demo/observed/events.jsonl data/demo/reconciliation.jsonl
python -m tracetrust.rules data/demo/gold/events.jsonl data/demo/observed/events.jsonl data/demo/reconciliation.jsonl data/demo/findings.jsonl
python -m tracetrust.trust_score data/demo/observed/events.jsonl data/demo/reconciliation.jsonl data/demo/findings.jsonl data/demo/trust_scores.jsonl
python -m tracetrust.anomaly data/demo/observed/events.jsonl data/demo/reconciliation.jsonl data/demo/anomalies.jsonl
python -m tracetrust.evaluation data/demo/ground_truth.json data/demo/reconciliation.jsonl data/demo/findings.jsonl data/demo/evaluation.json
python -m tracetrust.graph project data/demo/observed/events.jsonl data/demo/reconciliation.jsonl data/demo/findings.jsonl data/demo/trust_scores.jsonl data/demo/trace_graph.json
python -m tracetrust.graph query data/demo/trace_graph.json lot:observed-42:lot-00001 --direction ancestors
uvicorn tracetrust.api:app --reload
python -m unittest discover -s tests -v
```

La salida contiene `gold/`, `observed/` y `ground_truth.json`. Las perturbaciones
del dataset observado se registran explícitamente para evaluar reconciliación,
reglas y anomalías.
