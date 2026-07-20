from __future__ import annotations

import csv
import io
import json
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat
from scipy.signal import resample_poly

ROOT = Path(__file__).resolve().parents[1]
BANK = ROOT / "output" / "ECG_BANCO_INICIAL_REAL"
RHYTHMS = BANK / "rhythms"
CATALOG = BANK / "catalog" / "rhythms_catalog.json"
CATALOG_CSV = BANK / "catalog" / "rhythms_catalog.csv"
MANIFEST = BANK / "candidates" / "ventricular_tachycardia_candidates.json"
CACHE = ROOT / ".cache"
ARCHIVE = CACHE / "PhysioNetChallenge2020_Training_E.tar.gz"
ARCHIVE_URLS = (
    "https://storage.googleapis.com/physionet-challenge-2020-12-lead-ecg-public/PhysioNetChallenge2020_Training_E.tar.gz",
    "https://cloudypipeline.com:9555/api/download/physionet2020training/PhysioNetChallenge2020_Training_E.tar.gz/",
)

TARGET_SNOMED = "164895002"
TARGET_CODE = "VT"
TARGET_DIAGNOSIS = "Taquicardia ventricular"
TARGET_COUNT = 20
LEADS = ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]
LEAD_CANON = {lead.upper(): lead for lead in LEADS}


def ensure_pruebas_branch() -> None:
    branch = subprocess.check_output(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=ROOT, text=True
    ).strip()
    if branch != "pruebas":
        raise RuntimeError(
            f"Este generador solo puede ejecutarse en la rama pruebas; rama actual: {branch}"
        )


def download_archive() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    if ARCHIVE.exists() and ARCHIVE.stat().st_size > 10_000_000:
        return

    temporary = ARCHIVE.with_suffix(".partial")
    temporary.unlink(missing_ok=True)
    errors: list[str] = []
    for url in ARCHIVE_URLS:
        try:
            print(f"Descargando Georgia G12EC desde {url}")
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "EKG-PROYECT-pruebas/2.0"},
            )
            with urllib.request.urlopen(request, timeout=300) as source, temporary.open("wb") as target:
                shutil.copyfileobj(source, target, length=1024 * 1024)
            if temporary.stat().st_size <= 10_000_000:
                raise RuntimeError("el archivo descargado es demasiado pequeño")
            temporary.replace(ARCHIVE)
            return
        except Exception as exc:  # pragma: no cover - depende de la red externa
            errors.append(f"{url}: {exc}")
            temporary.unlink(missing_ok=True)
    raise RuntimeError("No se pudo descargar el archivo Georgia G12EC:\n" + "\n".join(errors))


def write_json(path: Path, value: Any, compact: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if compact:
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    else:
        text = json.dumps(value, ensure_ascii=False, indent=2)
    path.write_text(text + "\n", encoding="utf-8")


def parse_number(value: str | None) -> float | None:
    if value is None:
        return None
    value = value.strip()
    if not value or value.lower() in {"nan", "unknown", "none", "null"}:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def header_attribute(lines: list[str], key: str) -> str | None:
    prefix = f"#{key}:"
    for line in lines:
        if line.startswith(prefix):
            value = line[len(prefix):].strip()
            return None if value.lower() == "unknown" else value
    return None


def diagnosis_codes(lines: list[str]) -> list[str]:
    raw = header_attribute(lines, "Dx") or ""
    return [item.strip() for item in raw.split(",") if item.strip()]


def parse_header(text: str, member_name: str) -> dict[str, Any]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError(f"Encabezado vacío: {member_name}")

    first = lines[0].split()
    if len(first) < 4:
        raise RuntimeError(f"Primera línea inválida en {member_name}")
    record_id = first[0]
    lead_count = int(first[1])
    sample_rate = int(round(float(first[2])))
    samples = int(first[3])
    if lead_count != 12 or sample_rate != 500 or samples != 5000:
        raise RuntimeError(
            f"{record_id}: se esperaban 12 derivaciones, 500 Hz y 5000 muestras; "
            f"se obtuvieron {lead_count}, {sample_rate} y {samples}"
        )

    signal_lines = lines[1 : 1 + lead_count]
    if len(signal_lines) != 12:
        raise RuntimeError(f"{record_id}: faltan líneas de derivaciones")

    channels: list[dict[str, Any]] = []
    for line in signal_lines:
        parts = line.split()
        if len(parts) < 9:
            raise RuntimeError(f"Línea de señal inválida en {record_id}: {line}")
        lead = LEAD_CANON.get(parts[-1].upper())
        if lead is None:
            raise RuntimeError(f"Derivación desconocida en {record_id}: {parts[-1]}")
        gain_match = re.match(r"([-+0-9.eE]+)(?:\(([-+0-9.eE]+)\))?/([^\s]+)", parts[2])
        if not gain_match:
            raise RuntimeError(f"Ganancia inválida en {record_id}: {parts[2]}")
        gain = float(gain_match.group(1))
        explicit_baseline = gain_match.group(2)
        adc_zero = float(parts[4])
        baseline = float(explicit_baseline) if explicit_baseline is not None else adc_zero
        channels.append(
            {
                "lead": lead,
                "gain": gain,
                "baseline": baseline,
                "units": gain_match.group(3),
            }
        )

    if {channel["lead"] for channel in channels} != set(LEADS):
        raise RuntimeError(f"{record_id}: el conjunto de derivaciones no es el estándar de 12 derivaciones")

    return {
        "recordId": record_id,
        "member": member_name,
        "sampleRateHz": sample_rate,
        "samples": samples,
        "channels": channels,
        "diagnoses": diagnosis_codes(lines),
        "age": parse_number(header_attribute(lines, "Age")),
        "sex": header_attribute(lines, "Sex"),
        "rx": header_attribute(lines, "Rx"),
        "history": header_attribute(lines, "Hx"),
        "symptoms": header_attribute(lines, "Sx"),
        "rawHeader": lines,
    }


def read_member_text(archive: tarfile.TarFile, member: tarfile.TarInfo) -> str:
    stream = archive.extractfile(member)
    if stream is None:
        raise RuntimeError(f"No se pudo leer {member.name}")
    return stream.read().decode("utf-8", errors="replace")


def discover_candidates(archive: tarfile.TarFile) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    header_members = sorted(
        (member for member in archive.getmembers() if member.isfile() and member.name.lower().endswith(".hea")),
        key=lambda member: member.name,
    )
    for member in header_members:
        text = read_member_text(archive, member)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if TARGET_SNOMED not in diagnosis_codes(lines):
            continue
        try:
            candidates.append(parse_header(text, member.name))
        except RuntimeError as exc:
            print(f"Omitido {member.name}: {exc}")

    candidates.sort(key=lambda item: item["recordId"])
    if not candidates:
        raise RuntimeError(
            f"No se encontraron registros con el código SNOMED CT {TARGET_SNOMED} en Georgia G12EC"
        )
    selected = candidates[:TARGET_COUNT]
    print(f"Encontrados {len(candidates)} registros de TV; se incorporarán {len(selected)}.")
    return selected


def find_mat_member(archive: tarfile.TarFile, header_member: str) -> tarfile.TarInfo:
    expected = str(Path(header_member).with_suffix(".mat")).replace("\\", "/")
    try:
        return archive.getmember(expected)
    except KeyError as exc:
        raise RuntimeError(f"No existe la señal correspondiente a {header_member}") from exc


def physical_signals(archive: tarfile.TarFile, candidate: dict[str, Any]) -> dict[str, list[float]]:
    member = find_mat_member(archive, candidate["member"])
    stream = archive.extractfile(member)
    if stream is None:
        raise RuntimeError(f"No se pudo leer {member.name}")
    payload = loadmat(io.BytesIO(stream.read()))
    if "val" not in payload:
        raise RuntimeError(f"{member.name} no contiene la matriz val")
    digital = np.asarray(payload["val"], dtype=np.float64)
    if digital.shape == (candidate["samples"], 12):
        digital = digital.T
    if digital.shape != (12, candidate["samples"]):
        raise RuntimeError(f"Dimensiones inesperadas en {member.name}: {digital.shape}")

    by_lead: dict[str, list[float]] = {}
    for index, channel in enumerate(candidate["channels"]):
        values = (digital[index] - channel["baseline"]) / channel["gain"]
        by_lead[channel["lead"]] = np.round(values, 6).tolist()
    return {lead: by_lead[lead] for lead in LEADS}


def resample_to_100hz(leads500: dict[str, list[float]]) -> dict[str, list[float]]:
    result: dict[str, list[float]] = {}
    for lead in LEADS:
        values = np.asarray(leads500[lead], dtype=np.float64)
        reduced = resample_poly(values, up=1, down=5, padtype="line")
        if reduced.size != 1000:
            raise RuntimeError(f"Remuestreo inválido en {lead}: {reduced.size} muestras")
        result[lead] = np.round(reduced, 6).tolist()
    return result


def signal_payload(
    rhythm_id: str,
    title: str,
    candidate: dict[str, Any],
    leads: dict[str, list[float]],
    sample_rate: int,
    derived: bool,
) -> dict[str, Any]:
    samples = len(leads[LEADS[0]])
    source: dict[str, Any] = {
        "dataset": "Georgia 12-Lead ECG Challenge Database",
        "datasetShortName": "G12EC",
        "challenge": "PhysioNet/Computing in Cardiology Challenge 2020",
        "version": "1.0.2",
        "recordId": candidate["recordId"],
        "archiveMember": candidate["member"],
        "snomedCtCodes": candidate["diagnoses"],
    }
    if derived:
        source["derivedFrom"] = "500 Hz official signal; polyphase resampling to 100 Hz"
    return {
        "schemaVersion": "1.1",
        "id": rhythm_id,
        "title": title,
        "source": source,
        "sampleRateHz": sample_rate,
        "durationSeconds": round(samples / sample_rate, 6),
        "samplesPerLead": samples,
        "units": "mV",
        "leadOrder": LEADS,
        "leads": {lead: leads[lead] for lead in LEADS},
    }


def code_description(code: str) -> str:
    if code == TARGET_SNOMED:
        return "Taquicardia ventricular (hallazgo electrocardiográfico)"
    return "Diagnóstico concomitante codificado en SNOMED CT; pendiente de traducción clínica"


def build_metadata(
    rhythm_id: str,
    title: str,
    candidate: dict[str, Any],
    sampling_validation: dict[str, Any],
) -> dict[str, Any]:
    diagnoses = candidate["diagnoses"]
    concomitant = [code for code in diagnoses if code != TARGET_SNOMED]
    numeric_record = int(re.sub(r"\D", "", candidate["recordId"]) or 0)
    return {
        "id": rhythm_id,
        "title": title,
        "targetCode": TARGET_CODE,
        "snomedCtCode": TARGET_SNOMED,
        "selectionScore": None,
        "ecgId": numeric_record,
        "sourceRecordId": candidate["recordId"],
        "candidateStatus": "pending_review",
        "status": "pending_review",
        "candidateGroup": "Taquicardia ventricular real",
        "candidateSummary": (
            "Registro de 12 derivaciones etiquetado con taquicardia ventricular; "
            "requiere revisión visual antes de promoción a main."
        ),
        "patient": {
            "patientId": candidate["recordId"],
            "age": candidate["age"],
            "sex": candidate["sex"],
            "height": None,
            "weight": None,
        },
        "acquisition": {
            "recordingDate": None,
            "device": None,
            "site": "Georgia, Estados Unidos",
            "nurse": None,
        },
        "report": {
            "original": f"Etiquetas SNOMED CT del encabezado WFDB: {', '.join(diagnoses)}",
            "initialAutogenerated": None,
            "heartAxis": None,
            "infarctionStadium1": None,
            "infarctionStadium2": None,
            "scpCodes": {code: 100.0 for code in diagnoses},
            "scpCodeDetails": [
                {"code": code, "probability": 100.0, "description": code_description(code)}
                for code in diagnoses
            ],
            "isPure": not concomitant,
            "concomitantCodes": concomitant,
        },
        "validation": {
            "validatedByHuman": None,
            "secondOpinion": None,
            "validatedBy": None,
            "stratFold": None,
            "selectionReview": (
                "Código SNOMED CT oficial del conjunto de datos; candidato pendiente de "
                "revisión morfológica por el proyecto EKG."
            ),
        },
        "quality": {
            "baselineDrift": None,
            "staticNoise": None,
            "burstNoise": None,
            "electrodeProblems": None,
            "extraBeats": None,
            "pacemaker": None,
        },
        "samplingValidation": sampling_validation,
        "allDatasetFields": {
            "recordId": candidate["recordId"],
            "diagnoses": diagnoses,
            "rx": candidate["rx"],
            "history": candidate["history"],
            "symptoms": candidate["symptoms"],
        },
        "filename_lr": None,
        "filename_hr": candidate["member"].replace(".hea", ".mat"),
        "files": {},
    }


def build_educational(rhythm_id: str, candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "rhythmId": rhythm_id,
        "status": "candidate",
        "diagnosis": TARGET_DIAGNOSIS,
        "reviewStatus": "pending_review",
        "note": (
            "Registro etiquetado con taquicardia ventricular en G12EC. La etiqueta del conjunto "
            "de datos no sustituye la revisión del trazado antes de incorporarlo al banco estable."
        ),
        "findings": [
            {"label": "Código diagnóstico de origen: SNOMED CT 164895002."},
            {"label": "Verificar frecuencia, regularidad, anchura y morfología del QRS en las 12 derivaciones."},
            {"label": "Buscar disociación AV, latidos de captura o de fusión cuando sean visibles."},
            {"label": "En una taquicardia de QRS ancho, la conducta segura es asumir origen ventricular hasta demostrar lo contrario."},
        ],
        "questions": [
            {
                "question": "¿Qué hallazgos apoyan origen ventricular frente a taquicardia supraventricular con aberrancia?",
                "answer": "Disociación AV, captura o fusión, concordancia precordial y criterios morfológicos compatibles con TV."
            },
            {
                "question": "¿Cuál es la primera clasificación clínica necesaria?",
                "answer": "Determinar si existe pulso y si el paciente está hemodinámicamente estable."
            }
        ],
        "source": {
            "dataset": "Georgia 12-Lead ECG Challenge Database",
            "recordId": candidate["recordId"],
            "snomedCtCode": TARGET_SNOMED,
        },
    }


def clean_previous_candidates() -> None:
    for folder in RHYTHMS.glob("vt_e*"):
        if folder.is_dir():
            shutil.rmtree(folder)


def main() -> None:
    ensure_pruebas_branch()
    download_archive()
    clean_previous_candidates()

    sys.path.insert(0, str(ROOT / "tools"))
    from build_ecg_bank import compare_leads, write_embedded_viewer_data

    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    catalog = [
        item for item in catalog
        if not (item.get("targetCode") == TARGET_CODE and item.get("status") == "candidate")
    ]

    manifest_candidates: list[dict[str, Any]] = []
    with tarfile.open(ARCHIVE, mode="r:gz") as archive:
        selected = discover_candidates(archive)
        total = len(selected)
        for index, candidate in enumerate(selected, start=1):
            record_id = candidate["recordId"]
            rhythm_id = f"vt_{record_id.lower()}"
            title = f"{TARGET_DIAGNOSIS} · {record_id}"
            print(f"[{index:02d}/{total:02d}] {title}")

            leads500 = physical_signals(archive, candidate)
            leads100 = resample_to_100hz(leads500)
            folder = RHYTHMS / rhythm_id
            folder.mkdir(parents=True, exist_ok=True)

            write_json(
                folder / "signal_500hz.json",
                signal_payload(rhythm_id, title, candidate, leads500, 500, derived=False),
                compact=True,
            )
            signal100 = signal_payload(rhythm_id, title, candidate, leads100, 100, derived=True)
            write_json(folder / "signal_100hz.json", signal100, compact=True)
            write_json(folder / "signal.json", signal100, compact=True)

            sampling_validation = compare_leads(leads100, leads500)
            write_json(
                folder / "metadata.json",
                build_metadata(rhythm_id, title, candidate, sampling_validation),
            )
            write_json(folder / "educational.json", build_educational(rhythm_id, candidate))

            candidate_document = {
                "id": rhythm_id,
                "sourceRecordId": record_id,
                "title": title,
                "targetCode": TARGET_CODE,
                "snomedCtCode": TARGET_SNOMED,
                "diagnoses": candidate["diagnoses"],
                "sourceHeaderMember": candidate["member"],
                "status": "pending_review",
            }
            write_json(folder / "candidate.json", candidate_document)
            manifest_candidates.append(candidate_document)

            numeric_record = int(re.sub(r"\D", "", record_id) or 0)
            catalog.append(
                {
                    "id": rhythm_id,
                    "title": f"[PRUEBA] {title}",
                    "targetCode": TARGET_CODE,
                    "snomedCtCode": TARGET_SNOMED,
                    "ecgId": numeric_record,
                    "sourceRecordId": record_id,
                    "sampleRateHz": 100,
                    "durationSeconds": 10.0,
                    "path": f"rhythms/{rhythm_id}/signal.json",
                    "status": "candidate",
                }
            )

    manifest = {
        "schemaVersion": "1.0",
        "dataset": {
            "name": "Georgia 12-Lead ECG Challenge Database",
            "shortName": "G12EC",
            "challenge": "PhysioNet/Computing in Cardiology Challenge 2020",
            "version": "1.0.2",
            "license": "CC BY 4.0",
        },
        "targetCode": TARGET_CODE,
        "snomedCtCode": TARGET_SNOMED,
        "diagnosis": TARGET_DIAGNOSIS,
        "selectionRule": (
            "Primeros 20 registros ordenados por ID con 12 derivaciones, 500 Hz, 5000 muestras "
            "y código SNOMED CT 164895002 en el encabezado WFDB."
        ),
        "candidates": manifest_candidates,
    }
    write_json(MANIFEST, manifest)
    write_json(CATALOG, catalog)

    with CATALOG_CSV.open("w", encoding="utf-8", newline="") as handle:
        fields = [
            "id", "title", "targetCode", "snomedCtCode", "ecgId", "sourceRecordId",
            "sampleRateHz", "durationSeconds", "path", "status",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(catalog)

    write_embedded_viewer_data()
    print(f"Listo: {len(manifest_candidates)} candidatos de taquicardia ventricular incorporados a pruebas.")


if __name__ == "__main__":
    main()
