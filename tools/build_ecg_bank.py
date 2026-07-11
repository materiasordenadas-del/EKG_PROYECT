from __future__ import annotations

import ast
import argparse
import csv
import hashlib
import json
import math
import shutil
import sys
import urllib.request
from pathlib import Path
from typing import Any

try:
    import numpy as np
    import wfdb
except ImportError as exc:
    raise SystemExit("Faltan dependencias. Ejecuta GENERAR_TODO_Y_ABRIR.bat.") from exc

BASE = "https://physionet.org/files/ptb-xl/1.0.3"
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "ECG_BANCO_INICIAL_REAL"
CACHE = ROOT / ".cache"

TARGETS = [
    ("sinus_rhythm", "Ritmo sinusal normal", "NORM", {"SR"}),
    ("sinus_bradycardia", "Bradicardia sinusal", "SBRAD", {"NORM", "SR"}),
    ("sinus_tachycardia", "Taquicardia sinusal", "STACH", {"NORM", "SR"}),
    ("atrial_fibrillation", "Fibrilación auricular", "AFIB", set()),
    ("atrial_flutter", "Flutter auricular", "AFLT", set()),
    ("first_degree_av_block", "Bloqueo AV de primer grado", "1AVB", {"SR", "LPR", "NORM"}),
    ("third_degree_av_block", "Bloqueo AV completo/de tercer grado", "3AVB", set()),
    ("ventricular_premature_beats", "Extrasístoles ventriculares", "PVC", {"SR", "NORM", "PRC(S)"}),
]

LEAD_CANON = {
    "I": "I", "II": "II", "III": "III", "AVR": "aVR", "AVL": "aVL", "AVF": "aVF",
    "V1": "V1", "V2": "V2", "V3": "V3", "V4": "V4", "V5": "V5", "V6": "V6",
}
LEAD_ORDER = ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]


def download(url: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > 0:
        return
    print(f"Descargando {url}")
    request = urllib.request.Request(url, headers={"User-Agent": "ECG-study-bank/1.1"})
    with urllib.request.urlopen(request, timeout=180) as source, path.open("wb") as target:
        shutil.copyfileobj(source, target)


def truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "1.0", "true", "yes"}


def clean(value: Any) -> Any:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return None
    return value


def has_text(value: Any) -> bool:
    value = clean(value)
    return value is not None and str(value).lower() not in {"false", "0", "0.0"}


def parse_codes(raw: str) -> dict[str, float]:
    try:
        data = ast.literal_eval(raw)
        return {str(k): float(v) for k, v in data.items()} if isinstance(data, dict) else {}
    except Exception:
        return {}


def load_scp_dictionary(path: Path) -> dict[str, dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        rows = csv.DictReader(handle)
        result = {}
        for row in rows:
            code = row.get("Unnamed: 0") or row.get("code") or ""
            if code:
                result[code] = {k: clean(v) for k, v in row.items() if k not in {"Unnamed: 0", "code"}}
        return result


def score_row(row: dict[str, str], target: str, allowed: set[str]) -> float:
    codes = parse_codes(row.get("scp_codes", ""))
    if target not in codes:
        return float("-inf")
    score = min(max(codes.get(target, 0), 0), 100) * 0.05
    if truthy(row.get("validated_by_human")): score += 12
    if truthy(row.get("second_opinion")): score += 5
    try: fold = int(float(row.get("strat_fold", "0") or 0))
    except ValueError: fold = 0
    if fold in {9, 10}: score += 8
    elif fold in {7, 8}: score += 2
    for field in ("baseline_drift", "static_noise", "burst_noise", "electrodes_problems"):
        if has_text(row.get(field)): score -= 12
    if has_text(row.get("pacemaker")): score -= 20
    extras = set(codes) - {target} - allowed
    score -= len(extras) * 12
    report = (row.get("report") or "").lower()
    words = {
        "NORM": ["normal ecg", "normales ekg"], "SBRAD": ["sinusbrady", "sinus brady"],
        "STACH": ["sinustachy", "sinus tachy"], "AFIB": ["atrial fibrillation", "vorhofflimmern", "förmaksflimmer"],
        "AFLT": ["atrial flutter", "vorhofflattern", "förmaksfladder"],
        "1AVB": ["first degree", "1.grades", "a-v block i", "av block i"],
        "3AVB": ["third degree", "complete av block", "av-block iii", "a-v block iii"],
        "PVC": ["premature ventricular", "ventrikuläre extrasyst", "ves"],
    }
    if any(word in report for word in words.get(target, [])): score += 8
    return score


def choose_records(rows: list[dict[str, str]]) -> list[tuple[str, str, str, set[str], dict[str, str], float]]:
    chosen = []
    used = set()
    for slug, title, code, allowed in TARGETS:
        candidates = sorted(
            [(score_row(row, code, allowed), row) for row in rows if score_row(row, code, allowed) != float("-inf")],
            key=lambda item: (item[0], item[1].get("ecg_id", "")), reverse=True,
        )
        selected = next(((score, row) for score, row in candidates if row.get("ecg_id") not in used), None)
        if selected is None: raise RuntimeError(f"No se encontró registro para {title} ({code}).")
        score, row = selected
        used.add(row["ecg_id"])
        chosen.append((slug, title, code, allowed, row, score))
        print(f"Seleccionado {title}: ECG {row['ecg_id']} (puntuación {score:.1f})")
    return chosen


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prepare_wfdb_record(base_rel: str, folder: Path, prefix: str) -> Path:
    remote_name = Path(base_rel).name
    local_base = folder / prefix
    hea = local_base.with_suffix(".hea")
    dat = local_base.with_suffix(".dat")
    download(f"{BASE}/{base_rel}.hea", hea)
    download(f"{BASE}/{base_rel}.dat", dat)
    header = hea.read_text(encoding="utf-8")
    header = header.replace(f"{remote_name}.dat", dat.name)
    first = header.splitlines()[0].split()
    first[0] = local_base.name
    lines = header.splitlines()
    lines[0] = " ".join(first)
    hea.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return local_base


def read_record(record_base: Path) -> tuple[dict[str, list[float]], int, int]:
    record = wfdb.rdrecord(str(record_base))
    if record.p_signal is None: raise RuntimeError(f"Sin señal física: {record_base}")
    leads = {}
    for index, name in enumerate(record.sig_name):
        canonical = LEAD_CANON.get(name.upper())
        if canonical:
            leads[canonical] = [round(float(value), 6) for value in record.p_signal[:, index]]
    missing = [lead for lead in LEAD_ORDER if lead not in leads]
    if missing: raise RuntimeError(f"Faltan derivaciones {missing} en {record_base}")
    return {lead: leads[lead] for lead in LEAD_ORDER}, int(round(float(record.fs))), int(record.sig_len)


def write_signal(path: Path, slug: str, title: str, row: dict[str, str], source_rel: str,
                 leads: dict[str, list[float]], fs: int, samples: int) -> None:
    signal = {
        "schemaVersion": "1.1", "id": slug, "title": title,
        "source": {"dataset": "PTB-XL", "version": "1.0.3", "ecgId": int(float(row["ecg_id"])), "record": source_rel},
        "sampleRateHz": fs, "durationSeconds": round(samples / fs, 6), "samplesPerLead": samples,
        "units": "mV", "leadOrder": LEAD_ORDER, "leads": leads,
    }
    path.write_text(json.dumps(signal, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def compare_leads(lr: dict[str, list[float]], hr: dict[str, list[float]]) -> dict[str, Any]:
    results = {}
    preserve_flags = []
    for lead in ("V2", "V3", "V4", "V5"):
        low = np.asarray(lr[lead], dtype=float)
        high = np.asarray(hr[lead], dtype=float)
        x_high = np.linspace(0, 1, high.size, endpoint=False)
        x_low = np.linspace(0, 1, low.size, endpoint=False)
        high_at_low = np.interp(x_low, x_high, high)
        corr = float(np.corrcoef(low, high_at_low)[0, 1]) if np.std(low) > 0 and np.std(high_at_low) > 0 else 1.0
        rmse = float(np.sqrt(np.mean((low - high_at_low) ** 2)))
        p2p_low = float(np.ptp(low)); p2p_high = float(np.ptp(high))
        amplitude_delta = abs(p2p_low - p2p_high) / max(p2p_high, 1e-9) * 100
        preserved = corr >= 0.98 and amplitude_delta <= 8
        preserve_flags.append(preserved)
        results[lead] = {
            "correlation100vs500": round(corr, 6), "rmseMv": round(rmse, 6),
            "min100Mv": round(float(np.min(low)), 6), "max100Mv": round(float(np.max(low)), 6),
            "min500Mv": round(float(np.min(high)), 6), "max500Mv": round(float(np.max(high)), 6),
            "peakToPeak100Mv": round(p2p_low, 6), "peakToPeak500Mv": round(p2p_high, 6),
            "peakToPeakDifferencePercent": round(amplitude_delta, 3), "morphologyPreserved": preserved,
        }
    conclusion = (
        "La morfología y amplitud de V2–V5 se conservan entre 100 y 500 Hz; las ondas llamativas proceden del registro, no del remuestreo."
        if all(preserve_flags) else
        "Existen diferencias relevantes entre 100 y 500 Hz en una o más precordiales; debe revisarse visualmente la versión de 500 Hz antes de concluir."
    )
    return {"leads": results, "allPrecordialsPreserved": all(preserve_flags), "conclusion": conclusion}


def install_viewer() -> None:
    template = ROOT / "template"
    destination = OUT / "viewer"
    if destination.exists(): shutil.rmtree(destination)
    shutil.copytree(template / "viewer", destination)
    shutil.copy2(template / "ABRIR_VISOR.bat", OUT / "ABRIR_VISOR.bat")
    shutil.copy2(template / "ABRIR_VISOR.html", OUT / "ABRIR_VISOR.html")


def write_embedded_viewer_data() -> None:
    """Crea los datos que permiten abrir el visor directamente desde un HTML."""
    catalog_path = OUT / "catalog" / "rhythms_catalog.json"
    if not catalog_path.exists():
        raise RuntimeError("No existe el catálogo del banco para preparar el visor autónomo.")
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    data: dict[str, Any] = {"catalog/rhythms_catalog.json": catalog}
    for item in catalog:
        rhythm_id = item["id"]
        base = OUT / "rhythms" / rhythm_id
        for filename in ("signal_100hz.json", "signal_500hz.json", "metadata.json", "educational.json"):
            path = base / filename
            if not path.exists():
                raise RuntimeError(f"Falta {path.relative_to(OUT)} para el visor autónomo.")
            data[f"rhythms/{rhythm_id}/{filename}"] = json.loads(path.read_text(encoding="utf-8"))
    viewer_data = OUT / "viewer" / "data.js"
    viewer_data.write_text(
        "window.ECG_BANK_DATA = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n",
        encoding="utf-8",
    )


def write_output_readme() -> None:
    (OUT / "README.md").write_text(
        "# Banco de ECG reales\n\n"
        "Abra `ABRIR_VISOR.html` con doble clic. Funciona sin Internet, sin descargas y sin servidor local.\n\n"
        "`ABRIR_VISOR.bat` sigue disponible como alternativa.\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Construye el banco local de ECG reales PTB-XL.")
    parser.add_argument(
        "--refresh-viewer-data", action="store_true",
        help="Actualiza solo el visor HTML autónomo del banco existente, sin descargar ni modificar señales.",
    )
    args = parser.parse_args()
    if args.refresh_viewer_data:
        install_viewer()
        write_embedded_viewer_data()
        write_output_readme()
        print(f"Visor HTML autónomo actualizado en: {OUT}")
        return 0

    CACHE.mkdir(parents=True, exist_ok=True)
    if OUT.exists(): shutil.rmtree(OUT)
    (OUT / "catalog").mkdir(parents=True)
    (OUT / "LICENSES").mkdir(parents=True)

    db_path = CACHE / "ptbxl_database.csv"
    scp_path = CACHE / "scp_statements.csv"
    license_path = CACHE / "LICENSE.txt"
    download(f"{BASE}/ptbxl_database.csv", db_path)
    download(f"{BASE}/scp_statements.csv", scp_path)
    download(f"{BASE}/LICENSE.txt", license_path)

    with db_path.open("r", encoding="utf-8") as handle: rows = list(csv.DictReader(handle))
    scp_dictionary = load_scp_dictionary(scp_path)
    chosen = choose_records(rows)
    shutil.copy2(scp_path, OUT / "catalog" / "scp_statements.csv")
    shutil.copy2(license_path, OUT / "LICENSES" / "LICENSE.txt")

    catalog = []
    for slug, title, target, allowed, row, score in chosen:
        folder = OUT / "rhythms" / slug
        folder.mkdir(parents=True, exist_ok=True)
        lr_rel, hr_rel = row["filename_lr"], row["filename_hr"]
        lr_base = prepare_wfdb_record(lr_rel, folder, "source_100hz")
        hr_base = prepare_wfdb_record(hr_rel, folder, "source_500hz")
        lr_leads, lr_fs, lr_n = read_record(lr_base)
        hr_leads, hr_fs, hr_n = read_record(hr_base)
        write_signal(folder / "signal_100hz.json", slug, title, row, lr_rel, lr_leads, lr_fs, lr_n)
        write_signal(folder / "signal_500hz.json", slug, title, row, hr_rel, hr_leads, hr_fs, hr_n)
        shutil.copy2(folder / "signal_100hz.json", folder / "signal.json")

        codes = parse_codes(row.get("scp_codes", ""))
        code_details = []
        for code, probability in codes.items():
            detail = scp_dictionary.get(code, {})
            code_details.append({
                "code": code, "probability": probability, "description": detail.get("description"),
                "diagnostic": detail.get("diagnostic"), "rhythm": detail.get("rhythm"),
                "form": detail.get("form"), "diagnosticClass": detail.get("diagnostic_class"),
                "diagnosticSubclass": detail.get("diagnostic_subclass"),
            })
        extras = sorted(set(codes) - {target} - allowed)
        comparison = compare_leads(lr_leads, hr_leads)
        (folder / "validation_100_vs_500.json").write_text(json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8")

        all_fields = {key: clean(value) for key, value in row.items()}
        metadata = {
            "id": slug, "title": title, "targetCode": target, "selectionScore": round(score, 2),
            "ecgId": int(float(row["ecg_id"])),
            "patient": {"patientId": clean(row.get("patient_id")), "age": clean(row.get("age")), "sex": clean(row.get("sex")), "height": clean(row.get("height")), "weight": clean(row.get("weight"))},
            "acquisition": {"recordingDate": clean(row.get("recording_date")), "device": clean(row.get("device")), "site": clean(row.get("site")), "nurse": clean(row.get("nurse"))},
            "report": {"original": clean(row.get("report")), "initialAutogenerated": clean(row.get("initial_autogenerated_report")), "heartAxis": clean(row.get("heart_axis")), "infarctionStadium1": clean(row.get("infarction_stadium1")), "infarctionStadium2": clean(row.get("infarction_stadium2")), "scpCodes": codes, "scpCodeDetails": code_details, "isPure": not extras, "concomitantCodes": extras},
            "validation": {"validatedByHuman": truthy(row.get("validated_by_human")), "secondOpinion": truthy(row.get("second_opinion")), "validatedBy": clean(row.get("validated_by")), "stratFold": clean(row.get("strat_fold")), "selectionReview": "preselección automática; requiere revisión visual antes de publicación"},
            "quality": {"baselineDrift": clean(row.get("baseline_drift")), "staticNoise": clean(row.get("static_noise")), "burstNoise": clean(row.get("burst_noise")), "electrodeProblems": clean(row.get("electrodes_problems")), "extraBeats": clean(row.get("extra_beats")), "pacemaker": clean(row.get("pacemaker"))},
            "samplingValidation": comparison,
            "allDatasetFields": all_fields,
            "files": {"signal100Sha256": sha256(folder / "signal_100hz.json"), "signal500Sha256": sha256(folder / "signal_500hz.json")},
        }
        (folder / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        educational = {"rhythmId": slug, "summary": "", "findings": [], "questions": [], "reviewed": False}
        (folder / "educational.json").write_text(json.dumps(educational, ensure_ascii=False, indent=2), encoding="utf-8")
        catalog.append({"id": slug, "title": title, "targetCode": target, "ecgId": metadata["ecgId"], "sampleRateHz": lr_fs, "durationSeconds": round(lr_n/lr_fs,2), "path": f"rhythms/{slug}/signal.json"})

    (OUT / "catalog" / "rhythms_catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    with (OUT / "catalog" / "rhythms_catalog.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(catalog[0].keys())); writer.writeheader(); writer.writerows(catalog)
    install_viewer()
    write_embedded_viewer_data()
    write_output_readme()
    print(f"\nBanco creado en: {OUT}")
    return 0


if __name__ == "__main__":
    try: raise SystemExit(main())
    except Exception as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        raise
