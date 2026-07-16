from __future__ import annotations

import ast
import csv
import io
import json
import subprocess
import sys
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Any

import wfdb

ROOT = Path(__file__).resolve().parents[1]
BANK = ROOT / "output" / "ECG_BANCO_INICIAL_REAL"
RHYTHMS = BANK / "rhythms"
MANIFEST = BANK / "candidates" / "afib_candidates.json"
CATALOG = BANK / "catalog" / "rhythms_catalog.json"
CATALOG_CSV = BANK / "catalog" / "rhythms_catalog.csv"
PTB_DIR = "ptb-xl/1.0.3"
METADATA_URL = "https://physionet.org/files/ptb-xl/1.0.3/ptbxl_database.csv"
LEADS = ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]
CANON = {name.upper(): name for name in LEADS}


def ensure_pruebas_branch() -> None:
    branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=ROOT, text=True).strip()
    if branch != "pruebas":
        raise RuntimeError(f"Este generador solo puede ejecutarse en la rama pruebas; rama actual: {branch}")


def candidate_title(ecg_id: int) -> str:
    return f"Fibrilación auricular · ECG {ecg_id}"


def clean(value: Any) -> Any:
    if value is None:
        return None
    text = str(value).strip()
    return None if not text or text.lower() in {"nan", "none", "null"} else value


def boolean(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "1.0", "true", "yes"}


def number(value: Any) -> float | None:
    value = clean(value)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def scp_codes(value: str) -> dict[str, float]:
    try:
        parsed = ast.literal_eval(value or "{}")
    except Exception:
        return {}
    result: dict[str, float] = {}
    if isinstance(parsed, dict):
        for key, raw in parsed.items():
            try:
                result[str(key)] = float(raw)
            except (TypeError, ValueError):
                pass
    return result


def load_metadata() -> dict[int, dict[str, str]]:
    request = urllib.request.Request(METADATA_URL, headers={"User-Agent": "EKG-PROYECT-pruebas/1.0"})
    with urllib.request.urlopen(request, timeout=180) as response:
        text = response.read().decode("utf-8")
    rows: dict[int, dict[str, str]] = {}
    for row in csv.DictReader(io.StringIO(text)):
        try:
            rows[int(row["ecg_id"])] = row
        except (KeyError, TypeError, ValueError):
            continue
    return rows


def read_signal(remote_record: str, rhythm_id: str, title: str, ecg_id: int) -> dict[str, Any]:
    remote = PurePosixPath(remote_record)
    record = wfdb.rdrecord(remote.name, pn_dir=f"{PTB_DIR}/{remote.parent.as_posix()}")
    if record.p_signal is None:
        raise RuntimeError(f"{remote_record} no contiene señal física")
    fs = int(round(float(record.fs)))
    samples = int(record.sig_len)
    leads: dict[str, list[float]] = {}
    for index, raw_name in enumerate(record.sig_name):
        canonical = CANON.get(str(raw_name).upper())
        if canonical:
            leads[canonical] = [round(float(value), 6) for value in record.p_signal[:, index]]
    missing = [lead for lead in LEADS if lead not in leads]
    if missing:
        raise RuntimeError(f"Faltan derivaciones {missing} en {remote_record}")
    expected_fs = 100 if "records100" in remote_record else 500
    if fs != expected_fs:
        raise RuntimeError(f"Frecuencia inválida en {remote_record}: {fs} Hz; se esperaban {expected_fs} Hz")
    expected_samples = expected_fs * 10
    if samples != expected_samples:
        raise RuntimeError(f"Duración inválida en {remote_record}: {samples} muestras; se esperaban {expected_samples}")
    return {
        "schemaVersion": "1.1",
        "id": rhythm_id,
        "title": title,
        "source": {"dataset": "PTB-XL", "version": "1.0.3", "ecgId": ecg_id, "record": remote_record},
        "sampleRateHz": fs,
        "durationSeconds": round(samples / fs, 6),
        "samplesPerLead": samples,
        "units": "mV",
        "leadOrder": LEADS,
        "leads": {lead: leads[lead] for lead in LEADS},
    }


def build_metadata(candidate: dict[str, Any], row: dict[str, str]) -> dict[str, Any]:
    codes = scp_codes(row.get("scp_codes", ""))
    concomitant = [code for code in codes if code != "AFIB"]
    return {
        "id": candidate["id"],
        "title": candidate["title"],
        "targetCode": "AFIB",
        "selectionScore": None,
        "ecgId": int(candidate["ecgId"]),
        "candidateStatus": "pending_review",
        "status": "pending_review",
        "candidateGroup": candidate.get("group"),
        "candidateSummary": candidate.get("summary"),
        "patient": {
            "patientId": clean(row.get("patient_id")),
            "age": number(row.get("age")),
            "sex": clean(row.get("sex")),
            "height": number(row.get("height")),
            "weight": number(row.get("weight")),
        },
        "acquisition": {
            "recordingDate": clean(row.get("recording_date")),
            "device": clean(row.get("device")),
            "site": clean(row.get("site")),
            "nurse": clean(row.get("nurse")),
        },
        "report": {
            "original": clean(row.get("report")),
            "initialAutogenerated": clean(row.get("initial_autogenerated_report")),
            "heartAxis": clean(row.get("heart_axis")),
            "infarctionStadium1": clean(row.get("infarction_stadium1")),
            "infarctionStadium2": clean(row.get("infarction_stadium2")),
            "scpCodes": codes,
            "scpCodeDetails": [{"code": code, "probability": probability, "description": None} for code, probability in codes.items()],
            "isPure": not concomitant,
            "concomitantCodes": concomitant,
        },
        "validation": {
            "validatedByHuman": boolean(row.get("validated_by_human")),
            "secondOpinion": boolean(row.get("second_opinion")),
            "validatedBy": clean(row.get("validated_by")),
            "stratFold": clean(row.get("strat_fold")),
            "selectionReview": "candidato en rama pruebas; requiere revisión visual antes de fusionar a main",
        },
        "quality": {
            "baselineDrift": clean(row.get("baseline_drift")),
            "staticNoise": clean(row.get("static_noise")),
            "burstNoise": clean(row.get("burst_noise")),
            "electrodeProblems": clean(row.get("electrodes_problems")),
            "extraBeats": clean(row.get("extra_beats")),
            "pacemaker": clean(row.get("pacemaker")),
        },
        "samplingValidation": {
            "leads": {},
            "allPrecordialsPreserved": None,
            "conclusion": "Candidato de prueba con señales oficiales PTB-XL a 100 y 500 Hz; pendiente de revisión visual.",
        },
        "allDatasetFields": {key: clean(value) for key, value in row.items()},
        "filename_lr": clean(row.get("filename_lr")),
        "filename_hr": clean(row.get("filename_hr")),
        "files": {},
    }


def write_json(path: Path, value: Any, compact: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if compact:
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    else:
        text = json.dumps(value, ensure_ascii=False, indent=2)
    path.write_text(text + "\n", encoding="utf-8")


def main() -> None:
    ensure_pruebas_branch()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    rows = load_metadata()
    candidate_ids = {str(candidate["id"]) for candidate in manifest["candidates"]}
    catalog = [item for item in catalog if item.get("id") not in candidate_ids]

    for index, candidate in enumerate(manifest["candidates"], start=1):
        rhythm_id = str(candidate["id"])
        ecg_id = int(candidate["ecgId"])
        row = rows.get(ecg_id)
        if row is None:
            raise RuntimeError(f"ECG {ecg_id} no encontrado en ptbxl_database.csv")
        folder = RHYTHMS / rhythm_id
        folder.mkdir(parents=True, exist_ok=True)
        print(f"[{index:02d}/20] {rhythm_id}")
        title = candidate_title(ecg_id)
        signal100 = read_signal(candidate["record100"], rhythm_id, title, ecg_id)
        signal500 = read_signal(candidate["record500"], rhythm_id, title, ecg_id)
        write_json(folder / "signal_100hz.json", signal100, compact=True)
        write_json(folder / "signal_500hz.json", signal500, compact=True)
        write_json(folder / "signal.json", signal100, compact=True)
        write_json(folder / "metadata.json", build_metadata(candidate, row))
        write_json(folder / "educational.json", {
            "rhythmId": rhythm_id,
            "status": "candidate",
            "diagnosis": "Fibrilación auricular",
            "reviewStatus": "pending_review",
            "note": "Candidato en rama pruebas. Requiere revisión visual antes de incorporarse a main.",
            "findings": [
                {"label": "Candidato de fibrilación auricular pendiente de revisión."},
                {"label": candidate.get("summary")},
            ],
            "questions": [],
        })
        write_json(folder / "candidate.json", candidate)
        catalog.append({
            "id": rhythm_id,
            "title": f"[PRUEBA] {title}",
            "targetCode": "AFIB",
            "ecgId": ecg_id,
            "sampleRateHz": 100,
            "durationSeconds": 10.0,
            "path": f"rhythms/{rhythm_id}/signal.json",
            "status": "candidate",
        })

    write_json(CATALOG, catalog)
    with CATALOG_CSV.open("w", encoding="utf-8", newline="") as handle:
        fields = ["id", "title", "targetCode", "ecgId", "sampleRateHz", "durationSeconds", "path", "status"]
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(catalog)
    sys.path.insert(0, str(ROOT / "tools"))
    from build_ecg_bank import write_embedded_viewer_data
    write_embedded_viewer_data()
    print(f"Listo: {len(manifest['candidates'])} candidatos incorporados al visor de pruebas.")


if __name__ == "__main__":
    main()
