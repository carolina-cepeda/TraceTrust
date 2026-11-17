# TraceTrust: guion de demo

## Preparación

Desde la raíz del proyecto:

```powershell
python -m tracetrust.generator data/demo --lots 10 --seed 42
python -m tracetrust.demo data/demo
python -m unittest discover -s tests -v
uvicorn tracetrust.api:app --reload
```

Abrir `http://127.0.0.1:8000/`. La aplicación usa `data/demo` por defecto.

## Narrativa sugerida

1. **Problema:** TRACOP produce exportaciones heterogéneas; TraceTrust no modifica
   el sistema fuente, las normaliza y conserva evidencia auditable.
2. **Flujo:** manifiesto validado → eventos canónicos → reconciliación explicable
   → reglas deterministas + Isolation Forest → Trust Score → grafo consultable.
3. **Caso visual:** seleccionar un lote y mostrar su línea temporal, los eventos
   relacionados, factores de confianza y hallazgos.
4. **Explicabilidad:** abrir un hallazgo y señalar regla, severidad, eventos y
   evidencia; después consultar una relación reconciliada y sus componentes.
5. **Arquitectura:** el dashboard consume `/api/v1`; SQLite es el read model local,
   mientras PostgreSQL y Neo4j tienen adaptadores de proyección preparados.

## Evidencia técnica

- 20 eventos gold y 20 observados en el dataset reproducible.
- Reconciliación: precision, recall y F1 de 1.0 en el ground truth de demo.
- 6 hallazgos combinando reglas y anomalías; los factores del Trust Score son
  visibles y trazables.
- Proyección de grafo con nodos de eventos, lotes, evidencias y hallazgos.
- 15 pruebas automatizadas pasando; `pipeline_summary.json`, `evaluation.json`,
  `benchmarks.json` y `calibration.json` respaldan la explicación.

## Límites honestos del MVP

La demo trabaja offline sobre snapshots y usa datos sintéticos controlados. El
adaptador Neo4j exporta Cypher y el adaptador PostgreSQL implementa el esquema y
la escritura, pero no se presentan como infraestructura desplegada en vivo.
GraphSAGE/RAG queda como línea experimental posterior; la demo implementa la
Arquitectura A del paper con componentes reproducibles y auditables.
