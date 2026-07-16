# Raíz de pruebas ECG

`testing/` es un entorno aislado para descargar, revisar y clasificar candidatos antes de incorporarlos al banco publicado.

## Regla principal

Nada dentro de `testing/` puede modificar, borrar o sobrescribir `output/ECG_BANCO_INICIAL_REAL`.

## Estructura

```text
testing/
├── candidates/                    # Señales descargadas localmente para revisión
│   └── atrial_fibrillation/
├── catalog/
│   └── afib_candidates.json       # Manifiesto versionado de candidatos
├── review/
│   └── review_state.json          # Decisiones humanas
├── reports/                       # Informes de validación generados
└── viewer/                        # Futuro visor de revisión
```

## Flujo

1. Leer `catalog/afib_candidates.json`.
2. Descargar únicamente la señal original PTB-XL de 500 Hz de cada candidato.
3. Guardar los archivos generados bajo `testing/candidates/atrial_fibrillation/<candidateId>/`.
4. Revisar visualmente las 12 derivaciones y DII largo.
5. Registrar la decisión en `review/review_state.json`.
6. Promover a producción únicamente mediante una acción explícita posterior.

## Estados permitidos

- `pending`: pendiente de revisión.
- `approved`: aprobado clínicamente para el banco.
- `rejected`: descartado.
- `reserved`: válido, pero reservado para otra categoría educativa.

## Reglas de integridad

- Usar la señal original a 500 Hz como referencia.
- No dibujar, suavizar, normalizar, corregir ni mezclar ondas.
- Mantener el `ecgId` original de PTB-XL.
- Documentar hallazgos concomitantes.
- No aprobar automáticamente ningún registro.
- El ECG 8215 permanece en producción y está excluido de esta lista de 20 candidatos.

Los archivos binarios y señales generadas en `testing/candidates/` no se versionan en Git; pueden regenerarse desde PhysioNet usando el manifiesto.
