from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BANK = ROOT / "output" / "ECG_BANCO_INICIAL_REAL"
RHYTHMS = BANK / "rhythms"
CATALOG = BANK / "catalog" / "rhythms_catalog.json"
CATALOG_CSV = BANK / "catalog" / "rhythms_catalog.csv"
MANIFEST = BANK / "candidates" / "sca_candidates.json"
CACHE = ROOT / ".cache"

MI_LOCALIZATION_CODES = {
    "AMI", "ASMI", "ALMI", "IMI", "ILMI", "IPMI", "IPLMI", "LMI", "PMI"
}
SUBENDOCARDIAL_INJURY_CODES = {"INJAS", "INJAL", "INJIN", "INJLA", "INJIL"}
ACUTE_STAGES = {"stadium i", "stadium i-ii"}
HARD_EXCLUSIONS = {"PACE", "WPW"}
NSTEMI_EXCLUSIONS = HARD_EXCLUSIONS | {"STE_", "CLBBB"}


def dump(path: Path, value: Any, compact: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        if compact
        else json.dumps(value, ensure_ascii=False, indent=2)
    )
    path.write_text(text + "\n", encoding="utf-8")


def normalize_stage(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().replace("–", "-").split())


def stages_for(row: dict[str, str]) -> set[str]:
    return {
        stage
        for stage in (
            normalize_stage(row.get("infarction_stadium1")),
            normalize_stage(row.get("infarction_stadium2")),
        )
        if stage
    }


def row_quality_penalty(row: dict[str, str], has_text) -> float:
    penalty = 0.0
    for field in ("baseline_drift", "static_noise", "burst_noise", "electrodes_problems"):
        if has_text(row.get(field)):
            penalty += 18.0
    if has_text(row.get("pacemaker")):
        penalty += 30.0
    if has_text(row.get("extra_beats")):
        penalty += 5.0
    return penalty


def classify_candidate(row: dict[str, str], parse_codes) -> tuple[str | None, dict[str, Any]]:
    code_map = parse_codes(row.get("scp_codes", ""))
    codes = set(code_map)
    stages = stages_for(row)
    has_mi_localization = bool(codes & MI_LOCALIZATION_CODES)
    has_subendocardial_injury = bool(codes & SUBENDOCARDIAL_INJURY_CODES)
    has_acute_stage = bool(stages & ACUTE_STAGES)
    has_st_elevation = "STE_" in codes

    evidence = {
        "scpCodes": sorted(codes),
        "infarctionStages": sorted(stages),
        "hasMiLocalizationCode": has_mi_localization,
        "hasSubendocardialInjuryCode": has_subendocardial_injury,
        "hasAcuteInfarctionStage": has_acute_stage,
        "hasNonSpecificStElevationCode": has_st_elevation,
    }

    if not (codes & HARD_EXCLUSIONS) and has_mi_localization and (has_acute_stage or has_st_elevation):
        if not has_subendocardial_injury:
            return "stemi", evidence

    if has_subendocardial_injury and not (codes & NSTEMI_EXCLUSIONS):
        return "nstemi", evidence

    return None, evidence


def score_candidate(row: dict[str, str], group: str, evidence: dict[str, Any], truthy, has_text, parse_codes) -> float:
    codes = parse_codes(row.get("scp_codes", ""))
    score = 0.0
    if truthy(row.get("validated_by_human")):
        score += 24.0
    if truthy(row.get("second_opinion")):
        score += 10.0
    try:
        fold = int(float(row.get("strat_fold", "0") or 0))
    except ValueError:
        fold = 0
    if fold in {9, 10}:
        score += 8.0
    elif fold in {7, 8}:
        score += 3.0

    score -= row_quality_penalty(row, has_text)
    score += max((codes.get(code, 0.0) for code in MI_LOCALIZATION_CODES), default=0.0) * 0.05

    if group == "stemi":
        if evidence["hasAcuteInfarctionStage"]:
            score += 14.0
        if evidence["hasNonSpecificStElevationCode"]:
            score += 6.0
    else:
        score += max((codes.get(code, 0.0) for code in SUBENDOCARDIAL_INJURY_CODES), default=0.0) * 0.08

    report = str(row.get("report") or "").lower()
    if group == "stemi" and any(term in report for term in ("acute", "akut", "st elevation", "st-hebung")):
        score += 5.0
    if group == "nstemi" and any(term in report for term in ("subendocard", "subendokard", "st depression", "st-senkung")):
        score += 5.0
    return score


def choose_candidates(rows: list[dict[str, str]], per_group: int, helpers: dict[str, Any]) -> dict[str, list[tuple[float, dict[str, str], dict[str, Any]]]]:
    ranked: dict[str, list[tuple[float, dict[str, str], dict[str, Any]]]] = {"stemi": [], "nstemi": []}
    for row in rows:
        group, evidence = classify_candidate(row, helpers["parse_codes"])
        if group is None:
            continue
        score = score_candidate(
            row,
            group,
            evidence,
            helpers["truthy"],
            helpers["has_text"],
            helpers["parse_codes"],
        )
        ranked[group].append((score, row, evidence))

    selected: dict[str, list[tuple[float, dict[str, str], dict[str, Any]]]] = {"stemi": [], "nstemi": []}
    used_ecg_ids: set[str] = set()
    used_patient_ids: set[str] = set()
    for group in ("stemi", "nstemi"):
        for score, row, evidence in sorted(
            ranked[group], key=lambda item: (item[0], item[1].get("ecg_id", "")), reverse=True
        ):
            ecg_id = str(row.get("ecg_id") or "")
            patient_id = str(row.get("patient_id") or "")
            if not ecg_id or ecg_id in used_ecg_ids or (patient_id and patient_id in used_patient_ids):
                continue
            selected[group].append((score, row, evidence))
            used_ecg_ids.add(ecg_id)
            if patient_id:
                used_patient_ids.add(patient_id)
            if len(selected[group]) >= per_group:
                break
        if len(selected[group]) < per_group:
            raise RuntimeError(
                f"Solo se encontraron {len(selected[group])} candidatos elegibles para {group}; se solicitaron {per_group}."
            )
    return selected


def code_details(codes: dict[str, float], scp_dictionary: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    details = []
    for code, probability in codes.items():
        item = scp_dictionary.get(code, {})
        details.append(
            {
                "code": code,
                "probability": probability,
                "description": item.get("description"),
                "diagnostic": item.get("diagnostic"),
                "rhythm": item.get("rhythm"),
                "form": item.get("form"),
                "diagnosticClass": item.get("diagnostic_class"),
                "diagnosticSubclass": item.get("diagnostic_subclass"),
            }
        )
    return details


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Añade candidatos STEMI y NSTEMI al banco de la rama pruebas sin diagnosticar SCA desde el ECG aislado."
    )
    parser.add_argument("--per-group", type=int, default=5, choices=range(1, 11))
    args = parser.parse_args()

    branch = subprocess.check_output(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=ROOT, text=True
    ).strip()
    if branch != "pruebas":
        raise RuntimeError(f"Solo puede ejecutarse en pruebas; rama actual: {branch}")

    sys.path.insert(0, str(ROOT / "tools"))
    from build_ecg_bank import (
        BASE,
        clean,
        compare_leads,
        download,
        has_text,
        load_scp_dictionary,
        parse_codes,
        prepare_wfdb_record,
        read_record,
        sha256,
        truthy,
        write_embedded_viewer_data,
        write_signal,
    )

    if not CATALOG.exists():
        raise RuntimeError("No existe el catálogo base. Construye primero el banco ECG.")

    CACHE.mkdir(parents=True, exist_ok=True)
    db_path = CACHE / "ptbxl_database.csv"
    scp_path = CACHE / "scp_statements.csv"
    download(f"{BASE}/ptbxl_database.csv", db_path)
    download(f"{BASE}/scp_statements.csv", scp_path)

    with db_path.open("r", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    scp_dictionary = load_scp_dictionary(scp_path)
    selected = choose_candidates(
        rows,
        args.per_group,
        {"parse_codes": parse_codes, "truthy": truthy, "has_text": has_text},
    )

    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    catalog = [
        item
        for item in catalog
        if not str(item.get("id", "")).startswith(("stemi_", "nstemi_"))
    ]
    for pattern in ("stemi_*", "nstemi_*"):
        for folder in RHYTHMS.glob(pattern):
            if folder.is_dir():
                shutil.rmtree(folder)

    candidates: list[dict[str, Any]] = []
    for group in ("stemi", "nstemi"):
        for score, row, evidence in selected[group]:
            ecg_id = int(float(row["ecg_id"]))
            slug = f"{group}_ecg_{ecg_id:05d}"
            diagnosis = "STEMI" if group == "stemi" else "NSTEMI (patrón ECG compatible)"
            title = f"{diagnosis} · ECG {ecg_id}"
            folder = RHYTHMS / slug
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
            validation = compare_leads(lr_leads, hr_leads)
            target_code = "SCA_STEMI" if group == "stemi" else "SCA_NSTEMI"
            limitation = (
                "Candidato con patrón compatible con STEMI. Debe confirmarse mediante revisión clínica humana; "
                "el ECG aislado no sustituye la evaluación del síndrome coronario agudo."
                if group == "stemi"
                else "Candidato con lesión/isquemia subendocárdica compatible. NSTEMI no puede confirmarse con ECG aislado: "
                "requiere síntomas, troponina con dinámica y exclusión de elevación persistente del ST."
            )
            metadata = {
                "id": slug,
                "title": title,
                "targetCode": target_code,
                "ecgId": ecg_id,
                "candidateStatus": "pending_review",
                "status": "pending_review",
                "classificationScope": "ECG pattern candidate; not a standalone clinical diagnosis",
                "classificationEvidence": evidence,
                "selectionScore": round(score, 2),
                "patient": {
                    "patientId": clean(row.get("patient_id")),
                    "age": clean(row.get("age")),
                    "sex": clean(row.get("sex")),
                    "height": clean(row.get("height")),
                    "weight": clean(row.get("weight")),
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
                    "scpCodeDetails": code_details(codes, scp_dictionary),
                    "isPure": False,
                    "concomitantCodes": sorted(set(codes) - MI_LOCALIZATION_CODES - SUBENDOCARDIAL_INJURY_CODES),
                },
                "validation": {
                    "validatedByHuman": truthy(row.get("validated_by_human")),
                    "secondOpinion": truthy(row.get("second_opinion")),
                    "validatedBy": clean(row.get("validated_by")),
                    "stratFold": clean(row.get("strat_fold")),
                    "selectionReview": limitation,
                },
                "quality": {
                    "baselineDrift": clean(row.get("baseline_drift")),
                    "staticNoise": clean(row.get("static_noise")),
                    "burstNoise": clean(row.get("burst_noise")),
                    "electrodeProblems": clean(row.get("electrodes_problems")),
                    "extraBeats": clean(row.get("extra_beats")),
                    "pacemaker": clean(row.get("pacemaker")),
                },
                "samplingValidation": validation,
                "source": {"dataset": "PTB-XL", "version": "1.0.3"},
                "files": {
                    "signal100Sha256": sha256(folder / "signal_100hz.json"),
                    "signal500Sha256": sha256(folder / "signal_500hz.json"),
                },
            }
            dump(folder / "metadata.json", metadata)
            findings = (
                [
                    {"label": "Confirmar elevación del ST en derivaciones contiguas y cambios recíprocos."},
                    {"label": "Definir territorio y descartar imitadores antes de aprobar."},
                ]
                if group == "stemi"
                else [
                    {"label": "Buscar depresión del ST y/o inversión dinámica de T en derivaciones contiguas."},
                    {"label": "No aprobar como NSTEMI sin correlación con troponina y clínica."},
                ]
            )
            dump(
                folder / "educational.json",
                {
                    "rhythmId": slug,
                    "status": "candidate",
                    "diagnosis": diagnosis,
                    "reviewStatus": "pending_review",
                    "note": limitation,
                    "findings": findings,
                    "questions": [],
                },
            )
            candidate = {
                "id": slug,
                "group": group,
                "ecgId": ecg_id,
                "targetCode": target_code,
                "selectionScore": round(score, 2),
                "evidence": evidence,
                "status": "pending_review",
            }
            dump(folder / "candidate.json", candidate)
            candidates.append(candidate)
            catalog.append(
                {
                    "id": slug,
                    "title": f"[PRUEBA] {title}",
                    "targetCode": target_code,
                    "ecgId": ecg_id,
                    "sampleRateHz": lr_fs,
                    "durationSeconds": round(lr_n / lr_fs, 3),
                    "path": f"rhythms/{slug}/signal.json",
                    "status": "candidate",
                    "sourceDataset": "PTB-XL",
                }
            )

    dump(
        MANIFEST,
        {
            "schemaVersion": "1.0",
            "dataset": {"name": "PTB-XL", "version": "1.0.3"},
            "targets": {
                "stemi": {
                    "label": "STEMI",
                    "rule": "Código de localización de infarto + estadio agudo I/I-II o STE_; excluye lesión subendocárdica.",
                    "clinicalLimit": "Requiere revisión clínica humana y exclusión de imitadores.",
                },
                "nstemi": {
                    "label": "NSTEMI (patrón compatible)",
                    "rule": "Código INJ* de lesión subendocárdica sin STE_, marcapasos, WPW ni BRI completo.",
                    "clinicalLimit": "El ECG no confirma NSTEMI; requiere troponina dinámica y contexto clínico.",
                },
            },
            "selection": {
                "candidatesPerGroup": args.per_group,
                "manualWaveformEditing": False,
                "reviewRequired": True,
            },
            "candidates": candidates,
        },
    )
    dump(CATALOG, catalog)

    fields = [
        "id",
        "title",
        "targetCode",
        "snomedCtCode",
        "ecgId",
        "sourceRecordId",
        "sampleRateHz",
        "durationSeconds",
        "path",
        "status",
        "sourceDataset",
    ]
    with CATALOG_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(catalog)

    write_embedded_viewer_data()
    print(
        f"Listo: {len(selected['stemi'])} candidatos STEMI y {len(selected['nstemi'])} candidatos NSTEMI "
        "incorporados exclusivamente a pruebas."
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        raise
