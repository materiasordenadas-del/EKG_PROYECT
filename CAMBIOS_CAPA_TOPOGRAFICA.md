# Capa educativa de topografía ECG

## Cómo abrir y usar

Abra `output/ECG_BANCO_INICIAL_REAL/ABRIR_VISOR.html`. Sobre el papel ECG aparecen dos modos:

- **Simplificada:** caras cardíacas y tres arterias principales.
- **Profunda:** añade patrones combinados, ramas coronarias, extensiones y advertencias.

Pulse un territorio o una arteria para ver marcos de color sobre sus derivaciones. Pulse de nuevo para retirarlo. Las selecciones pueden combinarse: el primer marco queda interno y los siguientes se añaden hacia fuera. El botón **Restablecer** borra todo.

La leyenda identifica cada color y estilo de línea. DII marca también su tira larga. V3R, V4R y V7-V9 se muestran únicamente como derivaciones adicionales recomendadas; no existen trazados fabricados para ellas.

## Archivos

- Creados: `template/viewer/ecg-topography-medical-data.js`, `topography-overlay.js`, `topography-overlay.css` y `tools/test_topography_overlay.py`.
- Modificados: plantilla HTML, aplicación y estilos del visor; el visor generado se actualiza con `python tools/build_ecg_bank.py --refresh-viewer-data`.

## Integridad y límites

La capa está fuera del canvas y solo dibuja marcos transparentes. No modifica la señal, su muestreo, ganancia, velocidad del papel, diagnóstico ni metadatos. La relación territorio–arteria se muestra como probable y educativa; no confirma una lesión ni sustituye la evaluación clínica o la coronariografía.
