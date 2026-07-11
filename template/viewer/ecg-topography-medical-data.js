'use strict';

/*
  ECG_TOPOGRAPHY_EDUCATION
  ------------------------
  Contenido médico estructurado para una capa educativa de topografía isquémica.

  PRINCIPIOS:
  1. Este archivo NO contiene señales ECG y NO debe modificar ningún trazado.
  2. La correlación ECG-territorio-arteria es probabilística, no anatómica absoluta.
  3. Las derivaciones V3R, V4R y V7-V9 no existen en el ECG estándar del banco actual.
     Deben mostrarse como derivaciones adicionales recomendadas, sin fabricar señales.
  4. "Septal", "anterior", "lateral" y "posterior" son etiquetas electrocardiográficas
     didácticas. No equivalen a una segmentación anatómica perfecta.
*/

(function exposeECGTopographyEducation(global) {
  const deepFreeze = value => {
    if (!value || typeof value !== 'object' || Object.isFrozen(value)) return value;
    Object.freeze(value);
    Object.values(value).forEach(deepFreeze);
    return value;
  };

  const ROLE_STYLES = {
    primary: {
      label: 'Derivaciones orientadoras principales',
      frameStyle: 'solid',
      clinicalMeaning: 'Observan directamente el territorio en el esquema electrocardiográfico convencional.'
    },
    extension: {
      label: 'Extensión posible',
      frameStyle: 'dashed',
      clinicalMeaning: 'Pueden alterarse según extensión, nivel de oclusión, dominancia o variación anatómica.'
    },
    reciprocal: {
      label: 'Cambios recíprocos o indirectos',
      frameStyle: 'dotted',
      clinicalMeaning: 'No observan directamente el territorio; muestran el vector opuesto o una pista indirecta.'
    },
    highRiskPattern: {
      label: 'Patrón de alto riesgo',
      frameStyle: 'double',
      clinicalMeaning: 'Patrón sindromático de isquemia extensa; no identifica por sí solo una arteria culpable.'
    },
    additionalUnavailable: {
      label: 'Derivaciones adicionales no disponibles',
      frameStyle: 'badge-only',
      clinicalMeaning: 'Deben registrarse aparte. No se debe reutilizar ni transformar otra señal para simularlas.'
    }
  };

  const SIMPLE_TERRITORIES = [
    {
      id: 'simple_anterior',
      order: 1,
      label: 'Cara anterior',
      shortLabel: 'Anterior',
      category: 'topography',
      leadGroups: [
        { role: 'primary', leads: ['V3', 'V4'] }
      ],
      oneLine: 'V3-V4 orientan a afectación anterior, habitualmente relacionada con la arteria descendente anterior.',
      probableArteries: ['Arteria descendente anterior'],
      caution: 'El ECG localiza un territorio eléctrico; la coronariografía confirma la anatomía.'
    },
    {
      id: 'simple_inferior',
      order: 2,
      label: 'Cara inferior',
      shortLabel: 'Inferior',
      category: 'topography',
      leadGroups: [
        { role: 'primary', leads: ['II', 'III', 'aVF'] }
      ],
      oneLine: 'II, III y aVF observan la cara inferior.',
      probableArteries: ['Arteria coronaria derecha', 'Arteria circunfleja'],
      caution: 'La arteria coronaria derecha es frecuente, pero la circunfleja puede ser culpable según la dominancia.'
    },
    {
      id: 'simple_lateral_low',
      order: 3,
      label: 'Cara lateral baja',
      shortLabel: 'Lateral baja',
      category: 'topography',
      leadGroups: [
        { role: 'primary', leads: ['V5', 'V6'] }
      ],
      oneLine: 'V5-V6 orientan a afectación lateral izquierda.',
      probableArteries: ['Arteria circunfleja', 'Arteria descendente anterior'],
      caution: 'No debe llamarse territorio apical de forma automática.'
    },
    {
      id: 'simple_lateral_high',
      order: 4,
      label: 'Cara lateral alta',
      shortLabel: 'Lateral alta',
      category: 'topography',
      leadGroups: [
        { role: 'primary', leads: ['I', 'aVL'] }
      ],
      oneLine: 'I y aVL orientan a afectación lateral alta.',
      probableArteries: ['Rama diagonal de la arteria descendente anterior', 'Arteria circunfleja', 'Rama marginal obtusa'],
      caution: 'I y aVL no identifican de forma exclusiva una rama diagonal.'
    },
    {
      id: 'simple_septal',
      order: 5,
      label: 'Cara septal',
      shortLabel: 'Septal',
      category: 'topography',
      leadGroups: [
        { role: 'primary', leads: ['V1', 'V2'] }
      ],
      oneLine: 'V1-V2 se denominan septales en la clasificación tradicional.',
      probableArteries: ['Arteria descendente anterior'],
      caution: 'V1-V2 no representan exclusivamente el tabique; también reciben vectores del ventrículo derecho y de regiones anteriores.'
    },
    {
      id: 'simple_posterior',
      order: 6,
      label: 'Cara posterior',
      shortLabel: 'Posterior',
      preferredAdvancedLabel: 'Posterior o inferobasal',
      category: 'topography',
      leadGroups: [
        { role: 'reciprocal', leads: ['V1', 'V2', 'V3'] },
        { role: 'additionalUnavailable', leads: ['V7', 'V8', 'V9'] }
      ],
      oneLine: 'En un ECG de 12 derivaciones se sospecha por descenso del ST y R prominente en V1-V3; se confirma con V7-V9.',
      probableArteries: ['Arteria circunfleja', 'Arteria coronaria derecha'],
      caution: 'V1-V3 son cambios indirectos. No deben colorearse como derivaciones directas.'
    },
    {
      id: 'simple_right_ventricle',
      order: 7,
      label: 'Ventrículo derecho',
      shortLabel: 'Ventrículo derecho',
      category: 'topography',
      leadGroups: [
        { role: 'reciprocal', leads: ['III', 'aVF', 'V1'] },
        { role: 'additionalUnavailable', leads: ['V3R', 'V4R'] }
      ],
      oneLine: 'Ante un infarto inferior, V3R-V4R —especialmente V4R— evalúan isquemia del ventrículo derecho.',
      probableArteries: ['Arteria coronaria derecha proximal'],
      caution: 'III mayor que II favorece arteria coronaria derecha, pero no confirma por sí solo infarto del ventrículo derecho.'
    }
  ];

  const ADVANCED_TERRITORIES = [
    ...SIMPLE_TERRITORIES,
    {
      id: 'advanced_lateral_complete',
      order: 20,
      label: 'Cara lateral completa',
      shortLabel: 'Lateral completa',
      category: 'combinedTopography',
      leadGroups: [
        { role: 'primary', leads: ['I', 'aVL', 'V5', 'V6'] }
      ],
      anatomy: 'Pared lateral del ventrículo izquierdo, observada en los planos frontal y horizontal.',
      interpretation: 'La afectación puede corresponder a arteria circunfleja, ramas marginales obtusas, ramas diagonales o extensión de una lesión de la arteria descendente anterior.',
      caution: 'No existe una correspondencia uno-a-uno entre estas derivaciones y una sola rama coronaria.'
    },
    {
      id: 'advanced_anteroseptal',
      order: 21,
      label: 'Patrón anteroseptal',
      shortLabel: 'Anteroseptal',
      category: 'combinedTopography',
      leadGroups: [
        { role: 'primary', leads: ['V1', 'V2', 'V3', 'V4'] }
      ],
      anatomy: 'Vector de lesión que abarca las derivaciones precordiales derechas y anteriores.',
      interpretation: 'Orienta principalmente a afectación de la arteria descendente anterior.',
      caution: 'La palabra anteroseptal describe el patrón ECG; no demuestra una necrosis septal anatómicamente aislada.'
    },
    {
      id: 'advanced_anterolateral',
      order: 22,
      label: 'Patrón anterolateral',
      shortLabel: 'Anterolateral',
      category: 'combinedTopography',
      leadGroups: [
        { role: 'primary', leads: ['V3', 'V4', 'V5', 'V6'] },
        { role: 'extension', leads: ['I', 'aVL'] }
      ],
      anatomy: 'Afectación anterior con extensión hacia la pared lateral.',
      interpretation: 'Puede observarse en una lesión extensa de la arteria descendente anterior, particularmente si compromete ramas diagonales.',
      caution: 'La presencia o ausencia de I y aVL depende de la extensión y de la anatomía individual.'
    },
    {
      id: 'advanced_inferoposterior',
      order: 23,
      label: 'Patrón inferoposterior',
      shortLabel: 'Inferoposterior',
      category: 'combinedTopography',
      leadGroups: [
        { role: 'primary', leads: ['II', 'III', 'aVF'] },
        { role: 'reciprocal', leads: ['V1', 'V2', 'V3'] },
        { role: 'additionalUnavailable', leads: ['V7', 'V8', 'V9'] }
      ],
      anatomy: 'Afectación inferior con extensión posterior o inferobasal.',
      interpretation: 'Puede corresponder a arteria coronaria derecha dominante o arteria circunfleja dominante.',
      caution: 'La extensión posterior debe confirmarse con V7-V9 cuando estén indicadas.'
    },
    {
      id: 'advanced_inferior_rv',
      order: 24,
      label: 'Patrón inferior con ventrículo derecho',
      shortLabel: 'Inferior + VD',
      category: 'combinedTopography',
      leadGroups: [
        { role: 'primary', leads: ['II', 'III', 'aVF'] },
        { role: 'reciprocal', leads: ['V1'] },
        { role: 'additionalUnavailable', leads: ['V3R', 'V4R'] }
      ],
      anatomy: 'Infarto inferior con extensión al ventrículo derecho.',
      interpretation: 'Sugiere una oclusión proximal de la arteria coronaria derecha antes de las ramas ventriculares derechas.',
      caution: 'La confirmación electrocardiográfica requiere derivaciones derechas, principalmente V4R.'
    },
    {
      id: 'advanced_diffuse_subendocardial',
      order: 25,
      label: 'Isquemia subendocárdica difusa',
      shortLabel: 'Isquemia difusa',
      category: 'highRiskPattern',
      leadGroups: [
        { role: 'highRiskPattern', leads: ['I', 'II', 'III', 'aVL', 'aVF', 'V4', 'V5', 'V6'] },
        { role: 'extension', leads: ['aVR', 'V1'] }
      ],
      anatomy: 'Desequilibrio isquémico circunferencial o multiterritorial.',
      interpretation: 'Descenso del ST en múltiples derivaciones con elevación en aVR y/o V1 sugiere isquemia multivaso o posible obstrucción del tronco coronario izquierdo, sobre todo con compromiso hemodinámico.',
      caution: 'No es un patrón específico ni diagnóstico de lesión del tronco coronario izquierdo.'
    }
  ];

  const SIMPLE_ARTERIES = [
    {
      id: 'artery_lad_simple',
      order: 1,
      label: 'Arteria descendente anterior',
      category: 'coronary',
      territories: ['Septal', 'Anterior', 'Anteroseptal', 'Apical', 'Anterolateral si la lesión es extensa'],
      leadGroups: [
        { role: 'primary', leads: ['V1', 'V2', 'V3', 'V4'] },
        { role: 'extension', leads: ['V5', 'V6', 'I', 'aVL'] }
      ],
      summary: 'Arteria más relacionada con patrones septales, anteriores y anteroseptales.',
      caution: 'La extensión a V5-V6, I y aVL puede sugerir una lesión extensa, pero no determina de manera confiable el nivel exacto de oclusión.'
    },
    {
      id: 'artery_rca_simple',
      order: 2,
      label: 'Arteria coronaria derecha',
      category: 'coronary',
      territories: ['Inferior', 'Ventrículo derecho si la oclusión es proximal', 'Posterior según dominancia'],
      leadGroups: [
        { role: 'primary', leads: ['II', 'III', 'aVF'] },
        { role: 'reciprocal', leads: ['V1', 'V2', 'V3'] },
        { role: 'additionalUnavailable', leads: ['V3R', 'V4R', 'V7', 'V8', 'V9'] }
      ],
      summary: 'Se asocia sobre todo con infarto inferior y puede extenderse al ventrículo derecho o a la región posterior.',
      caution: 'La relación III mayor que II favorece esta arteria, pero no es una prueba anatómica definitiva.'
    },
    {
      id: 'artery_lcx_simple',
      order: 3,
      label: 'Arteria circunfleja',
      category: 'coronary',
      territories: ['Lateral', 'Posterolateral', 'Posterior o inferobasal', 'Inferior si existe dominancia izquierda'],
      leadGroups: [
        { role: 'primary', leads: ['I', 'aVL', 'V5', 'V6'] },
        { role: 'reciprocal', leads: ['V1', 'V2', 'V3'] },
        { role: 'extension', leads: ['II', 'III', 'aVF'] },
        { role: 'additionalUnavailable', leads: ['V7', 'V8', 'V9'] }
      ],
      summary: 'Se relaciona con territorio lateral y posterior; algunas oclusiones pueden ser poco evidentes en el ECG estándar.',
      caution: 'La afectación inferior depende de la dominancia coronaria.'
    }
  ];

  const ADVANCED_ARTERIES = [
    ...SIMPLE_ARTERIES,
    {
      id: 'artery_diagonal',
      order: 10,
      label: 'Rama diagonal de la arteria descendente anterior',
      category: 'coronaryBranch',
      territories: ['Lateral alta'],
      leadGroups: [
        { role: 'primary', leads: ['I', 'aVL'] }
      ],
      summary: 'Una causa posible de patrón lateral alto.',
      anatomy: 'Las ramas diagonales irrigan porciones anterolaterales del ventrículo izquierdo.',
      caution: 'I y aVL también pueden alterarse por arteria circunfleja, rama marginal obtusa o arteria descendente anterior proximal.'
    },
    {
      id: 'artery_obtuse_marginal',
      order: 11,
      label: 'Rama marginal obtusa de la arteria circunfleja',
      category: 'coronaryBranch',
      territories: ['Lateral', 'Lateral alta o baja según la rama'],
      leadGroups: [
        { role: 'primary', leads: ['I', 'aVL', 'V5', 'V6'] }
      ],
      summary: 'Irriga la pared lateral del ventrículo izquierdo.',
      caution: 'El ECG no permite distinguir de forma consistente una rama marginal obtusa de una lesión circunfleja más proximal.'
    },
    {
      id: 'artery_pda',
      order: 12,
      label: 'Rama descendente posterior',
      category: 'coronaryBranch',
      territories: ['Inferior', 'Posterior o inferobasal', 'Porción posterior del tabique'],
      leadGroups: [
        { role: 'primary', leads: ['II', 'III', 'aVF'] },
        { role: 'reciprocal', leads: ['V1', 'V2', 'V3'] },
        { role: 'additionalUnavailable', leads: ['V7', 'V8', 'V9'] }
      ],
      summary: 'Puede originarse en la arteria coronaria derecha o en la arteria circunfleja según la dominancia.',
      caution: 'El ECG suele describirse como infarto inferior con extensión posterior, no como diagnóstico seguro de una oclusión aislada de esta rama.'
    },
    {
      id: 'artery_left_main',
      order: 13,
      label: 'Tronco coronario izquierdo',
      category: 'highRiskCoronaryPattern',
      territories: ['Isquemia extensa del ventrículo izquierdo'],
      leadGroups: [
        { role: 'highRiskPattern', leads: ['I', 'II', 'III', 'aVL', 'aVF', 'V4', 'V5', 'V6'] },
        { role: 'extension', leads: ['aVR', 'V1'] }
      ],
      summary: 'El patrón clásico es descenso difuso del ST con elevación en aVR y/o V1.',
      caution: 'Debe rotularse como patrón de alto riesgo compatible con isquemia multivaso o posible tronco coronario izquierdo; no como diagnóstico específico de esa arteria.'
    }
  ];

  const DATA = {
    schemaVersion: '1.0.0',
    language: 'es',
    defaultMode: 'simple',
    standardLeadOrder: ['I', 'II', 'III', 'aVR', 'aVL', 'aVF', 'V1', 'V2', 'V3', 'V4', 'V5', 'V6'],
    standardLeadGrid: [
      ['I', 'aVR', 'V1', 'V4'],
      ['II', 'aVL', 'V2', 'V5'],
      ['III', 'aVF', 'V3', 'V6']
    ],
    longLead: 'II',
    additionalLeadsNotPresentInCurrentBank: ['V3R', 'V4R', 'V7', 'V8', 'V9'],
    uiSemantics: {
      allowMultipleSelections: true,
      clickingActiveItemRemovesIt: true,
      preserveActivationOrder: true,
      firstSelectedFrameIsInnermost: true,
      laterFramesExpandOutward: true,
      resetClearsAllSelections: true,
      includeLongLeadDuplicateWhenLeadIIIsSelected: true,
      neverModifySignalArrays: true,
      neverDrawIntoECGCanvas: true,
      missingAdditionalLeadPolicy: 'show-badge-and-clinical-note-only',
      roleStyles: ROLE_STYLES
    },
    modeDefinitions: {
      simple: {
        title: 'Topografía simplificada',
        description: 'Grupos esenciales y tres arterias coronarias principales.',
        orderNote: 'Orden pedagógico aproximado: primero los patrones frecuentes y de mayor utilidad clínica. No representa una incidencia universal.',
        topographicTerritories: SIMPLE_TERRITORIES,
        coronaryCorrelations: SIMPLE_ARTERIES
      },
      advanced: {
        title: 'Topografía profunda',
        description: 'Incluye patrones combinados, extensiones, cambios recíprocos, ramas coronarias y advertencias anatómicas.',
        orderNote: 'La correlación con una arteria culpable es probabilística y debe confirmarse con el contexto clínico y la anatomía coronaria.',
        topographicTerritories: ADVANCED_TERRITORIES,
        coronaryCorrelations: ADVANCED_ARTERIES
      }
    },
    globalClinicalWarnings: [
      'El electrocardiograma identifica territorios eléctricos, no delimita con precisión absoluta segmentos anatómicos.',
      'La anatomía coronaria, la dominancia, las colaterales y el nivel de oclusión modifican el patrón.',
      'Un ECG inicial normal o no diagnóstico no excluye un síndrome coronario agudo.',
      'Las derivaciones adicionales deben registrarse realmente; nunca deben simularse reutilizando otra señal.',
      'Este módulo es educativo y no debe emitir un diagnóstico automático del paciente.'
    ],
    evidenceBasis: [
      {
        source: 'European Society of Cardiology',
        document: '2023 Guidelines for the management of acute coronary syndromes',
        keyPoints: [
          'V3R-V4R ante sospecha de infarto inferior para evaluar isquemia del ventrículo derecho.',
          'V7-V9 para investigar infarto posterior.',
          'Descenso del ST en V1-V3 y/o elevación en V7-V9 orientan a oclusión posterior.',
          'Descenso del ST en seis o más derivaciones con elevación en aVR y/o V1 sugiere isquemia multivaso o posible tronco coronario izquierdo.'
        ]
      },
      {
        source: 'Farreras-Rozman. Medicina Interna, 20.ª edición, 2024',
        document: 'Capítulo de examen clínico cardiovascular y electrocardiografía',
        keyPoints: [
          'V1-V2 exploran predominantemente región septal y ventrículo derecho.',
          'V3-V4 exploran región anterior.',
          'I y aVL tienen orientación lateral; II, III y aVF inferior.',
          'V3R-V4R exploran ventrículo derecho y V7-V9 regiones posteriores/laterales.'
        ]
      }
    ]
  };

  global.ECG_TOPOGRAPHY_EDUCATION = deepFreeze(DATA);
})(window);
