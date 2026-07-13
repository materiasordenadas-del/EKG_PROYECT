# ECG_BANCO_INICIAL_REAL_COMPLETO_V4

Esta versión descarga para cada registro las señales oficiales de PTB-XL a 100 Hz y 500 Hz.

El panel desplegable Información del registro muestra:
- Paciente: ID, edad, sexo, altura y peso.
- Adquisición: fecha, dispositivo, centro, personal e ID del ECG.
- Informe: original, autogenerado, eje, estadio de infarto y códigos SCP traducidos.
- Validación: evaluación humana, segunda opinión y estado de revisión.
- Calidad técnica: ruido, deriva, electrodos, latidos extras y marcapasos.
- Comparación numérica 100 vs 500 Hz de V2–V5.

No se muestra una sección de procedencia en la interfaz.

## Abrir el banco

Abra `output\ECG_BANCO_INICIAL_REAL\ABRIR_VISOR.html` con doble clic. No requiere Internet, descargas, servidor ni archivo `.bat`.

`GENERAR_TODO_Y_ABRIR.bat` queda solo para crear el banco la primera vez. Si el banco ya existe, también lo abre sin descargar nada.

## Animación y frecuencia cardíaca

La animación no tiene controles 0,5×, 1×, 2× ni selector de velocidad. El papel permanece fijo a 25 mm/s: los 10 segundos ocupan 250 mm en la cuadrícula y, si no caben en pantalla, se muestran con desplazamiento horizontal. El cursor usa siempre el mismo tiempo visible; no se acelera al cambiar la FC.

- La FC original se estima técnicamente desde DII de la señal original de 500 Hz; no modifica la señal ni constituye un diagnóstico.
- La FC de reproducción cambia únicamente qué momento de la señal se dibuja en cada punto de tiempo visible: `tiempo de señal = tiempo visible × (FC de reproducción / FC original)`.
- A 120 lpm frente a un original de 60 lpm se ven aproximadamente el doble de complejos en los mismos 10 segundos de pantalla; el cursor no se mueve más rápido.
- Pausar/Reproducir no cambia la FC. Reiniciar vuelve al inicio y conserva la FC de reproducción elegida. "Restablecer FC original" devuelve la escala a tiempo real.

## Pantalla de monitor

En el selector **Pantalla**, elija **Monitor negro** para ver un fondo negro sin cuadrícula ni línea de base, con ondas y etiquetas verdes. Este cambio es solamente visual y no altera ninguna señal ECG.

## Capa educativa de topografía

Sobre el ECG están los modos **Simplificada** y **Profunda**. Seleccione caras cardíacas o arterias para ver marcos de colores sobre las derivaciones relacionadas; un segundo clic las retira y **Restablecer** borra todas las selecciones.

Los marcos no modifican la señal ni colorean ondas. V3R, V4R y V7-V9 se muestran solo como derivaciones adicionales recomendadas, porque no existen en este banco de 12 derivaciones. Consulte `CAMBIOS_CAPA_TOPOGRAFICA.md` para el uso y las limitaciones.

## Manual para añadir o actualizar ritmos (para ChatGPT)

Este banco contiene ECG reales de PTB-XL. Nunca se deben dibujar, corregir, suavizar, normalizar ni mezclar señales.

### Abrir y revisar

1. Abrir `output\ECG_BANCO_INICIAL_REAL\ABRIR_VISOR.html`.
2. Elegir el ritmo y la resolución. Para revisar morfología, usar siempre 500 Hz.
3. Consultar "Información del registro" para ver los códigos SCP, informe y calidad técnica.

### Añadir un ritmo nuevo

1. Hacer una copia completa de la carpeta `output\ECG_BANCO_INICIAL_REAL` antes de generar nada.
2. En `tools\build_ecg_bank.py`, añadir una entrada a `TARGETS` con: identificador corto, título visible, código SCP objetivo y códigos compatibles.
3. Revisar que el código SCP existe en `scp_statements.csv` y que no contradice el ritmo buscado.
4. Ejecutar manualmente `python tools\build_ecg_bank.py`. Este paso reconstruye el banco y descarga solo fuentes originales de PTB-XL; no modifica ondas manualmente.
5. Abrir el HTML, comprobar 12 derivaciones, 10 segundos, unidades en mV y la señal de 500 Hz. La selección clínica final debe ser humana.

### Actualizar solo el visor, sin tocar ECG

Después de modificar archivos de `template\viewer`, ejecutar:

`python tools\build_ecg_bank.py --refresh-viewer-data`

Este comando reemplaza únicamente los archivos del visor y vuelve a crear `viewer\data.js`. No descarga, borra ni cambia señales ni metadatos de los ECG.

### Datos que no se deben modificar

- `rhythms\...\signal_500hz.json` y `signal_100hz.json`
- archivos fuente `.hea` y `.dat`
- el `ecgId` de un ECG ya elegido

Al añadir nuevos ritmos, conservar las copias de seguridad y documentar el código SCP, el `ecgId`, cualquier hallazgo concomitante y la decisión de revisión humana.
