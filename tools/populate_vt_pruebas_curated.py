from __future__ import annotations

import json

import populate_vt_pruebas_verified as vt

EXCLUDED_RECORDS = {
    "S0426": {
        "reason": "La ventana automática más activa tuvo una frecuencia estimada de 83.2 lpm; no se conserva como candidato de taquicardia sin revisión manual del registro completo.",
        "criterion": "estimatedRateBpm < 120",
    },
    "S0533": {
        "reason": "El encabezado incluye fibrilación ventricular (SNOMED CT 164896001) además de taquicardia ventricular; se excluye para evitar un candidato mixto de alto riesgo.",
        "criterion": "concomitant ventricular fibrillation",
    },
}


def main() -> int:
    vt.RECORDS = [item for item in vt.RECORDS if item[2] not in EXCLUDED_RECORDS]
    result = vt.main()

    manifest = json.loads(vt.MANIFEST.read_text(encoding="utf-8"))
    manifest["selection"]["excludedRecords"] = [
        {"recordId": record_id, **details}
        for record_id, details in EXCLUDED_RECORDS.items()
    ]
    vt.dump(vt.MANIFEST, manifest)
    print(
        "Curación aplicada: S0426 excluido por frecuencia insuficiente y "
        "S0533 por fibrilación ventricular concomitante."
    )
    return result


if __name__ == "__main__":
    raise SystemExit(main())
