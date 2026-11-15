# TraceTrust: arquitectura inicial

## Decisión de producto

TraceTrust será una capa analítica desacoplada de TRACOP. Su responsabilidad es
recibir snapshots offline, normalizar registros, reconciliar entidades y eventos,
construir una representación de trazabilidad auditable y devolver consultas,
alertas, anomalías y explicaciones.

TraceTrust no modifica la fuente operacional y no convierte una inferencia en un
hecho. Cada afirmación debe conservar su origen, tipo de relación y nivel de
confianza.

## Principios derivados del paper 2

1. **El grafo es una proyección analítica, no la fuente original.** PostgreSQL
   conserva el snapshot, los eventos canónicos, las relaciones y los resultados
   auditables. El grafo se puede reconstruir.
2. **La procedencia es un dato de primera clase.** Nodos, relaciones, reglas,
   anomalías y respuestas de IA apuntan a `source_system`, `source_record_id`,
   `snapshot_id` y evidencia.
3. **Tres tipos de relación.** `RECORDED` representa lo declarado por una fuente;
   `DERIVED` representa una regla determinística; `INFERRED` representa una
   correspondencia o señal probabilística.
4. **La interfaz debe explicar antes de resumir.** La vista principal muestra la
   genealogía y sus conflictos; el Trust Score es un resumen desglosable, no una
   etiqueta de verdad.
5. **La IA consulta, no decide.** RAG/LLM recupera subgrafos, alertas y evidencia
   antes de responder. No crea relaciones, no recalcula el Trust Score y no
   escribe en el grafo.

## Modelo de información mínimo

```text
Snapshot
  -> SourceRecord
  -> CanonicalTraceabilityEvent
       -> Lot / Actor / Organization / Location
       -> Evidence
       -> input_lot / output_lot
  -> Relation
       -> recorded | derived | inferred
       -> provenance + confidence
  -> Finding
       -> deterministic_rule | tabular_anomaly | relational_anomaly
       -> severity + explanation + evidence
  -> TrustAssessment
       -> six factors + weights + critical penalties
```

El `CanonicalTraceabilityEvent` debe conservar tanto el valor normalizado como
el valor original. Para el MVP sus campos son: `event_id`, `source_system`,
`source_record_id`, `event_type`, `timestamp`, `actor`, `organization`,
`input_lots`, `output_lots`, `quantity`, `unit`, `location`, `evidence_refs` y
`raw_payload`.

## Capas del sistema

### 1. Ingesta y contratos

- Leer CSV/JSONL acompañado por `snapshot-manifest.schema.json`.
- Validar hash, conteo de filas, versión de esquema y política de anonimización.
- Rechazar o aislar archivos que no cumplan el contrato; nunca corregirlos en
  silencio.

### 2. Núcleo canónico

- Normalizar fechas, unidades, tipos de evento y referencias a lotes.
- Mantener `raw_payload` y la identidad del registro de origen.
- Registrar errores de calidad como findings, no como pérdida de datos.

### 3. Reconciliación

- Seleccionar candidatos por identificador, ventana temporal, producto,
  organización, ubicación y cantidad.
- Calcular `match_score` explicable por componentes.
- Clasificar cada par como `match`, `non_match` o `review`.
- Guardar los valores comparados y la versión del algoritmo.

### 4. Grafo consultable

- Proyectar lotes, eventos, actores, evidencias y relaciones en Neo4j.
- Incluir propiedades de procedencia directamente en las relaciones.
- Mantener índices para `snapshot_id`, `source_record_id`, `lot_id`, tiempo y
  tipo de evento.
- Exponer subgrafos acotados para que la visualización no intente dibujar todo
  el corpus a la vez.

### 5. Analítica

- Reglas determinísticas primero: secuencia temporal, transferencia/recepción,
  conservación de masa, evidencia obligatoria, custodia y referencias huérfanas.
- Features tabulares reproducibles para Isolation Forest; LOF y One-Class SVM
  quedan como benchmarks.
- Trust Score con seis factores: procedencia/evidencia, continuidad,
  consistencia de cantidades, coherencia temporal, validación cruzada y
  completitud.

### 6. Consulta visual e IA

- Vista de lote: línea de tiempo + genealogía + fuentes + evidencias.
- Vista de conflicto: comparación lado a lado de registros, diferencia y regla.
- Vista de impacto: descendientes que dependen de un evento o relación.
- Vista de confianza: factores, pesos, penalizaciones y trazas de cálculo.
- Asistente RAG: responde solo con evidencia recuperada y devuelve referencias
  a nodos, relaciones, findings y snapshot.

## API inicial orientada a tareas

```text
GET  /snapshots/{snapshot_id}
GET  /lots/{lot_id}/lineage?direction=both&depth=20
GET  /lots/{lot_id}/impact
GET  /findings?severity=critical&snapshot_id=...
GET  /relations/{relation_id}/evidence
GET  /trust/{entity_type}/{entity_id}
POST /reconciliation/runs
POST /analysis/runs
POST /assistant/query
```

Cada endpoint analítico debe devolver `snapshot_id`, `generated_at`,
`algorithm_version` y una colección de referencias de procedencia.

## Orden de implementación

1. Contratos de snapshot y modelos Pydantic del CTE.
2. Generador controlado con `gold` y `observed` datasets.
3. Normalización + reconciliación con métricas contra ground truth.
4. Persistencia PostgreSQL y proyección reconstruible a Neo4j.
5. Consultas de genealogía, discrepancias e impacto.
6. Reglas determinísticas y esquema uniforme de findings.
7. Trust Score con sensibilidad de pesos.
8. Isolation Forest y benchmarks.
9. API de subgrafos y primera interfaz visual.
10. RAG/LLM; GraphSAGE solo como experimento posterior al MVP.

## Riesgos que debemos controlar desde el inicio

- **Coherencia no equivale a verdad:** el sistema debe decir “respaldo de la
  trazabilidad disponible”, no “producto verdadero”.
- **Explosión visual:** la UI necesita profundidad, filtros y agregación por
  comunidad/evento; no un lienzo con todos los nodos.
- **Alucinaciones de IA:** la respuesta debe fallar de forma explícita cuando no
  encuentre evidencia suficiente.
- **Reconciliación opaca:** ningún match inferido debe aparecer como registrado.
- **Evaluación sesgada:** separar desarrollo, calibración y prueba, manteniendo
  las semillas del conjunto final fuera del ajuste.

