import json
import logging
from itertools import combinations
import concurrent.futures

import ollama

from config import OLLAMA_BASE_URL, OLLAMA_MODEL
from services.data_model import (
    DrugExtractionResult, PubMedSearchQuery, PICOEvidence, DrugNameList
)
from services.notebook_rag import NotebookRAG
from external.rxnav import RXNavClient
from external.pubmed import PubMedClient
from external.internet import search_tool
from external.openfda import OpenFDA

logger = logging.getLogger(__name__)

_rxnav_client = RXNavClient()
_pubmed_client = PubMedClient()
_openfda_client = OpenFDA()


class InteractionChecker:
    def __init__(self):
        self.client = ollama.Client(host=OLLAMA_BASE_URL)

    def interaction_check(self, text: str, notebook_id: str = "", on_progress=None) -> dict:
        def _progress(step: str, pct: int):
            if on_progress:
                on_progress(step, pct)

        # ── Notebook RAG: fetch patient-specific context ──────────────────────
        _progress("Retrieving patient context…", 8)
        notebook_chunks: list = []
        if notebook_id:
            try:
                notebook_chunks = NotebookRAG.retrieve(notebook_id, text[:500])
            except Exception as e:
                logger.warning("NotebookRAG retrieval failed: %s", e)

        # ── Step A: Extract drug name strings from text ───────────────────────
        _progress("Extracting drug names…", 18)
        step_a_system_prompt = """
            You are a drug name extractor.

            The user will provide a medical query containing drug brand names, generic names, or both.

            Your job:
            1. Identify every drug brand name and generic name mentioned in the query.
            2. Output ONLY a JSON array of strings — one entry per drug, exactly as mentioned.

            Example input: "Calpol 500, Brufen 400mg and metformin"
            Example output: ["Calpol 500", "Brufen 400mg", "metformin"]

            No explanation. No preamble. Only the JSON array.
        """
        pass1_response = self.client.chat(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": step_a_system_prompt},
                {"role": "user", "content": text}
            ],
            format=DrugNameList.model_json_schema(),
            options={"temperature": 0.1}
        )
        drug_list_obj = DrugNameList.model_validate_json(pass1_response["message"]["content"])
        step_a_conf = max(0.0, min(1.0, drug_list_obj.confidence))
        drug_names = drug_list_obj.items

        # ── Step B: Web search per drug name (no LLM, raw context only) ──────
        _progress("Searching drug databases…", 30)
        brand_molecule_map: dict[str, str] = {}
        for item in drug_names:
            content = search_tool(f"Molecule present in the medical drug {item}")
            brand_molecule_map[item] = content.strip()[:300]

        logger.info("Web search completed for drugs: %s", list(brand_molecule_map.keys()))
        text = text + "\n\nDrug web search context:\n" + json.dumps(brand_molecule_map, indent=1)

        # ── Step C: Full structured drug extraction with candidate names ──────
        _progress("Identifying molecular structures…", 42)
        step_c_system_prompt = f"""
            You are a clinical pharmacology language formatter. Your only job is to:
            1. Extract all drug and substance names from natural language input.
            2. Internet search response is attached for each drug to help identify brand vs generic vs molecule names.

            === PATIENT SOURCE DOCUMENTS ===
            {json.dumps(notebook_chunks, indent=1)}

            === BRAND MOLECULE INTERNET SEARCH CONTEXT ===
            {brand_molecule_map}

            Rules:
            - Extract ALL substances mentioned — brand names, generic names, supplements, herbal remedies
            - Do not add drugs not mentioned
            - Do not diagnose or speculate on conditions
            - If dosage/duration is unclear, mark as "unspecified"
            - Output must be valid JSON only, no preamble, no explanation
            - For each drug in drugs_mentioned, populate candidate_names with 3-5 name variants:
              the name as mentioned, INN/generic name, molecule name, common abbreviations, and
              chemical synonyms — these are used to maximize hits against drug databases like RxNorm

            Output format (strict JSON):
            {{
                "drugs_mentioned": [
                    {{
                        "name_as_mentioned": "aspirin",
                        "generic_name": "acetylsalicylic acid",
                        "drug_class": "NSAID / antiplatelet",
                        "dosage": "unspecified",
                        "duration": "unspecified",
                        "candidate_names": ["aspirin", "acetylsalicylic acid", "ASA", "acetylsalicylate", "2-acetoxybenzoic acid"]
                    }}
                ]
            }}
        """
        response = self.client.chat(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": step_c_system_prompt},
                {"role": "user", "content": text}
            ],
            format=DrugExtractionResult.model_json_schema(),
            options={"temperature": 0.2}
        )
        drug_extraction_obj = DrugExtractionResult.model_validate_json(response["message"]["content"])
        step_c_conf = max(0.0, min(1.0, drug_extraction_obj.confidence))
        drug_extraction_result = drug_extraction_obj.model_dump()
        logger.info("Drug extraction result: %s", drug_extraction_result)

        # ── RxNorm verification ───────────────────────────────────────────────
        _progress("Verifying drug identities via RxNorm…", 55)
        pseudoscience_flags: list = []
        verified_drugs: list = []

        for drug in drug_extraction_result.get("drugs_mentioned", []):
            drug_name = drug.get("name_as_mentioned", "")
            candidates = list(drug.get("candidate_names") or [])
            for fallback in [drug.get("generic_name", ""), drug_name]:
                if fallback and fallback not in candidates:
                    candidates.append(fallback)
            seen_lower: set = set()
            unique_candidates = [
                c for c in candidates
                if c and not (c.lower() in seen_lower or seen_lower.add(c.lower()))
            ]

            rxnav_response = _rxnav_client.get_rxcui(unique_candidates)
            rxcui_found = rxnav_response["rxcui"]
            matched_candidate = rxnav_response["matched_candidate"]

            if rxcui_found and matched_candidate:
                drug["rxcui"] = rxcui_found
                verified_drugs.append(drug)
                logger.info(
                    "RxNorm verified '%s' via '%s' → rxcui=%s",
                    drug_name, matched_candidate, rxcui_found
                )

        logger.info("Verified drugs: %s", [d["name_as_mentioned"] for d in verified_drugs])

        drug_rxcui_map = {
            (d.get("generic_name") or d.get("name_as_mentioned")): d.get("rxcui")
            for d in verified_drugs
        }
        rxcui_names_map = {d.get("rxcui"): d.get("candidate_names") for d in verified_drugs}
        logger.info("Resolved RxCUIs: %s", drug_rxcui_map)

        # ── Process all drug pairs concurrently ───────────────────────────────
        _progress("Checking drug pair interactions…", 65)
        drugs_list = list(drug_rxcui_map.keys())
        drug_pairs = list(combinations(drugs_list, 2))

        interaction_results: list = []
        all_sources: list = []
        severities = ["NONE", "LOW", "MODERATE", "HIGH", "CONTRAINDICATED"]

        for drug1_name, drug2_name in drug_pairs:
            rxcui1 = drug_rxcui_map.get(drug1_name)
            rxcui2 = drug_rxcui_map.get(drug2_name)

            pair_result: dict = {
                "drug1": drug1_name,
                "drug2": drug2_name,
                "drug1_rxcui": rxcui1,
                "drug2_rxcui": rxcui2,
                "interaction_found": False,
                "severity": "NONE",
                "rxnorm": {},
                "openfda_drug1": {},
                "openfda_drug2": {},
                "adverse_event_count": None,
                "combined_severity": "NONE",
                "sources": []
            }

            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                futures: dict = {}
                if rxcui1 and rxcui2:
                    futures["rxnorm"] = executor.submit(
                        _openfda_client.fetch_rxnorm_interactions, rxcui1, rxcui2, drug2_name
                    )
                futures["openfda_d1"] = executor.submit(_openfda_client.fetch_label, drug1_name)
                futures["openfda_d2"] = executor.submit(_openfda_client.fetch_label, drug2_name)
                futures["adverse"] = executor.submit(
                    _openfda_client.fetch_adverse_events, drug1_name, drug2_name
                )

                rxnorm_data = futures["rxnorm"].result() if "rxnorm" in futures else {}
                openfda_d1 = futures["openfda_d1"].result()
                openfda_d2 = futures["openfda_d2"].result()
                adverse_count = futures["adverse"].result()

            rxnorm_severity = rxnorm_data.get("severity", "NONE")

            openfda_text = ""
            if openfda_d1.get("drug_interactions_text"):
                if drug2_name.lower() in openfda_d1["drug_interactions_text"].lower():
                    openfda_text = openfda_d1["drug_interactions_text"]
            if not openfda_text and openfda_d2.get("drug_interactions_text"):
                if drug1_name.lower() in openfda_d2["drug_interactions_text"].lower():
                    openfda_text = openfda_d2["drug_interactions_text"]

            openfda_severity = _openfda_client.map_severity(openfda_text)
            boxed_severity = _openfda_client.map_severity(
                (openfda_d1.get("boxed_warning") or "") + " " + (openfda_d2.get("boxed_warning") or "")
            )

            combined_severity = max(
                [rxnorm_severity, openfda_severity, boxed_severity],
                key=lambda s: severities.index(s)
            )

            pair_result.update({
                "interaction_found": rxnorm_data.get("found", False) or openfda_severity != "NONE",
                "severity": combined_severity,
                "rxnorm": rxnorm_data,
                "openfda_drug1": openfda_d1,
                "openfda_drug2": openfda_d2,
                "adverse_event_count": adverse_count,
                "combined_severity": combined_severity,
            })

            sources = []
            if rxnorm_data.get("source_url"):
                sources.append({
                    "label": f"RxNorm: {drug1_name} ↔ {drug2_name}",
                    "url": rxnorm_data["source_url"],
                    "type": "rxnorm"
                })
            if openfda_d1.get("source_url"):
                sources.append({
                    "label": f"OpenFDA Label: {drug1_name}",
                    "url": openfda_d1["source_url"],
                    "type": "openfda"
                })
            if openfda_d2.get("source_url"):
                sources.append({
                    "label": f"OpenFDA Label: {drug2_name}",
                    "url": openfda_d2["source_url"],
                    "type": "openfda"
                })

            pair_result["sources"] = sources
            all_sources.extend(sources)
            interaction_results.append(pair_result)
            logger.info(
                "Pair %s ↔ %s: found=%s, severity=%s",
                drug1_name, drug2_name, pair_result["interaction_found"], combined_severity
            )

        # ── PubMed + PICO per pair ────────────────────────────────────────────
        _progress("Fetching clinical evidence from PubMed…", 78)
        for pair in interaction_results:
            drug1 = pair["drug1"]
            drug2 = pair["drug2"]

            reformulations = (
                rxcui_names_map.get(pair["drug1_rxcui"], [drug1]) +
                rxcui_names_map.get(pair["drug2_rxcui"], [drug2])
            )

            query_obj = self.build_pubmed_query(drug1, drug2, reformulations)
            abstracts = _pubmed_client.fetch_pubmed(query_obj)

            pico_dict = None
            if abstracts:
                abstracts_text = "\n\n".join(
                    f"[PMID {a.get('id')}] {a.get('title')} ({a.get('pub_date')})\n{a.get('abstract')}"
                    for a in abstracts
                )
                pico_prompt = f"""
                    You are a clinical evidence synthesizer.
                    Extract a PICO framework for the drug interaction between {drug1} and {drug2}.
                    Base your extraction STRICTLY on the PubMed abstracts provided below.
                    Do not invent, infer, or add anything not stated in the abstracts.
                    If a PICO element cannot be found in the abstracts, set it to null.

                    === PUBMED ABSTRACTS ===
                    {abstracts_text}

                    Output strict JSON only. No preamble. No explanation.

                    {{
                        "population": "patient population described across the studies, or null",
                        "intervention": "the drug combination or co-administration studied, or null",
                        "comparison": "comparator arm or condition studied, or null",
                        "outcome": "primary outcomes and findings reported, or null",
                        "evidence_quality": "high | moderate | low | insufficient",
                        "key_findings": "1-2 sentence summary of what the evidence collectively shows",
                        "supporting_pmids": ["pmid1", "pmid2"]
                    }}

                    Rules:
                    - Quote or closely paraphrase from the abstracts — do not generalize
                    - supporting_pmids must only contain PMIDs from the abstracts above
                    - evidence_quality: high = RCT/meta-analysis, moderate = cohort/case-control,
                    low = case report/expert opinion, insufficient = no relevant findings
                    - If abstracts contain no relevant interaction data, set all fields to null
                    and evidence_quality to "insufficient"
                """
                pico_response = self.client.chat(
                    model=OLLAMA_MODEL,
                    messages=[
                        {"role": "system", "content": pico_prompt},
                        {"role": "user", "content": f"Extract PICO for {drug1} + {drug2} interaction."}
                    ],
                    format=PICOEvidence.model_json_schema(),
                    options={"temperature": 0}
                )
                try:
                    pico = PICOEvidence.model_validate_json(pico_response["message"]["content"])
                    if (
                        pico.evidence_quality == "insufficient"
                        and not any([pico.population, pico.intervention, pico.comparison, pico.outcome])
                    ):
                        pico_dict = None
                    else:
                        pico_dict = pico.model_dump()
                        logger.info("PICO generated for %s + %s", drug1, drug2)
                except Exception:
                    logger.warning("PICO parse failed for %s + %s", drug1, drug2)
                    pico_dict = None

                for abstract in abstracts:
                    all_sources.append({
                        "label": f"PubMed: {(abstract.get('title') or '')[:60]}...",
                        "url": f"https://pubmed.ncbi.nlm.nih.gov/{abstract.get('id', '')}",
                        "type": "pubmed",
                        "pmid": abstract.get("id")
                    })

            pair["pubmed_abstracts"] = abstracts
            pair["pico"] = pico_dict

        # ── Assemble result ───────────────────────────────────────────────────
        total_confidence = round(step_a_conf * step_c_conf, 3)
        response_data: dict = {
            "confidence": total_confidence,
            "drugs_extracted": drug_extraction_result,
            "brand_molecule_map": brand_molecule_map,
            "pseudoscience_flags": pseudoscience_flags,
            "verified_drugs": verified_drugs,
            "interaction_results": [
                {
                    "drug1": p["drug1"],
                    "drug2": p["drug2"],
                    "drug1_rxcui": p["drug1_rxcui"],
                    "drug2_rxcui": p["drug2_rxcui"],
                    "interaction_found": p["interaction_found"],
                    "severity": p["combined_severity"],
                    "rxnorm_description": p.get("rxnorm", {}).get("description"),
                    "rxnorm_source": p.get("rxnorm", {}).get("source"),
                    "openfda_warnings": p.get("openfda_drug1", {}).get("warnings"),
                    "openfda_boxed_warning": p.get("openfda_drug1", {}).get("boxed_warning"),
                    "adverse_event_count": p.get("adverse_event_count"),
                    "pico": p.get("pico"),
                    "pubmed_abstracts": p.get("pubmed_abstracts", []),
                }
                for p in interaction_results
            ],
            "all_sources": all_sources,
        }

        # ── Synthesis: human-readable summary ─────────────────────────────────
        _progress("Synthesising interaction findings…", 92)
        chat_prompt = f"""
            You are an expert clinical pharmacology assistant.
            You have gathered comprehensive drug interaction data from multiple authoritative sources.
            Your job is to explain the findings to the medical expert in clear, compassionate language.
            Do not dumb down medical accuracy — the medical expert deserves honest information.
            Never give a definitive diagnosis or treatment recommendation.
            Always advise consulting a pharmacist or prescribing physician.

            ==== INTERACTION ANALYSIS ====
            {json.dumps(response_data["interaction_results"], indent=1)}

            ==== PSEUDOSCIENCE FLAGS ====
            {json.dumps(pseudoscience_flags, indent=1)}

            Structure your response as follows:
            1. Brief acknowledgment of what the medical expert described
            2. For each drug pair — explain the interaction risk in plain language, severity, and what it means practically
            3. If any pseudoscience flags exist — explain calmly and factually why that substance cannot be analyzed
            4. Key takeaways and next steps (consult pharmacist, watch for specific symptoms)
            5. Red flags — specific symptoms that should prompt immediate medical attention

            Tone: warm, clear, never alarmist. Scientific but human.
        """
        synthesis_response = self.client.chat(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": chat_prompt},
                {"role": "user", "content": text},
            ],
            stream=False,
            options={"temperature": 0.4},
        )
        response_data["query_response"] = synthesis_response["message"]["content"]

        return response_data

    def build_pubmed_query(self, drug1: str, drug2: str, reformulations: list) -> dict:
        prompt = f"""
            You are a medical literature search specialist.
            Generate optimized PubMed search queries for the drug interaction between {drug1} and {drug2}.

            === CANDIDATE NAMES FOR THIS PAIR ===
            {json.dumps(reformulations, indent=1)}

            Output strict JSON only. No preamble. No explanation.

            {{
                "primary_query": "most specific MeSH boolean query",
                "fallback_query": "broader query if primary returns no results",
                "filters": ["Journal Article", "Clinical Trial", "Review"]
            }}

            Rules:
            - Use MeSH terms with [MeSH Terms] tag where possible
            - Use AND/OR/NOT boolean operators
            - primary_query must include both drug names and interaction/adverse effects
            - fallback_query uses generic names only without MeSH tags
            - Do not add conditions not implied by the interaction concern
        """
        response = self.client.chat(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"Build PubMed query for: {drug1} AND {drug2}"}
            ],
            format=PubMedSearchQuery.model_json_schema(),
            options={"temperature": 0.1}
        )
        try:
            return PubMedSearchQuery.model_validate_json(response["message"]["content"]).model_dump()
        except Exception:
            return {
                "primary_query": f"{drug1}[MeSH Terms] AND {drug2}[MeSH Terms] AND drug interactions[MeSH Terms]",
                "fallback_query": f"{drug1} AND {drug2} AND drug interaction",
                "filters": ["Journal Article"]
            }
