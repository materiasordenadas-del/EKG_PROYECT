# Raíz de pruebas ECG

`testing/` es un entorno aislado para descargar, revisar y clasificar candidatos antes de incorporarlos al banco publicado.

## Regla principal

Nada dentro de `testing/` puede modificar, borrar o sobrescribir `output/ECG_BANCO_INICIAL_REAL`.

## Probar los 20 ECG de fibrilación auricular

En Windows, desde la raíz del repositorio:

1. Haga doble clic en `GENERAR_PRUEBAS_AFIB.bat`.
2. El archivo instalará o comprobará `wfdb` y `numpy`.
3. Descargará únicamente los 20 registros PTB-XL definidos en `testing/catalog/afib_candidates.json`.
4. Validará que cada señal tenga 12 derivaciones, 500 Hz y aproximadamente 10 segundos.
5. Creará `testing/ABRIR_REVISION.html` con todas las señales incrustadas.
6. Abrirá el visor automáticamente.

Después de la primera generación, `testing/ABRIR_REVISION.html` puede abrirse directamente con doble clic. No requiere servidor, Internet ni archivo `.bat` para visualizar los ECG ya preparados.

## Funciones del visor

- Selector de los 20 candidatos y navegación anterior/siguiente.
- Disposición secuencial 3 × 4 de 12 derivaciones.
- Tira larga de DII con los 10 segundos completos.
- Señal original de 500 Hz.
- Escala fija de revisión: 25 mm/s y 10 mm/mV.
- Informe original, códigos SCP, validación y calidad técnica.
- Estados `pending`, `approved`, `rejected` y `reserved`.
- Lista de comprobaciones clínicas y técnicas.
- Notas por candidato.
- Persistencia local en el navegador.
- Exportación e importación de `review_state.json`.

Un HTML abierto con doble clic no puede modificar archivos del repositorio. Las decisiones se guardan en `localStorage`; use **Exportar review_state.json** para obtener un archivo que pueda sustituir posteriormente a `testing/review/review_state.json` tras una revisión consciente.

## Archivos generados localmente

```text
testing/
├── ABRIR_REVISION.html
├── candidates/
│   └── atrial_fibrillation/
│       └── afib_00330/
│           ├── source_hr.hea
│           ├── source_hr.dat
│           ├── signal_500hz.json
│           └── metadata.json
├── catalog/
│   └── afib_candidates.json
└── review/
    └── review_state.json
```

Los archivos de señales y el HTML autónomo no se versionan porque pueden regenerarse desde PhysioNet usando el manifiesto.

## Uso por terminal

Construcción completa:

```bash
python tools/build_test_candidates.py
```

Reconstruir todo desde cero:

```bash
python tools/build_test_candidates.py --force
```

Reparar o descargar un candidato concreto y después regenerar el visor completo:

```bash
python tools/build_test_candidates.py --only afib_00330
```

Reconstruir únicamente el HTML cuando las 20 señales ya existen:

```bash
python tools/build_test_candidates.py --viewer-only
```

## Flujo de revisión

1. Leer `catalog/afib_candidates.json`.
2. Descargar la señal original PTB-XL de 500 Hz.
3. Revisar visualmente las 12 derivaciones y DII largo.
4. Comprobar irregularidad RR, ausencia de ondas P consistentes, actividad fibrilatoria y artefacto.
5. Documentar los hallazgos concomitantes.
6. Marcar el candidato como aprobado, rechazado o reservado.
7. Exportar `review_state.json`.
8. Promover a producción solo mediante una acción explícita posterior.

## Reglas de integridad

- No dibujar, suavizar, normalizar, corregir ni mezclar ondas.
- Mantener el `ecgId` original de PTB-XL.
- Usar exclusivamente la señal original de 500 Hz durante la revisión.
- No aprobar automáticamente ningún registro.
- No interpretar la preselección por metadatos como validación clínica final.
- El ECG 8215 permanece en producción y está excluido de los 20 candidatos.
- El visor es una herramienta educativa y no está destinado al diagnóstico ni a decisiones clínicas.
