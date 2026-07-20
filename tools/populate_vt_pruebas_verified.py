from __future__ import annotations

import csv, hashlib, io, json, re, shutil, subprocess, sys, time, urllib.error, urllib.request
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat
from scipy.signal import find_peaks, resample_poly

ROOT = Path(__file__).resolve().parents[1]
BANK = ROOT / "output" / "ECG_BANCO_INICIAL_REAL"
RHYTHMS = BANK / "rhythms"
CATALOG = BANK / "catalog" / "rhythms_catalog.json"
CATALOG_CSV = BANK / "catalog" / "rhythms_catalog.csv"
MANIFEST = BANK / "candidates" / "ventricular_tachycardia_candidates.json"
BASE = "https://physionet.org/files/challenge-2020/1.0.2/training"
SNOMED = "164895002"
LEADS = ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]
RECORDS = [
    ("cpsc_2018_extra", "g2", "Q1083"),
    ("ptb", "g1", "S0316"), ("ptb", "g1", "S0354"),
    ("ptb", "g1", "S0361"), ("ptb", "g1", "S0410"),
    ("ptb", "g1", "S0425"), ("ptb", "g1", "S0426"),
    ("ptb", "g1", "S0501"), ("ptb", "g1", "S0530"),
    ("ptb", "g1", "S0533"), ("ptb", "g1", "S0541"),
]


def get(url: str, attempts: int = 4) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "EKG-PROYECT-vt/3.0"})
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=240) as response:
                return response.read()
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            last = exc
            time.sleep(attempt + 1)
    raise RuntimeError(f"No se pudo descargar {url}: {last}")


def dump(path: Path, value: Any, compact: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":")) if compact else json.dumps(value, ensure_ascii=False, indent=2)
    path.write_text(text + "\n", encoding="utf-8")


def hvalue(lines: list[str], key: str) -> str | None:
    for prefix in (f"#{key}:", f"# {key}:"):
        for line in lines:
            if line.startswith(prefix):
                value = line[len(prefix):].strip()
                return None if value.lower() in {"", "unknown", "nan", "none"} else value
    return None


def parse_header(text: str, dataset: str, group: str, record: str) -> dict[str, Any]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    first = lines[0].split()
    if len(first) < 4 or first[0] != record or int(first[1]) != 12:
        raise RuntimeError(f"Cabecera no válida para {record}")
    fs, samples = int(round(float(first[2]))), int(first[3])
    channels = {}
    for line in lines[1:13]:
        parts = line.split()
        lead = next((x for x in LEADS if x.upper() == parts[-1].upper()), None)
        match = re.match(r"([-+0-9.eE]+)(?:\(([-+0-9.eE]+)\))?/([^\s]+)", parts[2])
        if lead is None or match is None:
            raise RuntimeError(f"{record}: línea de derivación no válida")
        channels[lead] = {
            "gain": float(match.group(1)),
            "baseline": float(match.group(2)) if match.group(2) else float(parts[4]),
            "unit": match.group(3),
        }
    if set(channels) != set(LEADS):
        raise RuntimeError(f"{record}: faltan derivaciones")
    diagnoses = [x.strip().removesuffix(".0") for x in (hvalue(lines, "Dx") or "").split(",") if x.strip()]
    if SNOMED not in diagnoses:
        raise RuntimeError(f"{record}: no contiene SNOMED CT {SNOMED}")
    base = f"{BASE}/{dataset}/{group}/{record}"
    return {
        "dataset": dataset, "group": group, "record": record, "fs": fs,
        "samples": samples, "channels": [channels[x] for x in LEADS],
        "diagnoses": diagnoses, "age": hvalue(lines, "Age"), "sex": hvalue(lines, "Sex"),
        "hea": base + ".hea", "mat": base + ".mat", "headerText": text,
    }


def physical(payload: bytes, header: dict[str, Any]) -> np.ndarray:
    matrix = np.asarray(loadmat(io.BytesIO(payload))["val"], dtype=float)
    if matrix.shape == (header["samples"], 12):
        matrix = matrix.T
    if matrix.shape != (12, header["samples"]):
        raise RuntimeError(f"{header['record']}: forma inesperada {matrix.shape}")
    for index, channel in enumerate(header["channels"]):
        if channel["unit"].lower() != "mv" or channel["gain"] == 0:
            raise RuntimeError(f"{header['record']}: ganancia/unidad no compatible")
        matrix[index] = (matrix[index] - channel["baseline"]) / channel["gain"]
    return matrix


def rate_score(values: np.ndarray, fs: int) -> tuple[float, float]:
    values = values - np.median(values)
    envelope = np.abs(values)
    prominence = max(float(np.percentile(envelope, 80)) * .45, float(np.std(values)) * .35, 1e-6)
    peaks, _ = find_peaks(envelope, distance=max(1, int(.20 * fs)), prominence=prominence)
    if len(peaks) < 2:
        return -1e6, 0.0
    rr = np.diff(peaks) / fs
    rate = float(60 / np.median(rr))
    return min(rate, 300) + 2 * len(peaks) - 20 * float(np.std(rr) / max(np.mean(rr), 1e-9)), rate


def review_window(signal: np.ndarray, fs: int) -> tuple[np.ndarray, dict[str, Any]]:
    length = min(signal.shape[1], 10 * fs)
    if signal.shape[1] <= length:
        return signal.copy(), {"startSeconds": 0.0, "endSeconds": round(signal.shape[1] / fs, 3), "method": "registro completo", "estimatedRateBpm": None}
    best = None
    lead_ids = [LEADS.index("II"), LEADS.index("V1"), LEADS.index("V5")]
    for start in range(0, signal.shape[1] - length + 1, fs):
        pairs = [rate_score(signal[i, start:start + length], fs) for i in lead_ids]
        candidate = (sum(x[0] for x in pairs), start, float(np.median([x[1] for x in pairs])))
        if best is None or candidate[0] > best[0]:
            best = candidate
    assert best is not None
    _, start, rate = best
    return signal[:, start:start + length].copy(), {
        "startSeconds": round(start / fs, 3), "endSeconds": round((start + length) / fs, 3),
        "method": "ventana técnica de 10 s con mayor actividad QRS en II, V1 y V5; requiere revisión visual",
        "estimatedRateBpm": round(rate, 1),
    }


def resample(signal: np.ndarray, source: int, target: int) -> np.ndarray:
    if source == target:
        return signal.copy()
    divisor = int(np.gcd(source, target))
    return resample_poly(signal, target // divisor, source // divisor, axis=1, padtype="line")


def lead_dict(signal: np.ndarray) -> dict[str, list[float]]:
    return {lead: np.round(signal[i], 6).tolist() for i, lead in enumerate(LEADS)}


def signal_doc(rhythm: str, title: str, header: dict[str, Any], signal: np.ndarray, fs: int, segment: dict[str, Any], mat_sha: str) -> dict[str, Any]:
    return {
        "schemaVersion": "1.1", "id": rhythm, "title": title,
        "source": {
            "dataset": "PhysioNet/CinC Challenge 2020", "subset": header["dataset"], "version": "1.0.2",
            "recordId": header["record"], "headerUrl": header["hea"], "matUrl": header["mat"],
            "matSha256": mat_sha, "sourceSampleRateHz": header["fs"], "diagnosisCodes": header["diagnoses"],
            "diagnosisSystem": "SNOMED CT", "license": "CC BY 4.0", "segment": segment,
            "processing": "ADC→mV; recorte temporal documentado; remuestreo polifásico cuando corresponde",
        },
        "sampleRateHz": fs, "durationSeconds": round(signal.shape[1] / fs, 3), "samplesPerLead": int(signal.shape[1]),
        "units": "mV", "leadOrder": LEADS, "leads": lead_dict(signal),
    }


def main() -> int:
    branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=ROOT, text=True).strip()
    if branch != "pruebas":
        raise RuntimeError(f"Solo puede ejecutarse en pruebas; rama actual: {branch}")
    sys.path.insert(0, str(ROOT / "tools"))
    from build_ecg_bank import compare_leads, write_embedded_viewer_data

    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    catalog = [x for x in catalog if not str(x.get("id", "")).startswith("vt_")]
    for folder in RHYTHMS.glob("vt_*"):
        if folder.is_dir(): shutil.rmtree(folder)
    candidates = []

    for n, (dataset, group, record) in enumerate(RECORDS, 1):
        print(f"[{n:02d}/{len(RECORDS):02d}] {record}")
        base = f"{BASE}/{dataset}/{group}/{record}"
        header_text = get(base + ".hea").decode("utf-8", errors="replace")
        header = parse_header(header_text, dataset, group, record)
        mat = get(base + ".mat"); mat_sha = hashlib.sha256(mat).hexdigest()
        source = physical(mat, header); segment_signal, segment = review_window(source, header["fs"])
        s500, s100 = resample(segment_signal, header["fs"], 500), resample(segment_signal, header["fs"], 100)
        rhythm, title = f"vt_{record.lower()}", f"Taquicardia ventricular · {record}"
        folder = RHYTHMS / rhythm; folder.mkdir(parents=True, exist_ok=True)
        dump(folder / "signal_500hz.json", signal_doc(rhythm, title, header, s500, 500, segment, mat_sha), True)
        doc100 = signal_doc(rhythm, title, header, s100, 100, segment, mat_sha)
        dump(folder / "signal_100hz.json", doc100, True); dump(folder / "signal.json", doc100, True)
        (folder / "source_header.hea").write_text(header_text, encoding="utf-8")
        concomitant = [x for x in header["diagnoses"] if x != SNOMED]
        validation = compare_leads(lead_dict(s100), lead_dict(s500))
        metadata = {
            "id": rhythm, "title": title, "targetCode": "VT", "snomedCtCode": SNOMED,
            "ecgId": int(re.sub(r"\D", "", record) or 0), "sourceRecordId": record,
            "candidateStatus": "pending_review", "status": "pending_review",
            "patient": {"patientId": record, "age": header["age"], "sex": header["sex"], "height": None, "weight": None},
            "acquisition": {"recordingDate": None, "device": None, "site": dataset, "nurse": None},
            "report": {"original": "SNOMED CT: " + ", ".join(header["diagnoses"]), "initialAutogenerated": None, "heartAxis": None,
                "infarctionStadium1": None, "infarctionStadium2": None, "scpCodes": {x: 100.0 for x in header["diagnoses"]},
                "scpCodeDetails": [{"code": x, "probability": 100.0, "description": "Taquicardia ventricular" if x == SNOMED else "Diagnóstico concomitante SNOMED CT"} for x in header["diagnoses"]],
                "isPure": not concomitant, "concomitantCodes": concomitant},
            "validation": {"validatedByHuman": False, "secondOpinion": False, "validatedBy": None, "stratFold": None,
                "selectionReview": "Etiqueta del conjunto fuente y ventana técnica; pendiente de revisión morfológica humana."},
            "quality": {"baselineDrift": None, "staticNoise": None, "burstNoise": None, "electrodeProblems": None, "extraBeats": None, "pacemaker": None},
            "samplingValidation": validation,
            "source": {"dataset": "PhysioNet/CinC Challenge 2020", "subset": dataset, "headerUrl": header["hea"], "matUrl": header["mat"],
                "matSha256": mat_sha, "sourceSampleRateHz": header["fs"], "sourceDurationSeconds": round(header["samples"] / header["fs"], 3),
                "segment": segment, "license": "CC BY 4.0"},
            "files": {},
        }
        dump(folder / "metadata.json", metadata)
        dump(folder / "educational.json", {"rhythmId": rhythm, "status": "candidate", "diagnosis": "Taquicardia ventricular",
            "reviewStatus": "pending_review", "note": "Confirmar visualmente a 500 Hz; no asignar subtipo sin revisión humana.",
            "findings": [{"label": "Buscar QRS ancho, disociación AV, capturas y fusiones."}], "questions": []})
        candidate = {"id": rhythm, "sourceRecordId": record, "sourceSubset": dataset, "snomedCtCode": SNOMED,
            "diagnoses": header["diagnoses"], "reviewSegment": segment, "status": "pending_review"}
        dump(folder / "candidate.json", candidate); candidates.append(candidate)
        catalog.append({"id": rhythm, "title": f"[PRUEBA] {title}", "targetCode": "VT", "snomedCtCode": SNOMED,
            "ecgId": int(re.sub(r"\D", "", record) or 0), "sourceRecordId": record, "sampleRateHz": 100,
            "durationSeconds": round(s100.shape[1] / 100, 3), "path": f"rhythms/{rhythm}/signal.json", "status": "candidate", "sourceDataset": dataset})

    dump(MANIFEST, {"schemaVersion": "1.1", "dataset": {"name": "PhysioNet/CinC Challenge 2020", "version": "1.0.2", "license": "CC BY 4.0"},
        "target": {"diagnosis": "Taquicardia ventricular", "snomedCtCode": SNOMED},
        "selection": {"records": [x[2] for x in RECORDS], "windowSeconds": 10, "manualWaveformEditing": False, "reviewRequired": True},
        "candidates": candidates})
    dump(CATALOG, catalog)
    fields = ["id", "title", "targetCode", "snomedCtCode", "ecgId", "sourceRecordId", "sampleRateHz", "durationSeconds", "path", "status", "sourceDataset"]
    with CATALOG_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore"); writer.writeheader(); writer.writerows(catalog)
    write_embedded_viewer_data()
    print(f"Listo: {len(candidates)} candidatos VT incorporados exclusivamente a pruebas.")
    return 0


if __name__ == "__main__":
    try: raise SystemExit(main())
    except Exception as exc:
        print(f"\nERROR: {exc}", file=sys.stderr); raise
