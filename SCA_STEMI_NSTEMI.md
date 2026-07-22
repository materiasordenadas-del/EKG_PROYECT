# SCA: STEMI y NSTEMI en la rama `pruebas`

## Alcance

Se incorporan dos objetivos educativos al banco de ECG:

1. **STEMI**: candidatos con patrón electrocardiográfico compatible con infarto agudo de miocardio con elevación del segmento ST.
2. **NSTEMI**: candidatos con lesión o isquemia subendocárdica compatible con un síndrome coronario agudo sin elevación persistente del ST.

Estos objetivos se manejan como **candidatos pendientes de revisión clínica humana**, no como diagnósticos automáticos.

## Restricción clínica obligatoria

El ECG aislado no puede confirmar un NSTEMI. El diagnóstico clínico requiere síntomas compatibles, elevación y dinámica de troponina y ausencia de elevación persistente del ST. Por eso, la interfaz y los metadatos deben mostrar `NSTEMI (patrón ECG compatible)` y nunca presentar el trazado como NSTEMI confirmado.

Un patrón compatible con STEMI tampoco sustituye la evaluación clínica ni la exclusión de imitadores de elevación del ST.

## Reglas de preselección en PTB-XL

### STEMI

- Presencia de un código de localización de infarto: `AMI`, `ASMI`, `ALMI`, `IMI`, `ILMI`, `IPMI`, `IPLMI`, `LMI` o `PMI`.
- Además, estadio de infarto agudo `Stadium I`/`Stadium I-II` o código `STE_`.
- Exclusión de códigos de lesión subendocárdica `INJ*`, marcapasos y preexcitación.
- Revisión visual obligatoria a 500 Hz para confirmar elevación del ST en derivaciones contiguas, cambios recíprocos, territorio y posibles imitadores.

### NSTEMI — patrón compatible

- Presencia de un código de lesión subendocárdica: `INJAS`, `INJAL`, `INJIN`, `INJLA` o `INJIL`.
- Ausencia de `STE_`, marcapasos, preexcitación y bloqueo completo de rama izquierda.
- Revisión visual obligatoria a 500 Hz.
- La aprobación solo significa que el ECG es compatible con lesión/isquemia subendocárdica; no confirma necrosis miocárdica.

## Integridad de señal

- Las señales proceden de PTB-XL 1.0.3.
- No se dibujan, corrigen, suavizan, mezclan ni fabrican ondas.
- Se conservan las versiones oficiales a 100 Hz y 500 Hz.
- Cada candidato mantiene códigos SCP, informe original, estadio de infarto, calidad técnica y validación humana disponible.

## Ejecución prevista

```bash
python tools/populate_sca_pruebas.py --per-group 5
```

El script debe ejecutarse exclusivamente en la rama `pruebas`. Los candidatos generados permanecen con estado `pending_review` hasta revisión humana.

## Fuentes

- PTB-XL 1.0.3: https://physionet.org/content/ptb-xl/1.0.3/
- Wagner P, et al. PTB-XL, a large publicly available electrocardiography dataset. Scientific Data. 2020. DOI: 10.1038/s41597-020-0495-6
