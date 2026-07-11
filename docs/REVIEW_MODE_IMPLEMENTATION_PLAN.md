# Plan de implementación: modo Revisión de candidatos ECG

## Estado actual auditado

El constructor del banco es `tools/build_ecg_bank.py`. Descarga metadatos de PTB-XL, selecciona un único registro por cada uno de los ocho ritmos y escribe el resultado en `output/ECG_BANCO_INICIAL_REAL`.

- La selección automática está en `score_row()` y `choose_records()`. `score_row()` suma validación humana, segunda opinión y calidad técnica, y resta hallazgos adicionales. Actualmente los hallazgos incompatibles no se excluyen de forma estricta para ritmo sinusal normal.
- `TARGETS` define los ocho ritmos, su código SCP objetivo y los códigos permitidos.
- `choose_records()` ordena los candidatos por puntuación y elige solo el primero que no esté ya usado. No hay lista de candidatos, revisión humana ni IDs congelados.
- El constructor usa `filename_lr` para descargar la fuente de 100 Hz y `filename_hr` para la fuente de 500 Hz mediante `prepare_wfdb_record()`. Cada registro se lee con WFDB, sin transformar sus ondas, y se guarda en JSON.
- Cada carpeta de `rhythms/<ritmo>/` contiene fuentes `.hea/.dat`, `signal_100hz.json`, `signal_500hz.json`, `signal.json`, `metadata.json`, `educational.json` y comparación 100/500 Hz. `signal.json` es hoy una copia de 100 Hz.
- `metadata.json` contiene: identificador, título, código objetivo, puntuación, `ecgId`, paciente, adquisición, informe y códigos SCP traducidos, validación, calidad, validación de muestreo, todos los campos originales y hashes de señal.
- Cada JSON de señal contiene: versión de esquema, identificador, título, procedencia PTB-XL y `ecgId`, frecuencia, duración, muestras por derivación, unidades mV, orden de derivaciones y las 12 señales numéricas.
- El catálogo actual es `catalog/rhythms_catalog.json`: una lista de ocho elementos con `id`, título, código objetivo, `ecgId`, frecuencia, duración y ruta. Apunta a `signal.json`, por lo que describe 100 Hz aunque el visor permite seleccionar 500 Hz.
- El visor carga el catálogo en `init()` y, al elegir un ritmo, `loadRhythm()` carga señal, metadatos y contenido educativo. El visor autónomo actual puede usar `viewer/data.js` en lugar de solicitudes de red, pero conserva el mismo flujo lógico.
- El constructor borra por completo `output/ECG_BANCO_INICIAL_REAL` antes de construir. Por tanto, todavía no puede conservar decisiones humanas ni congelar un banco final.

La animación usa una FC original estimada desde DII de la señal oficial de 500 Hz y una FC de reproducción elegida por el usuario. No existen multiplicadores 0,5×, 1× ni 2×. El reloj visible, cursor y papel avanzan siempre en tiempo real; la escala `FC de reproducción / FC original` se usa solo para seleccionar con interpolación las muestras de la señal.

## Archivos previstos para la siguiente fase

- `tools/build_ecg_bank.py`: selección de 3–5 candidatos, filtros estrictos, generación de candidatos, validaciones y congelación final.
- `tools/review_server.py` (nuevo): servidor local mínimo para leer y guardar `review_state.json`, sin Internet ni base de datos.
- `template/viewer/index.html`, `template/viewer/app.js` y `template/viewer/styles.css`: interfaz separada en modos Banco y Revisión.
- `template/ABRIR_VISOR.bat` y/o un nuevo iniciador de revisión: arranque del servidor local solo al revisar o guardar decisiones.
- `output/ECG_BANCO_INICIAL_REAL/review/` y `output/ECG_BANCO_INICIAL_REAL/reports/`: datos generados, no fuentes clínicas modificadas.

## Estructura propuesta

```text
output/ECG_BANCO_INICIAL_REAL/
├── catalog/
│   ├── rhythms_catalog.json
│   └── catalog_final.json
├── rhythms/                         # solo los registros aprobados, sin alterar señales
├── review/
│   ├── candidates/
│   │   └── <ritmo>/candidate_01/    # señal original 500 Hz, metadatos y fuentes WFDB
│   ├── review_catalog.json
│   └── review_state.json
└── reports/
    ├── review_validation_report.json
    └── review_validation_report.md
```

`review_catalog.json` listará entre tres y cinco candidatos por ritmo, con su puntuación, todos los códigos SCP y descripciones, informe, datos de adquisición, validación y calidad técnica. Cada candidato usará `signal_500hz.json` como señal principal; el 100 Hz podrá existir solo como referencia técnica y no será usado en la revisión.

`review_state.json` guardará, por candidato, el estado `pending`, `approved` o `rejected`, notas, fecha de revisión y marca de revisión humana. Por ritmo guardará el candidato y `ecgId` aprobado. Solo una aprobación podrá estar activa por ritmo.

## Selección y revisión propuestas

1. Sustituir la selección única por una clasificación que devuelva hasta cinco `ecgId` únicos por ritmo.
2. Para ritmo sinusal normal, exigir simultáneamente `NORM` y `SR`, y excluir con filtro estricto (puntuación no elegible) infarto, hipertrofia, ST-T, bloqueos, preexcitación, ectopias, fibrilación/flutter, marcapasos, problemas de electrodos y ruido relevante. No se aceptará una simple penalización para estas incompatibilidades.
3. Para los demás ritmos, permitir solo hallazgos adicionales no contradictorios, aplicar penalización fuerte y conservarlos visibles en metadatos.
4. Generar las carpetas de candidatos sin copiar ni alterar ondas: señal WFDB oficial a 500 Hz, cabeceras `.hea/.dat` y metadatos completos.
5. Añadir modo Revisión con selector de ritmo y candidato, anterior/siguiente, ECG de 12 derivaciones, DII largo, diagnóstico y metadatos visibles. La revisión tendrá fija la señal original a 500 Hz, ganancia 10 mm/mV y velocidad 25 mm/s.
6. Guardar aprobar, rechazar y notas a través de un servidor Python local. Un HTML abierto directamente no puede escribir `review_state.json` de forma segura; por ello la persistencia requerirá abrir el modo Revisión con el iniciador local. El modo Banco podrá seguir siendo HTML autónomo y de solo lectura.
7. Cuando haya ocho aprobaciones, crear `catalog/catalog_final.json`, copiar o referenciar únicamente esos registros en `rhythms/` y evitar que una ejecución normal los sustituya. La regeneración de candidatos requerirá el parámetro explícito `--regenerate-candidates`.
8. Generar los dos informes de validación y fallar si falta cualquier requisito técnico o si el catálogo final no contiene exactamente ocho ritmos aprobados.

## Riesgos y controles

- **Riesgo clínico:** un candidato bien codificado puede no ser pedagógicamente adecuado. El sistema solo ordena y expone datos; la aprobación sigue siendo humana.
- **Persistencia:** el visor HTML autónomo no puede guardar archivos. El servidor local deberá limitarse a `127.0.0.1`, validar el contenido recibido y escribir únicamente dentro de `review/`.
- **Regeneración destructiva:** el constructor actual borra `output`. Se cambiará para preservar aprobaciones y exigir una orden explícita al regenerar candidatos.
- **Datos grandes:** cinco candidatos por ocho ritmos a 500 Hz ocuparán más espacio. Se mantendrá una sola copia de cada fuente y no se duplicarán señales innecesariamente.
- **Integridad:** se verificarán 12 derivaciones, 500 Hz, 10 segundos, mV, ausencia de NaN, longitud uniforme, correspondencia de DII y `ecgId` único.

## Criterios de aceptación

- Hay de tres a cinco candidatos accesibles por cada ritmo, cuando PTB-XL los provea.
- Todos los candidatos de revisión se muestran desde la señal original de 500 Hz.
- La interfaz permite aprobar, rechazar, escribir notas y volver a abrir conservando las decisiones.
- El usuario ve códigos SCP, informe original, metadatos, calidad y problemas técnicos de cada candidato.
- No se modifica, sintetiza, corrige, suaviza ni normaliza ninguna señal ECG.
- Al aprobar los ocho ritmos se crea `catalog_final.json` con exactamente ocho `ecgId` aprobados y estos no cambian salvo regeneración solicitada explícitamente.
- Los informes de validación se generan y señalan cualquier candidato o catálogo final inválido.
