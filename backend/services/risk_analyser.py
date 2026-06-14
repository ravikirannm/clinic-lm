import concurrent.futures
import json
import logging
import math

import ollama

from config import OLLAMA_BASE_URL, OLLAMA_MODEL
from services.data_model import RiskScoreExtraction
from services.extract_keywords import ExtractKeywords
from services.notebook_rag import NotebookRAG

logger = logging.getLogger(__name__)

try:
    _extract_keywords = ExtractKeywords()
except Exception as e:
    logger.warning("NER model unavailable (%s); keyword extraction disabled", e)
    _extract_keywords = None


# ── Extraction prompts ────────────────────────────────────────────────────────

_SYS_WELLS = """You are an expert clinical data extraction assistant. Parse the patient text and extract the exact clinical findings required for the Wells Criteria (DVT). DO NOT calculate a score — only extract parameter statuses. Output strict JSON matching the schema exactly."""

_SYS_CHA2DS2 = """You are an expert clinical data extraction assistant. Parse the patient text and extract demographic details and comorbidity history required for the CHA2DS2-VASc score. DO NOT calculate a score — only extract values. Output strict JSON matching the schema exactly."""

_SYS_QSOFA = """You are an expert clinical data extraction assistant. Parse the patient text and extract acute physiological variables required for the qSOFA score. DO NOT calculate a score — only extract values. Output strict JSON matching the schema exactly."""

_SYS_MELD = """You are an expert clinical data extraction assistant. Parse the patient text and extract laboratory values required for the MELD score. DO NOT calculate a score — only extract values with their units. Output strict JSON matching the schema exactly."""


def _wells_user(context: str, text: str) -> str:
    return f"""=== PATIENT SOURCE DOCUMENTS ===
{context}

=== CLINICAL NOTE ===
{text}

Extract the Wells DVT parameters. For each, set status_found to "present", "absent", or "unknown", and include the exact evidence_quote from the text (or null).

Parameters to extract (one entry per parameter):
1. Active cancer (treatment within 6 months or palliation)
2. Paralysis, paresis, or recent plaster immobilization of lower extremities
3. Recently bedridden >= 3 days or major surgery within 12 weeks
4. Localized tenderness along the distribution of the deep venous system
5. Entire leg swollen
6. Calf swelling at least 3 cm larger than asymptomatic side
7. Pitting edema confined to the symptomatic leg
8. Collateral superficial veins (non-varicose)
9. Previous documented DVT or PE
10. Alternative diagnosis at least as likely as DVT (set status_found to "yes" or "no")"""


def _cha2ds2_user(context: str, text: str) -> str:
    return f"""=== PATIENT SOURCE DOCUMENTS ===
{context}

=== CLINICAL NOTE ===
{text}

Extract the CHA2DS2-VASc parameters. Use value_found for Age (numeric) and Biological Sex (male/female). Use status_found (present/absent/unknown) for all comorbidities. Include evidence_quote for each.

Parameters to extract:
1. Age (set value_found to numeric age)
2. Biological Sex (set value_found to "male" or "female")
3. Congestive Heart Failure history (or LVEF <= 40%)
4. Hypertension history (or consistently elevated BP)
5. Diabetes Mellitus history
6. Stroke, TIA, or Thromboembolism history
7. Vascular Disease history (prior MI, PAD, or aortic plaque)"""


def _qsofa_user(context: str, text: str) -> str:
    return f"""=== PATIENT SOURCE DOCUMENTS ===
{context}

=== CLINICAL NOTE ===
{text}

Extract the qSOFA parameters. Use value_found for numeric values and status_found for categorical ones. Include evidence_quote for each.

Parameters to extract:
1. Respiratory Rate (set value_found to numeric breaths/min or null)
2. Altered Mental Status (GCS < 15, confusion, or acute lethargy) (set status_found to "altered", "normal", or "unknown")
3. Systolic Blood Pressure (set value_found to numeric mmHg or null)"""


def _meld_user(context: str, text: str) -> str:
    return f"""=== PATIENT SOURCE DOCUMENTS ===
{context}

=== CLINICAL NOTE ===
{text}

Extract the MELD laboratory values. Use value_found for numeric values and specify unit (mg/dL or umol/L where applicable). Include evidence_quote for each.

Parameters to extract:
1. Serum Bilirubin (value_found: numeric, unit: "mg/dL" or "umol/L")
2. Serum Creatinine (value_found: numeric, unit: "mg/dL" or "umol/L")
3. INR (International Normalized Ratio) (value_found: numeric)
4. Serum Sodium (value_found: numeric, unit: "mEq/L" or "mmol/L")
5. Renal Dialysis History (received at least twice within prior 7 days / CVVH) (status_found: "yes", "no", or "unknown")"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _find(params: list[dict], *keywords: str) -> dict:
    """Return first parameter whose name contains any keyword (case-insensitive)."""
    lck = [k.lower() for k in keywords]
    for p in params:
        name = p.get("parameter", "").lower()
        if any(k in name for k in lck):
            return p
    return {}


def _is_present(status: str | None) -> bool:
    return (status or "").lower() in ("present", "yes", "true", "positive", "altered", "abnormal", "1")


def _parse_float(v: str | None) -> float | None:
    if not v or str(v).lower() in ("null", "none", "unknown"):
        return None
    try:
        return float(str(v).replace(",", ".").strip())
    except (ValueError, AttributeError):
        return None


# ── Deterministic calculators ─────────────────────────────────────────────────

def _calc_wells_dvt(params: list[dict]) -> dict:
    CRITERIA = [
        ("Active cancer (treatment within 6 months or palliation)", 1),
        ("Paralysis, paresis, or recent plaster immobilization of lower extremities", 1),
        ("Recently bedridden >= 3 days or major surgery within 12 weeks", 1),
        ("Localized tenderness along the distribution of the deep venous system", 1),
        ("Entire leg swollen", 1),
        ("Calf swelling at least 3 cm larger than asymptomatic side", 1),
        ("Pitting edema confined to the symptomatic leg", 1),
        ("Collateral superficial veins (non-varicose)", 1),
        ("Previous documented DVT or PE", 1),
    ]

    score = 0
    criteria = []

    for name, pts in CRITERIA:
        p = _find(params, name.split()[0], name.split()[1] if len(name.split()) > 1 else "")
        # More precise: match by first few distinctive words
        p = _find(params, *name.lower().split()[:3])
        status = (p.get("status_found") or "unknown").lower()
        awarded = pts if _is_present(status) else 0
        score += awarded
        criteria.append({
            "criterion": name,
            "points_possible": pts,
            "points_awarded": awarded,
            "status": status,
            "evidence": p.get("evidence_quote"),
        })

    # Alternative diagnosis (yes → -2)
    p = _find(params, "alternative")
    status = (p.get("status_found") or "unknown").lower()
    awarded = -2 if status == "yes" else 0
    score += awarded
    criteria.append({
        "criterion": "Alternative diagnosis at least as likely as DVT",
        "points_possible": -2,
        "points_awarded": awarded,
        "status": status,
        "evidence": p.get("evidence_quote"),
    })

    if score <= 0:
        risk, prob, rec = "Low", "~3%", "DVT unlikely. Consider D-dimer to rule out."
    elif score <= 2:
        risk, prob, rec = "Moderate", "~17%", "Moderate probability. D-dimer or compression ultrasound recommended."
    else:
        risk, prob, rec = "High", "~75%", "High probability of DVT. Compression ultrasound and anticoagulation consideration warranted."

    missing = [p["parameter"] for p in params if (p.get("status_found") or "unknown").lower() == "unknown"]
    return {"score": score, "max_score": 9, "risk_level": risk, "probability": prob,
            "recommendation": rec, "criteria": criteria, "missing_parameters": missing}


def _calc_cha2ds2_vasc(params: list[dict]) -> dict:
    score = 0
    criteria = []

    age_p = _find(params, "age")
    age = _parse_float(age_p.get("value_found"))
    if age is not None:
        pts = 2 if age >= 75 else (1 if age >= 65 else 0)
        score += pts
        criteria.append({"criterion": "Age ≥75 (+2) / Age 65–74 (+1)", "points_possible": 2,
                         "points_awarded": pts, "status": f"{int(age)} years", "evidence": age_p.get("evidence_quote")})
    else:
        criteria.append({"criterion": "Age ≥75 (+2) / Age 65–74 (+1)", "points_possible": 2,
                         "points_awarded": 0, "status": "unknown", "evidence": None})

    sex_p = _find(params, "sex", "gender")
    sex = (sex_p.get("value_found") or "").lower()
    sex_pts = 1 if sex in ("female", "f", "woman") else 0
    score += sex_pts
    criteria.append({"criterion": "Female sex", "points_possible": 1, "points_awarded": sex_pts,
                     "status": sex or "unknown", "evidence": sex_p.get("evidence_quote")})

    COMORBIDITIES = [
        ("heart failure", "chf", "Congestive Heart Failure (or LVEF ≤40%)", 1),
        ("hypertension",  None,  "Hypertension",                               1),
        ("diabetes",      None,  "Diabetes Mellitus",                           1),
        ("stroke", "tia",       "Stroke / TIA / Thromboembolism",              2),
        ("vascular",      None,  "Vascular Disease (MI, PAD, aortic plaque)",  1),
    ]
    for k1, k2, label, pts in COMORBIDITIES:
        keys = [k1] + ([k2] if k2 else [])
        p = _find(params, *keys)
        status = (p.get("status_found") or "unknown").lower()
        awarded = pts if _is_present(status) else 0
        score += awarded
        criteria.append({"criterion": label, "points_possible": pts, "points_awarded": awarded,
                         "status": status, "evidence": p.get("evidence_quote")})

    _STROKE_RISK = {0: 0, 1: 1.3, 2: 2.2, 3: 3.2, 4: 4.0, 5: 6.7, 6: 9.8, 7: 9.6, 8: 12.5, 9: 15.2}
    annual = _STROKE_RISK.get(min(max(score, 0), 9), 15.2)

    if score == 0:
        risk, rec = "Low", "Anticoagulation generally not recommended."
    elif score == 1 and sex_pts == 0:
        risk, rec = "Low-Moderate", "Anticoagulation may be considered; weigh bleeding risk."
    elif score <= 2:
        risk, rec = "Moderate", "Oral anticoagulation generally recommended."
    else:
        risk, rec = "High", "Oral anticoagulation strongly recommended."

    missing = []
    if age is None:
        missing.append("Age")
    if not sex:
        missing.append("Biological Sex")
    missing += [p["parameter"] for p in params
                if p.get("parameter", "").lower() not in ("age", "biological sex")
                and (p.get("status_found") or "unknown").lower() == "unknown"]

    return {"score": score, "max_score": 9, "risk_level": risk, "annual_stroke_risk": f"{annual}%",
            "recommendation": rec, "criteria": criteria, "missing_parameters": missing}


def _calc_qsofa(params: list[dict]) -> dict:
    score = 0
    criteria = []

    rr_p = _find(params, "respiratory rate", "respiratory")
    rr = _parse_float(rr_p.get("value_found"))
    if rr is not None:
        pts = 1 if rr >= 22 else 0
        score += pts
        criteria.append({"criterion": "Respiratory Rate ≥22 /min", "points_possible": 1,
                         "points_awarded": pts, "status": f"{rr} /min", "evidence": rr_p.get("evidence_quote")})
    else:
        criteria.append({"criterion": "Respiratory Rate ≥22 /min", "points_possible": 1,
                         "points_awarded": 0, "status": "unknown", "evidence": None})

    ams_p = _find(params, "altered mental", "mental status", "gcs")
    ams = (ams_p.get("status_found") or "unknown").lower()
    ams_pts = 1 if ams == "altered" or _is_present(ams) else 0
    score += ams_pts
    criteria.append({"criterion": "Altered Mental Status (GCS <15)", "points_possible": 1,
                     "points_awarded": ams_pts, "status": ams, "evidence": ams_p.get("evidence_quote")})

    sbp_p = _find(params, "systolic", "blood pressure", "sbp")
    sbp = _parse_float(sbp_p.get("value_found"))
    if sbp is not None:
        pts = 1 if sbp <= 100 else 0
        score += pts
        criteria.append({"criterion": "Systolic BP ≤100 mmHg", "points_possible": 1,
                         "points_awarded": pts, "status": f"{sbp} mmHg", "evidence": sbp_p.get("evidence_quote")})
    else:
        criteria.append({"criterion": "Systolic BP ≤100 mmHg", "points_possible": 1,
                         "points_awarded": 0, "status": "unknown", "evidence": None})

    if score == 0:
        risk, interp = "Low", "Low risk of organ dysfunction. Routine monitoring."
    elif score == 1:
        risk, interp = "Moderate", "Possible sepsis. Consider further evaluation and blood cultures."
    else:
        risk, interp = "High", "High risk of organ failure / ICU admission. Urgent sepsis workup required."

    missing = []
    if rr is None:
        missing.append("Respiratory Rate")
    if ams == "unknown":
        missing.append("Altered Mental Status")
    if sbp is None:
        missing.append("Systolic Blood Pressure")

    return {"score": score, "max_score": 3, "risk_level": risk, "interpretation": interp,
            "criteria": criteria, "missing_parameters": missing}


def _calc_meld(params: list[dict]) -> dict:
    bili_p = _find(params, "bilirubin")
    creat_p = _find(params, "creatinine")
    inr_p = _find(params, "inr", "international normalized")
    na_p = _find(params, "sodium")
    dialysis_p = _find(params, "dialysis")

    bili_val = _parse_float(bili_p.get("value_found"))
    bili_unit = (bili_p.get("unit") or "mg/dL").lower()
    creat_val = _parse_float(creat_p.get("value_found"))
    creat_unit = (creat_p.get("unit") or "mg/dL").lower()
    inr_val = _parse_float(inr_p.get("value_found"))
    na_val = _parse_float(na_p.get("value_found"))
    dialysis = _is_present(dialysis_p.get("status_found"))

    # Unit conversions
    if bili_val and "umol" in bili_unit:
        bili_val /= 17.1
    if creat_val and "umol" in creat_unit:
        creat_val /= 88.4

    criteria = [
        {"criterion": "Serum Bilirubin", "points_possible": None, "points_awarded": None,
         "status": f"{round(bili_val, 2)} mg/dL" if bili_val else "unknown", "evidence": bili_p.get("evidence_quote")},
        {"criterion": "Serum Creatinine", "points_possible": None, "points_awarded": None,
         "status": f"{round(creat_val, 2)} mg/dL" if creat_val else "unknown", "evidence": creat_p.get("evidence_quote")},
        {"criterion": "INR", "points_possible": None, "points_awarded": None,
         "status": str(inr_val) if inr_val else "unknown", "evidence": inr_p.get("evidence_quote")},
        {"criterion": "Serum Sodium", "points_possible": None, "points_awarded": None,
         "status": f"{na_val} mEq/L" if na_val else "unknown", "evidence": na_p.get("evidence_quote")},
        {"criterion": "Renal Dialysis (×2 in prior week)", "points_possible": None, "points_awarded": None,
         "status": "yes" if dialysis else (dialysis_p.get("status_found") or "unknown"), "evidence": dialysis_p.get("evidence_quote")},
    ]

    score = None
    meld_na = None
    can_calc = all(v is not None for v in [bili_val, creat_val, inr_val])
    if can_calc:
        bili = max(bili_val, 1.0)
        inr = max(inr_val, 1.0)
        creat = 4.0 if dialysis else min(max(creat_val, 1.0), 4.0)
        score = round(3.78 * math.log(bili) + 11.2 * math.log(inr) + 9.57 * math.log(creat) + 6.43)
        if na_val is not None:
            na = max(min(na_val, 137), 125)
            meld_na = round(score + 1.32 * (137 - na) - 0.033 * score * (137 - na))

    _MORTALITY = [(9, "~1.9%"), (19, "~6%"), (29, "~19.6%"), (39, "~52.6%")]
    if score is None:
        risk, mortality = "Insufficient data", None
    else:
        risk = "Low" if score <= 9 else "Moderate" if score <= 19 else "Severe" if score <= 29 else "Very High" if score <= 39 else "Critical"
        mortality = next((m for t, m in _MORTALITY if score <= t), "~71.3%")

    missing = [lbl for lbl, v in [("Serum Bilirubin", bili_val), ("Serum Creatinine", creat_val), ("INR", inr_val)] if v is None]
    if na_val is None:
        missing.append("Serum Sodium (for MELD-Na)")

    result = {"score": score, "max_score": 40, "risk_level": risk, "3_month_mortality": mortality,
              "criteria": criteria, "missing_parameters": missing}
    if meld_na is not None:
        result["meld_na"] = meld_na
    return result


# ── Service ───────────────────────────────────────────────────────────────────

class RiskAnalyzer:
    def __init__(self):
        self.client = ollama.Client(host=OLLAMA_BASE_URL)

    def _extract(self, system: str, user: str, label: str) -> dict:
        try:
            resp = self.client.chat(
                model=OLLAMA_MODEL,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                format=RiskScoreExtraction.model_json_schema(),
                options={"temperature": 0},
            )
            return RiskScoreExtraction.model_validate_json(resp["message"]["content"]).model_dump()
        except Exception as e:
            logger.error("LLM extraction failed for %s: %s", label, e)
            return {"scoring_system": label, "parameters_extracted": [], "missing_parameters": []}

    def analyze(self, notebook_id: str, text: str) -> dict:
        # Step 1: keyword extraction
        keywords = _extract_keywords.get_clinical_ner_results(text) if _extract_keywords else []

        # Step 2: notebook RAG
        notebook_chunks: list = []
        if notebook_id and keywords:
            try:
                notebook_chunks = NotebookRAG.retrieve(notebook_id, " ".join(keywords))
            except Exception as e:
                logger.warning("NotebookRAG retrieval failed: %s", e)

        context = json.dumps(notebook_chunks, indent=1) if notebook_chunks else "(none)"

        # Step 3: parallel LLM extraction for all 4 scoring systems
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
            f_wells = ex.submit(self._extract, _SYS_WELLS, _wells_user(context, text), "Wells DVT")
            f_cha2 = ex.submit(self._extract, _SYS_CHA2DS2, _cha2ds2_user(context, text), "CHA2DS2-VASc")
            f_qsofa = ex.submit(self._extract, _SYS_QSOFA, _qsofa_user(context, text), "qSOFA")
            f_meld = ex.submit(self._extract, _SYS_MELD, _meld_user(context, text), "MELD")

        wells_raw = f_wells.result().get("parameters_extracted", [])
        cha2_raw = f_cha2.result().get("parameters_extracted", [])
        qsofa_raw = f_qsofa.result().get("parameters_extracted", [])
        meld_raw = f_meld.result().get("parameters_extracted", [])

        logger.info("Risk extraction done — Wells:%d CHA2:%d qSOFA:%d MELD:%d params",
                    len(wells_raw), len(cha2_raw), len(qsofa_raw), len(meld_raw))

        # Step 4: deterministic score calculation
        return {
            "keywords": keywords,
            "scores": {
                "wells_dvt": _calc_wells_dvt([p for p in wells_raw]),
                "cha2ds2_vasc": _calc_cha2ds2_vasc([p for p in cha2_raw]),
                "qsofa": _calc_qsofa([p for p in qsofa_raw]),
                "meld": _calc_meld([p for p in meld_raw]),
            },
        }
