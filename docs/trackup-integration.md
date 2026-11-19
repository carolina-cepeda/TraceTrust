# Integración Trackup → TraceTrust

TraceTrust recibe lotes de eventos canónicos de Trackup mediante:

```text
POST /api/v1/ingest/trackup
```

El endpoint queda protegido por `X-API-Key` cuando `TRACETRUST_API_KEY` está
configurada. Cada lote tiene un `snapshot_id`; repetir el mismo evento con el
mismo contenido es seguro y devuelve `duplicates`. Reutilizar un `event_id` con
otro contenido se rechaza.

## Regla de mapeo

Los eventos del outbox de Trackup (`LotPublished`, `LotReserved`, eventos de
pedido, etc.) no siempre tienen actor, organización, cantidad, unidad,
ubicación y evidencia suficientes para TraceTrust. El bridge solo acepta un
outbox event cuando su payload contiene un `canonical_event` completo. Los
eventos incompletos se rechazan explícitamente; no se rellenan campos con
valores inventados.

Ejemplo mínimo:

```json
{
  "snapshot_id": "trackup-2026-11-19-001",
  "source_system": "trackup",
  "source_schema": {
    "database_engine": "postgresql",
    "migration_ids": ["0010_ordering_schema"]
  },
  "anonymization": {
    "profile": "strict",
    "names_removed": true,
    "phones_removed": true,
    "actor_ids_pseudonymized": true,
    "precise_locations_removed": true,
    "media_refs_removed": true
  },
  "outbox_events": [
    {
      "id": "outbox-event-id",
      "aggregate": "lot:lot-123",
      "type": "TraceabilityEventRecorded",
      "created_at": "2026-11-19T12:00:00Z",
      "payload": {
        "canonical_event": {
          "event_id": "trace-event-123",
          "event_type": "production",
          "timestamp": "2026-11-19T11:59:00Z",
          "actor": "actor-pseudonym",
          "organization": "org-pseudonym",
          "input_lots": [],
          "output_lots": ["lot-123"],
          "quantity": 100,
          "unit": "kg",
          "location": "municipality-pseudonym"
        }
      }
    }
  ]
}
```

El worker de Trackup debe publicar este contrato después de confirmar la
transacción de negocio, conservar el `id` del outbox para reintentos y enviar
lotes de tamaño moderado. El endpoint devuelve el número de eventos aceptados,
duplicados y los artefactos analíticos generados.
