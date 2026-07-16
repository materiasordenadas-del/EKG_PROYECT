from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import shutil
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

try:
    import wfdb
except ImportError as exc:
    raise SystemExit(
        "Falta la dependencia wfdb. Ejecuta GENERAR_PRUEBAS_AFIB.bat o "
        "python -m pip install -r requirements.txt."
    ) from exc

BASE = "https://physionet.org/files/ptb-xl/1.0.3"
ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "testing" / "catalog" / "afib_candidates.json"
REVIEW_STATE_PATH = ROOT / "testing" / "review" / "review_state.json"
CANDIDATES_ROOT = ROOT / "testing" / "candidates" / "atrial_fibrillation"
VIEWER_PATH = ROOT / "testing" / "ABRIR_REVISION.html"
CACHE = ROOT / ".cache"
DATABASE_CSV = CACHE / "ptbxl_database.csv"

LEAD_CANON = {
    "I": "I", "II": "II", "III": "III", "AVR": "aVR", "AVL": "aVL", "AVF": "aVF",
    "V1": "V1", "V2": "V2", "V3": "V3", "V4": "V4", "V5": "V5", "V6": "V6",
}
LEAD_ORDER = ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Descarga candidatos AFIB de PTB-XL para revisión local.")
    parser.add_argument("--force", action="store_true", help="Reconstruye archivos aunque ya existan.")
    parser.add_argument("--only", action="append", default=[], metavar="CANDIDATE_ID")
    parser.add_argument("--viewer-only", action="store_true", help="Solo reconstruye el HTML.")
    return parser.parse_args()


def download(url: str, path: Path, force: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > 0 and not force:
        return
    temporary = path.with_suffix(path.suffix + ".part")
    if temporary.exists():
        temporary.unlink()
    request = urllib.request.Request(url, headers={"User-Agent": "ECG-study-bank-testing/1.0"})
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            print(f"Descargando {url}")
            with urllib.request.urlopen(request, timeout=180) as source, temporary.open("wb") as target:
                shutil.copyfileobj(source, target)
            if temporary.stat().st_size <= 0:
                raise RuntimeError("La descarga quedó vacía.")
            temporary.replace(path)
            return
        except Exception as exc:
            last_error = exc
            if temporary.exists():
                temporary.unlink()
            if attempt < 3:
                time.sleep(attempt * 2)
    raise RuntimeError(f"No se pudo descargar {url}: {last_error}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def clean(value: Any) -> Any:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return None
    return value


def truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "1.0", "true", "yes"}


def parse_scp_codes(raw: str) -> dict[str, float]:
    try:
        parsed = ast.literal_eval(raw)
    except Exception:
        return {}
    if not isinstance(parsed, dict):
        return {}
    result: dict[str, float] = {}
    for key, value in parsed.items():
        try:
            result[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return result


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def load_database_rows(force: bool = False) -> dict[int, dict[str, str]]:
    download(f"{BASE}/ptbxl_database.csv", DATABASE_CSV, force=force)
    rows: dict[int, dict[str, str]] = {}
    with DATABASE_CSV.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                ecg_id = int(float(row.get("ecg_id", "")))
            except (TypeError, ValueError):
                continue
            rows[ecg_id] = row
    return rows


def patch_header(hea: Path, dat: Path, remote_record: str) -> None:
    remote_name = Path(remote_record).name
    lines = hea.read_text(encoding="utf-8").splitlines()
    if not lines:
        raise RuntimeError(f"Cabecera vacía: {hea}")
    first = lines[0].split()
    first[0] = hea.stem
    lines[0] = " ".join(first)
    lines = [line.replace(f"{remote_name}.dat", dat.name) for line in lines]
    hea.write_text("\n".join(lines) + "\n", encoding="utf-8")


def prepare_record(candidate: dict[str, Any], force: bool) -> tuple[Path, Path, Path]:
    candidate_id = str(candidate["candidateId"])
    remote_record = str(candidate["sourceRecord500Hz"])
    folder = CANDIDATES_ROOT / candidate_id
    folder.mkdir(parents=True, exist_ok=True)
    base = folder / "source_hr"
    hea = base.with_suffix(".hea")
    dat = base.with_suffix(".dat")
    download(f"{BASE}/{remote_record}.hea", hea, force=force)
    download(f"{BASE}/{remote_record}.dat", dat, force=force)
    patch_header(hea, dat, remote_record)
    return folder, base, dat


def read_record(record_base: Path) -> tuple[dict[str, list[float]], int, int]:
    record = wfdb.rdrecord(str(record_base))
    if record.p_signal is None:
        raise RuntimeError(f"El registro no contiene señal física: {record_base}")
    fs = int(round(float(record.fs)))
    samples = int(record.sig_len)
    leads: dict[str, list[float]] = {}
    for index, name in enumerate(record.sig_name):
        canonical = LEAD_CANON.get(str(name).upper())
        if canonical:
            leads[canonical] = [round(float(value), 6) for value in record.p_signal[:, index]]
    missing = [lead for lead in LEAD_ORDER if lead not in leads]
    if missing:
        raise RuntimeError(f"Faltan derivaciones {missing} en {record_base}")
    if fs != 500:
        raise RuntimeError(f"Se esperaban 500 Hz y se obtuvieron {fs} Hz en {record_base}")
    duration = samples / fs
    if not 9.9 <= duration <= 10.1:
        raise RuntimeError(f"Duración inesperada ({duration:.3f} s) en {record_base}")
    return {lead: leads[lead] for lead in LEAD_ORDER}, fs, samples


def safe_float(value: Any) -> float | None:
    value = clean(value)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_metadata(candidate: dict[str, Any], row: dict[str, str], dat: Path) -> dict[str, Any]:
    age = safe_float(row.get("age"))
    if age is not None and not 0 <= age <= 120:
        age = None
    sex_raw = clean(row.get("sex"))
    sex = {"0": "Masculino", "0.0": "Masculino", "1": "Femenino", "1.0": "Femenino"}.get(str(sex_raw), sex_raw)
    return {
        "schemaVersion": "1.0",
        "candidateId": candidate["candidateId"],
        "ecgId": int(candidate["ecgId"]),
        "group": candidate.get("group"),
        "summary": candidate.get("summary"),
        "dataset": {"name": "PTB-XL", "version": "1.0.3", "license": "CC BY 4.0"},
        "patient": {"patientId": clean(row.get("patient_id")), "age": age, "sex": sex, "heightCm": safe_float(row.get("height")), "weightKg": safe_float(row.get("weight"))},
        "acquisition": {"recordingDate": clean(row.get("recording_date")), "device": clean(row.get("device")), "site": clean(row.get("site")), "nurse": clean(row.get("nurse")), "sourceRecord500Hz": candidate.get("sourceRecord500Hz")},
        "report": {"original": clean(row.get("report")), "scpCodes": parse_scp_codes(row.get("scp_codes", "")), "heartAxis": clean(row.get("heart_axis")), "infarctionStadium1": clean(row.get("infarction_stadium1")), "infarctionStadium2": clean(row.get("infarction_stadium2"))},
        "validation": {"validatedByHuman": truthy(row.get("validated_by_human")), "secondOpinion": truthy(row.get("second_opinion")), "validatedBy": clean(row.get("validated_by")), "stratFold": clean(row.get("strat_fold"))},
        "quality": {"baselineDrift": clean(row.get("baseline_drift")), "staticNoise": clean(row.get("static_noise")), "burstNoise": clean(row.get("burst_noise")), "electrodeProblems": clean(row.get("electrodes_problems")), "extraBeats": clean(row.get("extra_beats")), "pacemaker": clean(row.get("pacemaker"))},
        "integrity": {"sourceDatSha256": sha256(dat)},
    }


def process_candidate(candidate: dict[str, Any], row: dict[str, str], force: bool) -> None:
    folder, record_base, dat = prepare_record(candidate, force=force)
    signal_path = folder / "signal_500hz.json"
    metadata_path = folder / "metadata.json"
    if signal_path.exists() and metadata_path.exists() and not force:
        print(f"Conservado {candidate['candidateId']}: ya estaba preparado.")
        return
    leads, fs, samples = read_record(record_base)
    signal = {
        "schemaVersion": "1.1", "id": candidate["candidateId"],
        "title": f"Fibrilación auricular · ECG {candidate['ecgId']}",
        "source": {"dataset": "PTB-XL", "version": "1.0.3", "ecgId": int(candidate["ecgId"]), "record": candidate["sourceRecord500Hz"]},
        "sampleRateHz": fs, "durationSeconds": round(samples / fs, 6), "samplesPerLead": samples,
        "units": "mV", "leadOrder": LEAD_ORDER, "leads": leads,
    }
    write_json(signal_path, signal)
    write_json(metadata_path, build_metadata(candidate, row, dat))
    print(f"Preparado {candidate['candidateId']} · ECG {candidate['ecgId']}")


def load_embedded_records(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for candidate in catalog["candidates"]:
        folder = CANDIDATES_ROOT / str(candidate["candidateId"])
        signal_path = folder / "signal_500hz.json"
        metadata_path = folder / "metadata.json"
        if not signal_path.exists() or not metadata_path.exists():
            raise RuntimeError(f"Faltan archivos preparados para {candidate['candidateId']}.")
        records.append({"candidate": candidate, "signal": load_json(signal_path), "metadata": load_json(metadata_path)})
    return records


VIEWER_TEMPLATE = r'''<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Revisión de candidatos AFIB</title>
<style>
:root{--bg:#eef1f4;--card:#fff;--ink:#18212a;--muted:#66727e;--line:#d7dde3;--accent:#145f8c}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:Arial,Helvetica,sans-serif}button,select,textarea,input{font:inherit}header{position:sticky;top:0;z-index:20;background:#10212c;color:#fff;padding:14px 18px;box-shadow:0 2px 12px #0003}header h1{margin:0 0 4px;font-size:20px}header p{margin:0;color:#c9d6de;font-size:13px}main{max-width:1760px;margin:0 auto;padding:16px}.card{background:var(--card);border:1px solid var(--line);border-radius:12px;box-shadow:0 2px 9px #27374612;margin-bottom:14px}.toolbar{padding:12px;display:flex;flex-wrap:wrap;gap:10px;align-items:end}.field{display:flex;flex-direction:column;gap:5px}.field label{font-size:12px;color:var(--muted);font-weight:700}.field select,.field textarea{border:1px solid #bfc8d0;border-radius:7px;padding:8px;background:#fff}.field select{min-width:320px}.button{border:1px solid #aeb8c0;background:#fff;border-radius:7px;padding:8px 12px;cursor:pointer}.button:hover{background:#f2f5f7}.button.primary{background:var(--accent);border-color:var(--accent);color:#fff}.counts{margin-left:auto;display:flex;gap:8px;flex-wrap:wrap}.badge{padding:6px 9px;border-radius:999px;background:#e8edf1;font-size:12px;font-weight:700}.badge.approved{background:#dff3e8;color:#145d38}.badge.rejected{background:#f7dddd;color:#842727}.badge.reserved{background:#fff0ce;color:#7d5300}.summary{padding:12px 16px;border-top:1px solid var(--line);display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:8px}.summary strong{display:block;font-size:12px;color:var(--muted);margin-bottom:3px}.paper-scroll{overflow:auto;padding:10px}.paper-caption{font-size:12px;color:var(--muted);padding:0 12px 10px}.ecg{display:block;background:#fffdfd;border:1px solid #ddbcbc}.review-grid{display:grid;grid-template-columns:minmax(300px,420px) 1fr;gap:14px}.review-panel,.meta-panel{padding:14px}.review-panel h2,.meta-panel h2{margin:0 0 12px;font-size:17px}.status-buttons{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;margin-bottom:12px}.status-button{border:1px solid #b8c1c8;background:#fff;border-radius:8px;padding:10px;cursor:pointer;font-weight:700}.status-button.active[data-status=approved]{background:#dff3e8;border-color:#68aa83;color:#145d38}.status-button.active[data-status=rejected]{background:#f7dddd;border-color:#c67878;color:#842727}.status-button.active[data-status=reserved]{background:#fff0ce;border-color:#d5aa58;color:#7d5300}.status-button.active[data-status=pending]{background:#e8edf1;border-color:#8697a4}.checks{display:grid;gap:7px;margin:12px 0}.check{display:flex;gap:8px;align-items:flex-start;font-size:13px}.notes{width:100%;min-height:110px;resize:vertical}.actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}.notice{font-size:12px;color:var(--muted);line-height:1.45}.meta-sections{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:10px}.meta-section{border:1px solid var(--line);border-radius:8px;padding:10px;min-width:0}.meta-section h3{font-size:14px;margin:0 0 8px}.meta-row{display:grid;grid-template-columns:120px 1fr;gap:8px;border-top:1px solid #edf0f2;padding:6px 0;font-size:12px}.meta-row:first-of-type{border-top:0}.meta-key{color:var(--muted);font-weight:700}.meta-value{overflow-wrap:anywhere;white-space:pre-wrap}.footer{color:var(--muted);font-size:12px;padding:4px 2px 20px}@media(max-width:950px){.review-grid{grid-template-columns:1fr}.counts{margin-left:0;width:100%}.field select{min-width:240px}}
</style></head><body>
<header><h1>Laboratorio de revisión · Fibrilación auricular</h1><p>20 candidatos PTB-XL · 12 derivaciones · 500 Hz · 10 segundos · señal sin modificar</p></header><main>
<section class="card"><div class="toolbar"><button class="button" id="prevButton">← Anterior</button><div class="field"><label for="candidateSelect">Candidato</label><select id="candidateSelect"></select></div><button class="button" id="nextButton">Siguiente →</button><button class="button" id="resetViewButton">Redibujar</button><div class="counts" id="counts"></div></div><div class="summary" id="summary"></div></section>
<section class="card"><div class="paper-caption">Disposición secuencial 3 × 4: I/aVR/V1/V4 · II/aVL/V2/V5 · III/aVF/V3/V6. DII largo usa los 10 segundos completos. Escala fija: 25 mm/s y 10 mm/mV.</div><div class="paper-scroll"><canvas class="ecg" id="ecgCanvas"></canvas></div></section>
<section class="review-grid"><section class="card review-panel"><h2>Decisión de revisión</h2><div class="status-buttons"><button class="status-button" data-status="pending">Pendiente</button><button class="status-button" data-status="approved">Aprobar</button><button class="status-button" data-status="rejected">Rechazar</button><button class="status-button" data-status="reserved">Reservar</button></div><div class="checks" id="checks"></div><div class="field"><label for="notes">Notas clínicas o técnicas</label><textarea class="notes" id="notes"></textarea></div><div class="actions"><button class="button primary" id="saveButton">Guardar en este navegador</button><button class="button" id="exportButton">Exportar review_state.json</button><label class="button" for="importInput">Importar revisión</label><input type="file" id="importInput" accept="application/json" hidden></div><p class="notice">Las decisiones se guardan en el navegador. Exporte el JSON para versionarlas.</p></section><section class="card meta-panel"><h2>Metadatos del registro</h2><div class="meta-sections" id="metadata"></div></section></section>
<p class="footer">Fuente: PTB-XL 1.0.3, PhysioNet, licencia CC BY 4.0. Uso educativo; no destinado a diagnóstico.</p></main>
<script>
const BANK=__BANK_JSON__,STORAGE_KEY='ekg_project_afib_review_v1',LEAD_GRID=[['I','aVR','V1','V4'],['II','aVL','V2','V5'],['III','aVF','V3','V6']],REQUIRED_LABELS={twelveLeadsPresent:'Las 12 derivaciones están presentes',durationTenSeconds:'La duración es de 10 segundos',sampleRate500Hz:'La señal es de 500 Hz',rrIrregularityVisible:'La irregularidad RR es visible',consistentPWavesAbsent:'No hay ondas P consistentes',fibrillatoryActivityCompatible:'La actividad auricular es compatible con FA',artifactAcceptable:'El artefacto es aceptable',concomitantFindingsDocumented:'Los hallazgos concomitantes están documentados'};let currentIndex=0,reviewState=loadReviewState();const $=id=>document.getElementById(id),clone=v=>JSON.parse(JSON.stringify(v)),shown=v=>v===null||v===undefined||v===''?'No indicado':String(v);
function defaultReview(){const b=clone(BANK.reviewState);for(const i of b.candidates){i.checks=i.checks||{};for(const k of b.requiredChecks)i.checks[k]=Boolean(i.checks[k])}return b}function mergeReview(x){const b=defaultReview(),m=new Map((x?.candidates||[]).map(i=>[i.candidateId,i]));for(const i of b.candidates){const n=m.get(i.candidateId);if(!n)continue;i.status=['pending','approved','rejected','reserved'].includes(n.status)?n.status:'pending';i.reviewedByHuman=Boolean(n.reviewedByHuman);i.notes=String(n.notes||'');i.checks={...i.checks,...(n.checks||{})}}return b}function loadReviewState(){try{const s=localStorage.getItem(STORAGE_KEY);if(s)return mergeReview(JSON.parse(s))}catch(e){console.warn(e)}return defaultReview()}function saveReview(){localStorage.setItem(STORAGE_KEY,JSON.stringify(reviewState));renderCounts()}function record(){return BANK.records[currentIndex]}function decision(){return reviewState.candidates.find(i=>i.candidateId===record().candidate.candidateId)}
function init(){BANK.records.forEach((r,n)=>{const o=document.createElement('option');o.value=n;o.textContent=`${String(n+1).padStart(2,'0')} · ECG ${r.candidate.ecgId} · ${r.candidate.group}`;$('candidateSelect').appendChild(o)});$('candidateSelect').onchange=()=>{currentIndex=Number($('candidateSelect').value);render()};$('prevButton').onclick=()=>{currentIndex=(currentIndex-1+BANK.records.length)%BANK.records.length;render()};$('nextButton').onclick=()=>{currentIndex=(currentIndex+1)%BANK.records.length;render()};$('resetViewButton').onclick=draw;$('saveButton').onclick=()=>{capture();saveReview();flash('Guardado')};$('exportButton').onclick=exportReview;$('importInput').onchange=importReview;document.querySelectorAll('.status-button').forEach(b=>b.onclick=()=>{const d=decision();d.status=b.dataset.status;d.reviewedByHuman=d.status!=='pending';capture();saveReview();renderReview()});window.onresize=()=>requestAnimationFrame(draw);render()}
function capture(){const d=decision();d.notes=$('notes').value;document.querySelectorAll('[data-check]').forEach(i=>d.checks[i.dataset.check]=i.checked)}function render(){captureSafe();$('candidateSelect').value=currentIndex;renderSummary();renderReview();renderMetadata();renderCounts();draw()}function captureSafe(){if(!$('notes')||!BANK.records.length)return;const d=decision();if(d&&document.activeElement===$('notes'))d.notes=$('notes').value}
function renderSummary(){const r=record(),rows=[['Candidato',r.candidate.candidateId],['ECG ID',r.candidate.ecgId],['Grupo',r.candidate.group],['Resumen',r.candidate.summary],['Señal',`${r.signal.sampleRateHz} Hz · ${r.signal.durationSeconds} s · ${r.signal.units}`]];$('summary').innerHTML='';for(const [k,v] of rows){const d=document.createElement('div'),s=document.createElement('strong'),p=document.createElement('span');s.textContent=k;p.textContent=shown(v);d.append(s,p);$('summary').append(d)}}
function renderReview(){const d=decision();document.querySelectorAll('.status-button').forEach(b=>b.classList.toggle('active',b.dataset.status===d.status));$('checks').innerHTML='';for(const k of reviewState.requiredChecks){const l=document.createElement('label'),i=document.createElement('input'),s=document.createElement('span');l.className='check';i.type='checkbox';i.dataset.check=k;i.checked=Boolean(d.checks?.[k]);i.onchange=()=>{d.checks[k]=i.checked;saveReview()};s.textContent=REQUIRED_LABELS[k]||k;l.append(i,s);$('checks').append(l)}$('notes').value=d.notes||''}function renderCounts(){const c={pending:0,approved:0,rejected:0,reserved:0};for(const i of reviewState.candidates)c[i.status]++;$('counts').innerHTML=`<span class="badge">Pendientes: ${c.pending}</span><span class="badge approved">Aprobados: ${c.approved}</span><span class="badge rejected">Rechazados: ${c.rejected}</span><span class="badge reserved">Reservados: ${c.reserved}</span>`}
function section(t,e){const b=document.createElement('section'),h=document.createElement('h3');b.className='meta-section';h.textContent=t;b.append(h);for(const [k,v] of e){const r=document.createElement('div'),a=document.createElement('div'),z=document.createElement('div');r.className='meta-row';a.className='meta-key';z.className='meta-value';a.textContent=k;z.textContent=typeof v==='object'&&v!==null?JSON.stringify(v,null,2):shown(v);r.append(a,z);b.append(r)}return b}function renderMetadata(){const m=record().metadata,t=$('metadata');t.innerHTML='';t.append(section('Paciente',[['ID',m.patient?.patientId],['Edad',m.patient?.age],['Sexo',m.patient?.sex],['Altura',m.patient?.heightCm],['Peso',m.patient?.weightKg]]),section('Adquisición',[['Fecha',m.acquisition?.recordingDate],['Dispositivo',m.acquisition?.device],['Centro',m.acquisition?.site],['Registro',m.acquisition?.sourceRecord500Hz]]),section('Informe',[['Original',m.report?.original],['Códigos SCP',m.report?.scpCodes],['Eje',m.report?.heartAxis],['Estadio de infarto',m.report?.infarctionStadium1]]),section('Validación',[['Validado por humano',m.validation?.validatedByHuman?'Sí':'No'],['Segunda opinión',m.validation?.secondOpinion?'Sí':'No'],['Validador',m.validation?.validatedBy],['Fold',m.validation?.stratFold]]),section('Calidad',[['Deriva basal',m.quality?.baselineDrift],['Ruido estático',m.quality?.staticNoise],['Ruido en ráfagas',m.quality?.burstNoise],['Electrodos',m.quality?.electrodeProblems],['Latidos extras',m.quality?.extraBeats],['Marcapasos',m.quality?.pacemaker]]))}
function exportReview(){capture();saveReview();const a=reviewState.candidates.filter(x=>x.status==='approved').map(x=>x.candidateId),e={...reviewState,approvedCandidateId:a.length===1?a[0]:null,approvedCandidateIds:a,exportedAt:new Date().toISOString()},b=new Blob([JSON.stringify(e,null,2)],{type:'application/json'}),u=URL.createObjectURL(b),l=document.createElement('a');l.href=u;l.download='review_state.json';l.click();setTimeout(()=>URL.revokeObjectURL(u),1000)}async function importReview(e){const f=e.target.files?.[0];if(!f)return;try{reviewState=mergeReview(JSON.parse(await f.text()));saveReview();render();flash('Importado')}catch(x){alert(x.message)}e.target.value=''}function flash(m){const o=$('saveButton').textContent;$('saveButton').textContent=m;setTimeout(()=>$('saveButton').textContent=o,1200)}
function draw(){const s=record().signal,c=$('ecgCanvas'),MM=6,SPEED=25,GAIN=10,mx=42,mt=34,mb=24,w=10*SPEED*MM,th=600,rh=th/3,gap=18,lh=180,h=mt+th+gap+lh+mb,cw=w/4,dpr=devicePixelRatio||1;c.width=Math.round((w+mx*2)*dpr);c.height=Math.round(h*dpr);c.style.width=`${w+mx*2}px`;c.style.height=`${h}px`;const x=c.getContext('2d');x.setTransform(dpr,0,0,dpr,0,0);x.clearRect(0,0,w+mx*2,h);grid(x,mx,mt,w,th+gap+lh,MM);for(let r=0;r<3;r++)for(let q=0;q<4;q++){const l=LEAD_GRID[r][q];segment(x,s.leads[l],s.sampleRateHz,q*2.5,2.5,mx+q*cw,mt+r*rh,cw,rh,MM*GAIN,l)}segment(x,s.leads.II,s.sampleRateHz,0,10,mx,mt+th+gap,w,lh,MM*GAIN,'II largo');calibration(x,mx+5,mt+5,MM,GAIN)}function grid(c,x,y,w,h,m){c.fillStyle='#fffdfd';c.fillRect(x,y,w,h);c.lineWidth=.45;c.strokeStyle='rgba(225,95,95,.25)';c.beginPath();for(let z=x;z<=x+w;z+=m){c.moveTo(z,y);c.lineTo(z,y+h)}for(let z=y;z<=y+h;z+=m){c.moveTo(x,z);c.lineTo(x+w,z)}c.stroke();c.lineWidth=.9;c.strokeStyle='rgba(195,45,45,.42)';c.beginPath();for(let z=x;z<=x+w;z+=m*5){c.moveTo(z,y);c.lineTo(z,y+h)}for(let z=y;z<=y+h;z+=m*5){c.moveTo(x,z);c.lineTo(x+w,z)}c.stroke()}function segment(c,d,fs,st,du,x,y,w,h,scale,label){if(!d?.length)return;c.save();c.beginPath();c.rect(x,y,w,h);c.clip();const cy=y+h/2,a=Math.max(0,Math.round(st*fs)),b=Math.min(d.length,Math.round((st+du)*fs)),n=Math.max(2,b-a);c.strokeStyle='rgba(20,30,38,.18)';c.lineWidth=.6;c.beginPath();c.moveTo(x,cy);c.lineTo(x+w,cy);c.stroke();c.strokeStyle='#101820';c.lineWidth=1.25;c.lineJoin='round';c.beginPath();for(let i=a;i<b;i++){const px=x+(i-a)/(n-1)*w,py=cy-Number(d[i])*scale;i===a?c.moveTo(px,py):c.lineTo(px,py)}c.stroke();c.fillStyle='#10212c';c.font='bold 14px Arial';c.fillText(label,x+8,y+18);c.restore()}function calibration(c,x,y,m,g){const h=m*g,w=m*5;c.strokeStyle='#101820';c.lineWidth=1.4;c.beginPath();c.moveTo(x,y+h);c.lineTo(x+w*.2,y+h);c.lineTo(x+w*.2,y);c.lineTo(x+w*.8,y);c.lineTo(x+w*.8,y+h);c.lineTo(x+w,y+h);c.stroke()}init();
</script></body></html>'''


def build_viewer(catalog: dict[str, Any], review_state: dict[str, Any], records: list[dict[str, Any]]) -> None:
    bank = {"schemaVersion": "1.0", "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "catalog": catalog, "reviewState": review_state, "records": records}
    embedded = json.dumps(bank, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    VIEWER_PATH.write_text(VIEWER_TEMPLATE.replace("__BANK_JSON__", embedded), encoding="utf-8")
    print(f"Visor creado: {VIEWER_PATH}")
    print(f"Tamaño: {VIEWER_PATH.stat().st_size / (1024 * 1024):.1f} MB")


def main() -> int:
    args = parse_args()
    if not CATALOG_PATH.exists() or not REVIEW_STATE_PATH.exists():
        raise SystemExit("No existe el catálogo o el estado de revisión dentro de testing/.")
    catalog, review_state = load_json(CATALOG_PATH), load_json(REVIEW_STATE_PATH)
    selected_ids = set(args.only) if args.only else None
    candidates = [c for c in catalog.get("candidates", []) if not selected_ids or c["candidateId"] in selected_ids]
    if selected_ids:
        missing = selected_ids - {str(c["candidateId"]) for c in candidates}
        if missing:
            raise SystemExit(f"candidateId desconocidos: {', '.join(sorted(missing))}")
    if not args.viewer_only:
        rows, failures = load_database_rows(force=args.force), []
        for index, candidate in enumerate(candidates, start=1):
            print(f"\n[{index}/{len(candidates)}] {candidate['candidateId']}")
            row = rows.get(int(candidate["ecgId"]))
            if row is None:
                failures.append(f"{candidate['candidateId']}: no está en ptbxl_database.csv")
                continue
            try:
                process_candidate(candidate, row, force=args.force)
            except Exception as exc:
                failures.append(f"{candidate['candidateId']}: {exc}")
        if failures:
            print("\nNo se completó el banco de pruebas:", file=sys.stderr)
            for failure in failures:
                print(f"- {failure}", file=sys.stderr)
            return 1
    build_viewer(catalog, review_state, load_embedded_records(catalog))
    print("\nLISTO. Abra testing\\ABRIR_REVISION.html con doble clic.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
