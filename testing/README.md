# Laboratorio general de pruebas ECG

`testing/` es el entorno general y aislado para probar candidatos, funciones de interfaz y cambios educativos antes de incorporarlos a la aplicación estable.

## Regla principal

Nada dentro de `testing/` puede modificar, borrar, sobrescribir ni promover automáticamente contenido de `output/ECG_BANCO_INICIAL_REAL`.

## Acceso online

GitHub Actions construye un único sitio con dos entradas:

```text
/                  Aplicación estable
/testing/          Portal general de pruebas
/testing/ABRIR_REVISION.html   Primer módulo: candidatos AFIB
```

El flujo `.github/workflows/deploy-pages.yml`:

1. Descarga el repositorio.
2. Instala las dependencias de Python.
3. Ejecuta `tools/build_test_candidates.py`.
4. Descarga desde PTB-XL las señales originales a 500 Hz.
5. Genera el visor AFIB autocontenido con los 20 ECG incrustados.
6. Publica producción y testing dentro del mismo sitio de GitHub Pages.

En la configuración de GitHub Pages debe seleccionarse **GitHub Actions** como fuente de publicación. No debe alternarse entre una rama estable y una rama de candidatos.

## Organización general

```text
testing/
├── index.html                         Portal general del laboratorio
├── ABRIR_REVISION.html                Artefacto generado del módulo AFIB
├── catalog/
│   └── afib_candidates.json
├── review/
│   └── review_state.json
├── candidates/
│   └── atrial_fibrillation/           Señales locales regenerables
├── reports/                           Informes futuros
└── modules/                           Espacio reservado para nuevos módulos
```

La fibrilación auricular es el primer módulo, pero `testing/` no está limitado a ese ritmo. Los siguientes módulos pueden utilizar la misma raíz para flutter, bloqueos AV, extrasístoles, taquicardias, nuevos candidatos, pruebas topográficas o pruebas de interfaz.

## Módulo AFIB

El visor permite:

- Elegir entre 20 candidatos PTB-XL.
- Navegar al ECG anterior o siguiente.
- Revisar las 12 derivaciones y DII largo.
- Mantener 500 Hz, 25 mm/s y 10 mm/mV.
- Consultar informe, códigos SCP, validación y calidad técnica.
- Marcar `pending`, `approved`, `rejected` o `reserved`.
- Completar una lista de comprobaciones.
- Guardar notas en el navegador.
- Importar o exportar `review_state.json`.

Las decisiones se guardan en `localStorage`. El navegador no modifica directamente el repositorio; para versionar una revisión debe exportarse `review_state.json` y reemplazarse conscientemente el archivo correspondiente.

## Uso local opcional

En Windows puede ejecutarse:

```text
GENERAR_PRUEBAS_AFIB.bat
```

Por terminal:

```bash
python tools/build_test_candidates.py
```

Reconstrucción completa:

```bash
python tools/build_test_candidates.py --force
```

Un candidato concreto:

```bash
python tools/build_test_candidates.py --only afib_00330
```

## Reglas de integridad

- No dibujar, suavizar, normalizar, corregir ni mezclar ondas.
- Mantener el `ecgId` original de PTB-XL.
- Usar la señal original de 500 Hz durante la revisión.
- No aprobar automáticamente ningún registro.
- No considerar la preselección por metadatos como validación clínica final.
- El ECG 8215 permanece en producción y está excluido de los 20 candidatos.
- El laboratorio es educativo y no está destinado al diagnóstico ni a decisiones clínicas.
