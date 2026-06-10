import logging
from collections import defaultdict
from typing import Any

from rdflib import RDF, XSD, Graph, Literal, Namespace, URIRef

logger = logging.getLogger(__name__)

from app.db import fuseki

PREFIX = """\
PREFIX pm: <https://ontology.example.org/project-management#>
PREFIX inst: <https://ontology.example.org/instances#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
"""

PM = Namespace("https://ontology.example.org/project-management#")
INST = Namespace("https://ontology.example.org/instances#")


def _serialize_nt(graph: Graph) -> str:
    return graph.serialize(format="nt")


def _insert_data(graph: Graph) -> None:
    fuseki.update(f"INSERT DATA {{\n{_serialize_nt(graph)}\n}}")


def _q(body: str) -> list[dict[str, Any]]:
    return fuseki.bindings(fuseki.query_safe(PREFIX + body))


# ──────────────────────────────────────────────────────────────
# Existence checks
# ──────────────────────────────────────────────────────────────

def project_exists(project_id: str) -> bool:
    return fuseki.ask(
        PREFIX + f'ASK {{ ?p a pm:Project ; pm:projectId "{project_id}" }}'
    )


def task_exists(task_id: str) -> bool:
    return fuseki.ask(
        PREFIX + f'ASK {{ ?t a pm:Task ; pm:taskId "{task_id}" }}'
    )


def person_exists(person_id: str) -> bool:
    return fuseki.ask(
        PREFIX + f'ASK {{ ?p a pm:Person ; pm:personId "{person_id}" }}'
    )


# ──────────────────────────────────────────────────────────────
# Projects
# ──────────────────────────────────────────────────────────────

def list_projects() -> list[dict]:
    rows = _q("""
SELECT ?projectId ?projectName ?domain ?status ?startDate ?endDate WHERE {
  ?p a pm:Project ;
     pm:projectId ?projectId ;
     pm:projectName ?projectName ;
     pm:projectStatus ?status .
  OPTIONAL { ?p pm:projectDomain ?domain . }
  OPTIONAL { ?p pm:startDate ?startDate . }
  OPTIONAL { ?p pm:endDate ?endDate . }
}
ORDER BY ?projectId
""")
    return [
        {
            "project_id": r["projectId"],
            "project_name": r["projectName"],
            "domain": r.get("domain"),
            "status": r["status"],
            "start_date": str(r["startDate"]) if r.get("startDate") else None,
            "end_date": str(r["endDate"]) if r.get("endDate") else None,
        }
        for r in rows
    ]


def update_project_status(project_id: str, new_status: str) -> None:
    """프로젝트의 pm:projectStatus를 교체한다. 'ACTIVE' 또는 'COMPLETED' 권장."""
    fuseki.update(PREFIX + f"""
DELETE {{ ?p pm:projectStatus ?old }}
INSERT {{ ?p pm:projectStatus "{new_status}" }}
WHERE  {{ ?p a pm:Project ; pm:projectId "{project_id}" ; pm:projectStatus ?old }}
""")


def all_projects_task_aggregate() -> dict[str, list[dict]]:
    rows = _q("""
SELECT ?projectId ?progress ?planned ?status WHERE {
  ?p a pm:Project ; pm:projectId ?projectId ; pm:hasTask ?t .
  ?t pm:progressPercent ?progress ; pm:taskStatus ?status .
  OPTIONAL { ?t pm:plannedHours ?planned . }
}
""")
    grouped: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        grouped[r["projectId"]].append({
            "progress": r["progress"],
            "planned": r.get("planned"),
            "status": r["status"],
        })
    return dict(grouped)


def list_tasks_by_project(project_id: str) -> list[dict]:
    rows = _q(f"""
SELECT ?taskId ?wbsCode ?taskName ?progress ?status
       ?assigneeRole ?assigneeName ?plannedStart ?dueDate
       ?plannedHours ?actualHours ?estimatedDays ?depCode
       ?reqId ?reqName ?phase ?criticality ?risk
WHERE {{
  ?p a pm:Project ; pm:projectId "{project_id}" ; pm:hasTask ?t .
  ?t pm:taskId ?taskId ;
     pm:wbsCode ?wbsCode ;
     pm:taskName ?taskName ;
     pm:progressPercent ?progress ;
     pm:taskStatus ?status .
  OPTIONAL {{ ?t pm:assigneeRole ?assigneeRole . }}
  OPTIONAL {{ ?t pm:plannedStart ?plannedStart . }}
  OPTIONAL {{ ?t pm:dueDate ?dueDate . }}
  OPTIONAL {{ ?t pm:plannedHours ?plannedHours . }}
  OPTIONAL {{ ?t pm:actualHours ?actualHours . }}
  OPTIONAL {{ ?t pm:estimatedDays ?estimatedDays . }}
  OPTIONAL {{ ?t pm:assignedTo ?person . ?person pm:personName ?assigneeName . }}
  OPTIONAL {{ ?t pm:dependsOn ?dep . ?dep pm:wbsCode ?depCode . }}
  OPTIONAL {{ ?t pm:implementsRequirement ?req . ?req pm:requirementId ?reqId ; pm:requirementName ?reqName . }}
  OPTIONAL {{ ?t pm:phase ?phase . }}
  OPTIONAL {{ ?t pm:criticality ?criticality . }}
  OPTIONAL {{ ?t pm:risk ?risk . }}
}}
ORDER BY ?wbsCode
""")
    # wbsCode별로 depends_on 목록 집계 (1:N 관계)
    tasks: dict[str, dict] = {}
    for r in rows:
        tid = r["taskId"]
        if tid not in tasks:
            tasks[tid] = {
                "task_id": tid,
                "wbs_code": r["wbsCode"],
                "task_name": r["taskName"],
                "progress": r["progress"],
                "status": r["status"],
                "assignee_role": r.get("assigneeRole"),
                "assignee": r.get("assigneeName"),
                "planned_start": r.get("plannedStart"),
                "planned_end": r.get("dueDate"),
                "planned_hours": r.get("plannedHours"),
                "actual_hours": r.get("actualHours"),
                "estimated_days": r.get("estimatedDays"),
                "req_id": r.get("reqId"),
                "req_name": r.get("reqName"),
                "phase": r.get("phase"),
                "criticality": r.get("criticality"),
                "risk": r.get("risk"),
                "depends_on": [],
            }
        if r.get("depCode") and r["depCode"] not in tasks[tid]["depends_on"]:
            tasks[tid]["depends_on"].append(r["depCode"])
    return list(tasks.values())


# ──────────────────────────────────────────────────────────────
# Tasks
# ──────────────────────────────────────────────────────────────

def get_task_by_id(task_id: str) -> dict | None:
    rows = _q(f"""
SELECT ?taskName ?wbsCode ?status ?progress
       ?plannedStart ?dueDate ?plannedHours ?actualHours ?estimatedDays
       ?assigneeRole ?assigneeId ?assigneeName ?sourceFile
       ?projectId ?reqId ?reqName ?depCode
WHERE {{
  ?t a pm:Task ; pm:taskId "{task_id}" ;
     pm:taskName ?taskName ;
     pm:wbsCode ?wbsCode ;
     pm:taskStatus ?status ;
     pm:progressPercent ?progress .
  OPTIONAL {{ ?t pm:plannedStart ?plannedStart . }}
  OPTIONAL {{ ?t pm:dueDate ?dueDate . }}
  OPTIONAL {{ ?t pm:plannedHours ?plannedHours . }}
  OPTIONAL {{ ?t pm:actualHours ?actualHours . }}
  OPTIONAL {{ ?t pm:estimatedDays ?estimatedDays . }}
  OPTIONAL {{ ?t pm:assigneeRole ?assigneeRole . }}
  OPTIONAL {{ ?t pm:assignedTo ?person .
             ?person pm:personId ?assigneeId ; pm:personName ?assigneeName . }}
  OPTIONAL {{ ?t pm:hasSourceFile ?sourceFile . }}
  OPTIONAL {{ ?proj pm:hasTask ?t ; pm:projectId ?projectId . }}
  OPTIONAL {{ ?t pm:implementsRequirement ?req .
             ?req pm:requirementId ?reqId ; pm:requirementName ?reqName . }}
  OPTIONAL {{ ?t pm:dependsOn ?dep . ?dep pm:wbsCode ?depCode . }}
}}
""")
    if not rows:
        return None

    first = rows[0]
    assignee = None
    if first.get("assigneeId"):
        assignee = {
            "person_id": first["assigneeId"],
            "person_name": first.get("assigneeName", ""),
        }
    source_files = sorted({r["sourceFile"] for r in rows if r.get("sourceFile")})
    depends_on = list({r["depCode"] for r in rows if r.get("depCode")})
    return {
        "task_id": task_id,
        "task_name": first["taskName"],
        "wbs_code": first["wbsCode"],
        "status": first["status"],
        "progress": first["progress"],
        "planned_start": first.get("plannedStart"),
        "planned_end": first.get("dueDate"),
        "planned_hours": first.get("plannedHours"),
        "actual_hours": first.get("actualHours"),
        "estimated_days": first.get("estimatedDays"),
        "assignee_role": first.get("assigneeRole"),
        "assignee": assignee,
        "source_files": source_files,
        "project_id": first.get("projectId"),
        "req_id": first.get("reqId"),
        "req_name": first.get("reqName"),
        "depends_on": depends_on,
    }


# ──────────────────────────────────────────────────────────────
# Persons
# ──────────────────────────────────────────────────────────────

def _fold_person_skills(rows: list[dict]) -> list[dict]:
    """Group person+skill rows by personId, yielding person dicts with skills list."""
    people: dict[str, dict] = {}
    for r in rows:
        pid = r["personId"]
        person = people.setdefault(pid, {
            "person_id": pid,
            "person_name": r["personName"],
            "role": r.get("role"),
            "skills": [],
        })
        if r.get("skillName"):
            person["skills"].append({
                "name": r["skillName"],
                "proficiency": r.get("proficiency"),
            })
    return list(people.values())


def list_persons_with_skills() -> list[dict]:
    rows = _q("""
SELECT ?personId ?personName ?role ?skillName ?proficiency
WHERE {
  ?p a pm:Person ;
     pm:personId ?personId ;
     pm:personName ?personName .
  OPTIONAL { ?p pm:role ?role . }
  OPTIONAL {
    ?p pm:hasSkill ?s .
    ?s pm:skillName ?skillName .
    OPTIONAL { ?s pm:proficiencyLevel ?proficiency . }
  }
}
ORDER BY ?personId
""")
    return _fold_person_skills(rows)


# ──────────────────────────────────────────────────────────────
# Recommendations (Phase 5)
# ──────────────────────────────────────────────────────────────

def get_project_profile(project_id: str) -> dict | None:
    rows = _q(f"""
SELECT ?projectName ?domain ?difficulty ?techStack WHERE {{
  ?p a pm:Project ; pm:projectId "{project_id}" ; pm:projectName ?projectName .
  OPTIONAL {{ ?p pm:projectDomain ?domain . }}
  OPTIONAL {{ ?p pm:difficultyLevel ?difficulty . }}
  OPTIONAL {{ ?p pm:techStack ?techStack . }}
}}
""")
    if not rows:
        return None
    first = rows[0]
    tech_stack = sorted({r["techStack"] for r in rows if r.get("techStack")})
    return {
        "project_id": project_id,
        "project_name": first["projectName"],
        "domain": first.get("domain"),
        "difficulty": first.get("difficulty"),
        "tech_stack": tech_stack,
    }


def _build_requirement_tree(flat: list[dict]) -> list[dict]:
    """req_id 명명규약(REQ-XXX vs REQ-XXX-YYY)으로 대분류/중분류 트리를 구성.

    - 토큰 2개(REQ-XXX) = Large
    - 토큰 3개 이상(REQ-XXX-YYY) = Mid (부모 req_id = REQ-XXX)
    - 부모 없는 Mid는 루트로 승격하여 누락 방지
    - 정렬: req_id 숫자 토큰 기준 오름차순
    """
    larges: dict[str, dict] = {}
    mids_by_parent: dict[str, list[dict]] = {}

    for r in flat:
        req_id = r.get("req_id") or ""
        tokens = req_id.split("-")
        if len(tokens) >= 3:
            parent_id = "-".join(tokens[:2])
            mids_by_parent.setdefault(parent_id, []).append(r)
        else:
            larges[req_id] = {**r, "children": []}

    orphans: list[dict] = []
    for parent_id, mids in mids_by_parent.items():
        if parent_id in larges:
            larges[parent_id]["children"].extend(mids)
        else:
            for m in mids:
                orphans.append({**m, "children": []})

    def _sort_key(req: dict) -> tuple:
        return tuple(
            int(t) if t.isdigit() else t
            for t in (req.get("req_id") or "").split("-")
        )

    for lg in larges.values():
        lg["children"].sort(key=_sort_key)

    roots = list(larges.values()) + orphans
    roots.sort(key=_sort_key)
    return roots


def get_project_detail(project_id: str) -> dict | None:
    rows = _q(f"""
SELECT ?projectName ?projectAmount ?clientName ?projectTheme ?projectDomain ?projectStatus
       ?contractType ?businessType ?budget ?leadCompany ?partnerCompany
       ?startDate ?endDate ?description
       ?googleSlideId ?gitlabProjectId ?gitlabRepoUrl
       ?reqId ?reqName ?reqDescription ?reqType ?reqUserType ?reqPriority ?reqStatus
WHERE {{
  ?proj a pm:Project ;
        pm:projectId "{project_id}" ;
        pm:projectName ?projectName ;
        pm:projectStatus ?projectStatus .
  OPTIONAL {{ ?proj pm:projectAmount ?projectAmount . }}
  OPTIONAL {{ ?proj pm:clientName ?clientName . }}
  OPTIONAL {{ ?proj pm:projectTheme ?projectTheme . }}
  OPTIONAL {{ ?proj pm:contractType ?contractType . }}
  OPTIONAL {{ ?proj pm:businessType ?businessType . }}
  OPTIONAL {{ ?proj pm:budget ?budget . }}
  OPTIONAL {{ ?proj pm:leadCompany ?leadCompany . }}
  OPTIONAL {{ ?proj pm:partnerCompany ?partnerCompany . }}
  OPTIONAL {{ ?proj pm:startDate ?startDate . }}
  OPTIONAL {{ ?proj pm:endDate ?endDate . }}
  OPTIONAL {{ ?proj pm:description ?description . }}
  OPTIONAL {{ ?proj pm:googleSlideId ?googleSlideId . }}
  OPTIONAL {{ ?proj pm:gitlabProjectId ?gitlabProjectId . }}
  OPTIONAL {{ ?proj pm:gitlabRepoUrl ?gitlabRepoUrl . }}
  OPTIONAL {{
    ?req pm:relatedToProject ?proj ;
         pm:requirementId ?reqId .
    OPTIONAL {{ ?req pm:requirementName ?reqName . }}
    OPTIONAL {{ ?req pm:requirementDescription ?reqDescription . }}
    OPTIONAL {{ ?req pm:requirementType ?reqType . }}
    OPTIONAL {{ ?req pm:userType ?reqUserType . }}
    OPTIONAL {{ ?req pm:requirementPriority ?reqPriority . }}
    OPTIONAL {{ ?req pm:requirementStatus ?reqStatus . }}
  }}
}}
""")
    if not rows:
        return None

    first = rows[0]
    partner_companies = sorted({r["partnerCompany"] for r in rows if r.get("partnerCompany")})

    req_map: dict[str, dict] = {}
    for r in rows:
        req_id = r.get("reqId")
        if not req_id:
            continue
        if req_id not in req_map:
            req_map[req_id] = {
                "req_id": req_id,
                "req_name": r.get("reqName"),
                "req_description": r.get("reqDescription"),
                "req_type": r.get("reqType"),
                "user_type": [],
                "req_priority": r.get("reqPriority"),
                "req_status": r.get("reqStatus"),
            }
        ut = r.get("reqUserType")
        if ut and ut not in req_map[req_id]["user_type"]:
            req_map[req_id]["user_type"].append(ut)
    requirements = _build_requirement_tree(list(req_map.values()))

    project_amount = first.get("projectAmount")
    return {
        "project_id": project_id,
        "project_name": first["projectName"],
        "project_amount": int(project_amount) if project_amount is not None else None,
        "client_name": first.get("clientName"),
        "project_theme": first.get("projectTheme"),
        "project_domain": first.get("projectDomain"),
        "project_status": first["projectStatus"],
        "start_date": str(first["startDate"]) if first.get("startDate") else None,
        "end_date": str(first["endDate"]) if first.get("endDate") else None,
        "description": first.get("description"),
        "contract_type": first.get("contractType"),
        "business_type": first.get("businessType"),
        "budget": first.get("budget"),
        "lead_company": first.get("leadCompany"),
        "partner_companies": partner_companies,
        "google_slide_id": first.get("googleSlideId"),
        "gitlab_project_id": first.get("gitlabProjectId"),
        "gitlab_repo_url": first.get("gitlabRepoUrl"),
        "requirements": requirements,
    }


def list_persons_for_matching() -> list[dict]:
    rows = _q("""
SELECT ?personId ?personName ?role ?grade ?availabilityScore ?synergyScore
       ?skillName ?proficiency
WHERE {
  ?p a pm:Person ;
     pm:personId ?personId ;
     pm:personName ?personName .
  OPTIONAL { ?p pm:role ?role . }
  OPTIONAL { ?p pm:grade ?grade . }
  OPTIONAL { ?p pm:availabilityScore ?availabilityScore . }
  OPTIONAL { ?p pm:synergyScore ?synergyScore . }
  OPTIONAL {
    ?p pm:hasSkill ?s .
    ?s pm:skillName ?skillName .
    OPTIONAL { ?s pm:proficiencyLevel ?proficiency . }
  }
}
ORDER BY ?personId
""")
    people: dict[str, dict] = {}
    for r in rows:
        pid = r["personId"]
        person = people.setdefault(pid, {
            "person_id": pid,
            "person_name": r["personName"],
            "role": r.get("role"),
            "grade": r.get("grade"),
            "availability_score": r.get("availabilityScore"),
            "synergy_score": r.get("synergyScore"),
            "skills": [],
        })
        if r.get("skillName"):
            person["skills"].append({
                "name": r["skillName"],
                "proficiency": r.get("proficiency") or 0.0,
            })
    return list(people.values())


def active_task_counts(project_id: str | None = None) -> list[dict]:
    """Person별 IN_PROGRESS/REVIEW Task 수와 avg progress를 계산."""
    project_filter = ""
    if project_id:
        project_filter = f"""
    ?proj pm:projectId "{project_id}" ; pm:hasTask ?t ."""

    rows = _q(f"""
SELECT ?personId ?personName ?role ?availabilityScore
       (COUNT(?t) AS ?activeTasks) (AVG(?progress) AS ?avgProgress)
WHERE {{
  ?p a pm:Person ;
     pm:personId ?personId ;
     pm:personName ?personName .
  OPTIONAL {{ ?p pm:role ?role . }}
  OPTIONAL {{ ?p pm:availabilityScore ?availabilityScore . }}
  OPTIONAL {{
    ?t pm:assignedTo ?p ;
       pm:taskStatus ?status ;
       pm:progressPercent ?progress .
    FILTER(?status = "IN_PROGRESS" || ?status = "REVIEW"){project_filter}
  }}
}}
GROUP BY ?personId ?personName ?role ?availabilityScore
ORDER BY ?personId
""")
    return [
        {
            "person_id": r["personId"],
            "person_name": r["personName"],
            "role": r.get("role"),
            "availability_score": r.get("availabilityScore"),
            "active_tasks": int(r.get("activeTasks") or 0),
            "avg_progress": r.get("avgProgress"),
        }
        for r in rows
    ]


def insert_recommendations(project_id: str, items: list[dict], created_at_iso: str) -> None:
    """Fuseki에 StaffingRecommendation 인스턴스들을 적재.

    items: [{person_id, similarity_score, rank, reason}, ...]
    """
    if not items:
        return

    triples = []
    for it in items:
        raw_reason = it.get("reason") or ""
        reason_safe = (
            raw_reason.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
        )
        rec_local = f"rec_{project_id}_{it['person_id']}_{it['rank']}"
        person_var = f"?p_{it['person_id']}"
        triples.append(
            f"  inst:{rec_local} a pm:StaffingRecommendation ;\n"
            f'    pm:recommendationId "{project_id}-{it["rank"]:02d}" ;\n'
            f"    pm:targetProject ?proj ;\n"
            f"    pm:recommendedPerson {person_var} ;\n"
            f'    pm:similarityScore "{it["similarity_score"]}"^^xsd:decimal ;\n'
            f'    pm:recommendationRank "{it["rank"]}"^^xsd:integer ;\n'
            f'    pm:recommendationReason "{reason_safe}" ;\n'
            f'    pm:createdAt "{created_at_iso}"^^xsd:dateTime .'
        )

    person_binds = "\n  ".join(
        f'?p_{it["person_id"]} pm:personId "{it["person_id"]}" .'
        for it in items
    )
    body = f"""
INSERT {{
{chr(10).join(triples)}
}}
WHERE {{
  ?proj pm:projectId "{project_id}" .
  {person_binds}
}}
"""
    fuseki.update(PREFIX + body)


def get_person_by_id(person_id: str) -> dict | None:
    rows = _q(f"""
SELECT ?personId ?personName ?role ?skillName ?proficiency
WHERE {{
  ?p a pm:Person ;
     pm:personId "{person_id}" ;
     pm:personName ?personName .
  BIND("{person_id}" AS ?personId)
  OPTIONAL {{ ?p pm:role ?role . }}
  OPTIONAL {{
    ?p pm:hasSkill ?s .
    ?s pm:skillName ?skillName .
    OPTIONAL {{ ?s pm:proficiencyLevel ?proficiency . }}
  }}
}}
""")
    folded = _fold_person_skills(rows)
    if not folded:
        return None
    person = folded[0]

    proj_rows = _q(f"""
SELECT ?projectId ?projectName WHERE {{
  ?p pm:personId "{person_id}" ; pm:participatesIn ?proj .
  ?proj pm:projectId ?projectId ; pm:projectName ?projectName .
}}
ORDER BY ?projectId
""")
    person["participates_in"] = [
        {"project_id": r["projectId"], "project_name": r["projectName"]}
        for r in proj_rows
    ]
    return person


# ──────────────────────────────────────────────────────────────
# RFP (Fuseki 저장 — pm:RFP ad-hoc 클래스)
# ──────────────────────────────────────────────────────────────

def _rfp_uri(rfp_id: str) -> URIRef:
    return URIRef(f"{INST}rfp_{rfp_id}")


def rfp_exists(rfp_id: str) -> bool:
    return fuseki.ask(
        PREFIX + f'ASK {{ ?r a pm:RFP ; pm:rfpId "{rfp_id}" }}'
    )


def create_rfp(
    rfp_id: str,
    file_name: str,
    extracted_text: str,
    page_count: int,
    created_at_iso: str,
) -> None:
    g = Graph()
    subj = _rfp_uri(rfp_id)
    g.add((subj, RDF.type, PM.RFP))
    g.add((subj, PM.rfpId, Literal(rfp_id)))
    g.add((subj, PM.fileName, Literal(file_name)))
    g.add((subj, PM.extractedText, Literal(extracted_text)))
    g.add((subj, PM.pageCount, Literal(page_count, datatype=XSD.integer)))
    g.add((subj, PM.rfpStatus, Literal("extracted")))
    g.add((subj, PM.createdAt, Literal(created_at_iso, datatype=XSD.dateTime)))
    _insert_data(g)


def update_rfp_analysis(
    rfp_id: str,
    analysis_json: str,
    project_name: str | None,
    confidence: float | None,
    status: str,
) -> None:
    # 이전 분석 값 제거 (있다면) 후 새 값 삽입
    subj = f"inst:rfp_{rfp_id}"
    delete = f"""
DELETE {{
  {subj} pm:analysisJson ?oldJson .
  {subj} pm:rfpStatus ?oldStatus .
  {subj} pm:projectNameHint ?oldName .
  {subj} pm:confidenceScore ?oldConf .
}}
WHERE {{
  {subj} pm:rfpId "{rfp_id}" .
  OPTIONAL {{ {subj} pm:analysisJson ?oldJson . }}
  OPTIONAL {{ {subj} pm:rfpStatus ?oldStatus . }}
  OPTIONAL {{ {subj} pm:projectNameHint ?oldName . }}
  OPTIONAL {{ {subj} pm:confidenceScore ?oldConf . }}
}}
"""
    fuseki.update(PREFIX + delete)

    g = Graph()
    s = _rfp_uri(rfp_id)
    g.add((s, PM.analysisJson, Literal(analysis_json)))
    g.add((s, PM.rfpStatus, Literal(status)))
    if project_name:
        g.add((s, PM.projectNameHint, Literal(project_name)))
    if confidence is not None:
        g.add((s, PM.confidenceScore, Literal(float(confidence), datatype=XSD.decimal)))
    _insert_data(g)


def mark_rfp_confirmed(rfp_id: str, project_id: str) -> None:
    subj = f"inst:rfp_{rfp_id}"
    delete = f"""
DELETE {{ {subj} pm:rfpStatus ?s . {subj} pm:confirmedProject ?p . }}
WHERE {{ {subj} pm:rfpId "{rfp_id}" .
        OPTIONAL {{ {subj} pm:rfpStatus ?s . }}
        OPTIONAL {{ {subj} pm:confirmedProject ?p . }} }}
"""
    fuseki.update(PREFIX + delete)

    g = Graph()
    s = _rfp_uri(rfp_id)
    g.add((s, PM.rfpStatus, Literal("confirmed")))
    g.add((s, PM.confirmedProject, URIRef(f"{INST}project_{project_id.lower()}")))
    _insert_data(g)


def unmark_rfp_confirmed(rfp_id: str) -> None:
    """confirm 실패 롤백 시 RFP 상태를 analyzed로 되돌립니다."""
    subj = f"inst:rfp_{rfp_id}"
    fuseki.update(f"""
{PREFIX}
DELETE {{ {subj} pm:rfpStatus ?s . {subj} pm:confirmedProject ?p . }}
INSERT {{ {subj} pm:rfpStatus "analyzed" . }}
WHERE {{
  {subj} pm:rfpId "{rfp_id}" .
  OPTIONAL {{ {subj} pm:rfpStatus ?s . }}
  OPTIONAL {{ {subj} pm:confirmedProject ?p . }}
}}
""")
    logger.warning("RFP confirmed 상태 롤백: rfp=%s", rfp_id)


def get_rfp(rfp_id: str) -> dict | None:
    rows = _q(f"""
SELECT ?fileName ?extractedText ?pageCount ?rfpStatus
       ?analysisJson ?confidenceScore ?createdAt ?confirmedProject
WHERE {{
  ?r a pm:RFP ; pm:rfpId "{rfp_id}" .
  OPTIONAL {{ ?r pm:fileName ?fileName . }}
  OPTIONAL {{ ?r pm:extractedText ?extractedText . }}
  OPTIONAL {{ ?r pm:pageCount ?pageCount . }}
  OPTIONAL {{ ?r pm:rfpStatus ?rfpStatus . }}
  OPTIONAL {{ ?r pm:analysisJson ?analysisJson . }}
  OPTIONAL {{ ?r pm:confidenceScore ?confidenceScore . }}
  OPTIONAL {{ ?r pm:createdAt ?createdAt . }}
  OPTIONAL {{ ?r pm:confirmedProject ?confirmedProject . }}
}}
""")
    if not rows:
        return None
    r = rows[0]
    return {
        "rfp_id": rfp_id,
        "file_name": r.get("fileName"),
        "extracted_text": r.get("extractedText"),
        "page_count": int(r["pageCount"]) if r.get("pageCount") is not None else 0,
        "status": r.get("rfpStatus") or "extracted",
        "analysis_json": r.get("analysisJson"),
        "confidence_score": r.get("confidenceScore"),
        "created_at": r.get("createdAt"),
        "confirmed_project": r.get("confirmedProject"),
    }


def list_rfps() -> list[dict]:
    rows = _q("""
SELECT ?rfpId ?fileName ?projectName ?status ?createdAt WHERE {
  ?r a pm:RFP ;
     pm:rfpId ?rfpId ;
     pm:fileName ?fileName ;
     pm:rfpStatus ?status .
  OPTIONAL { ?r pm:projectNameHint ?projectName . }
  OPTIONAL { ?r pm:createdAt ?createdAt . }
}
ORDER BY DESC(?createdAt)
""")
    return [
        {
            "rfp_id": r["rfpId"],
            "file_name": r["fileName"],
            "project_name": r.get("projectName"),
            "status": r.get("status") or "extracted",
            "created_at": r.get("createdAt") or "",
        }
        for r in rows
    ]


# ──────────────────────────────────────────────────────────────
# Project + WBS 확정 적재
# ──────────────────────────────────────────────────────────────

def _project_uri(project_id: str) -> URIRef:
    return URIRef(f"{INST}project_{project_id.lower()}")


def _task_uri(project_id: str, wbs_code: str) -> URIRef:
    safe = wbs_code.replace(".", "_")
    return URIRef(f"{INST}task_{project_id.lower()}_{safe}")


def _skill_uri(name: str) -> URIRef:
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in name.lower())
    return URIRef(f"{INST}skill_{safe}")


def _reqrole_uri(project_id: str, role: str) -> URIRef:
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in role.lower())
    return URIRef(f"{INST}reqrole_{project_id.lower()}_{safe}")


def insert_project_with_wbs(
    project_id: str,
    project: dict,
    wbs: list[dict],
    requirements: list[dict] | None = None,
    required_roles: list[dict] | None = None,
) -> int:
    """Project + Requirement + WBS Task + RequiredRole을 하나의 INSERT DATA 트랜잭션으로 적재.

    Returns: 삽입된 triple 수 (근사치).
    """
    g = Graph()
    proj_uri = _project_uri(project_id)
    g.add((proj_uri, RDF.type, PM.Project))
    g.add((proj_uri, PM.projectId, Literal(project_id)))
    g.add((proj_uri, PM.projectName, Literal(project["project_name"])))
    if project.get("project_amount") is not None:
        g.add((proj_uri, PM.projectAmount, Literal(int(project["project_amount"]), datatype=XSD.integer)))
    if project.get("client_name"):
        g.add((proj_uri, PM.clientName, Literal(project["client_name"])))
    if project.get("project_theme"):
        g.add((proj_uri, PM.projectTheme, Literal(project["project_theme"])))
    if project.get("contract_type"):
        g.add((proj_uri, PM.contractType, Literal(project["contract_type"])))
    if project.get("business_type"):
        g.add((proj_uri, PM.businessType, Literal(project["business_type"])))
    if project.get("budget"):
        g.add((proj_uri, PM.budget, Literal(project["budget"])))
    if project.get("lead_company"):
        g.add((proj_uri, PM.leadCompany, Literal(project["lead_company"])))
    for partner in project.get("partner_companies") or []:
        g.add((proj_uri, PM.partnerCompany, Literal(partner)))
    g.add((proj_uri, PM.projectStatus, Literal("ACTIVE")))
    if project.get("start_date"):
        g.add((proj_uri, PM.startDate, Literal(project["start_date"], datatype=XSD.date)))
    if project.get("end_date"):
        g.add((proj_uri, PM.endDate, Literal(project["end_date"], datatype=XSD.date)))
    if project.get("description"):
        g.add((proj_uri, PM.description, Literal(project["description"])))

    # Requirement 인스턴스들
    req_id_to_uri: dict[str, URIRef] = {}
    for req in requirements or []:
        req_id = req.get("req_id")
        if not req_id:
            continue
        req_uri = URIRef(f"inst:req_{project_id}_{req_id}")
        req_id_to_uri[req_id] = req_uri
        
        g.add((req_uri, RDF.type, PM.Requirement))
        g.add((req_uri, PM.requirementId, Literal(req_id)))
        if req.get("req_name"):
            g.add((req_uri, PM.requirementName, Literal(req["req_name"])))
        if req.get("req_description"):
            g.add((req_uri, PM.requirementDescription, Literal(req["req_description"])))
        # requirement_type 우선, 없으면 레거시 req_category 사용
        req_type_value = req.get("requirement_type") or req.get("req_category")
        if req_type_value:
            g.add((req_uri, PM.requirementType, Literal(req_type_value)))
        for user_type in req.get("user_type") or []:
            g.add((req_uri, PM.userType, Literal(user_type)))
        if req.get("priority"):
            g.add((req_uri, PM.requirementPriority, Literal(req["priority"])))
        g.add((req_uri, PM.requirementStatus, Literal("APPROVED")))
        g.add((req_uri, PM.relatedToProject, proj_uri))

    # Task 인스턴스들
    wbs_code_to_uri: dict[str, URIRef] = {}
    for idx, item in enumerate(wbs, start=1):
        wbs_code = item["wbs_code"]
        task_uri = _task_uri(project_id, wbs_code)
        wbs_code_to_uri[wbs_code] = task_uri
        task_id = f"{project_id}-T{idx:03d}"

        g.add((task_uri, RDF.type, PM.Task))
        g.add((task_uri, PM.taskId, Literal(task_id)))
        g.add((task_uri, PM.taskName, Literal(item["task_name"])))
        g.add((task_uri, PM.wbsCode, Literal(wbs_code)))
        g.add((task_uri, PM.taskStatus, Literal("미진행")))
        g.add((task_uri, PM.progressPercent, Literal(0, datatype=XSD.integer)))
        if item.get("planned_hours") is not None:
            g.add((task_uri, PM.plannedHours,
                   Literal(float(item["planned_hours"]), datatype=XSD.decimal)))
        if item.get("estimated_days") is not None:
            g.add((task_uri, PM.estimatedDays,
                   Literal(float(item["estimated_days"]), datatype=XSD.decimal)))
        if item.get("planned_start"):
            g.add((task_uri, PM.plannedStart, Literal(item["planned_start"])))
        if item.get("planned_end"):
            g.add((task_uri, PM.dueDate, Literal(item["planned_end"])))
        if item.get("assignee_role"):
            g.add((task_uri, PM.assigneeRole, Literal(item["assignee_role"])))
        for deliverable in item.get("deliverables") or []:
            g.add((task_uri, PM.deliverable, Literal(deliverable)))
        for skill in item.get("required_skills") or []:
            g.add((task_uri, PM.requiresSkill, _skill_uri(skill)))
            g.add((_skill_uri(skill), RDF.type, PM.Skill))
            g.add((_skill_uri(skill), PM.skillName, Literal(skill)))

        # Task와 Requirement 연결
        req_id = item.get("req_id")
        if req_id and req_id in req_id_to_uri:
            g.add((task_uri, PM.implementsRequirement, req_id_to_uri[req_id]))

        g.add((proj_uri, PM.hasTask, task_uri))

    # dependsOn 연결
    for item in wbs:
        src = wbs_code_to_uri.get(item["wbs_code"])
        for dep_code in item.get("depends_on") or []:
            dst = wbs_code_to_uri.get(dep_code)
            if src and dst:
                g.add((src, PM.dependsOn, dst))

    # RequiredRole 인스턴스들 (역할별 필요 인원·스킬·M/M)
    for rr in required_roles or []:
        role = (rr.get("role") or "").strip()
        if not role:
            continue
        rr_uri = _reqrole_uri(project_id, role)
        g.add((rr_uri, RDF.type, PM.RequiredRole))
        g.add((rr_uri, PM.roleName, Literal(role)))
        if rr.get("count") is not None:
            g.add((rr_uri, PM.requiredCount, Literal(int(rr["count"]), datatype=XSD.integer)))
        if rr.get("mm") is not None:
            g.add((rr_uri, PM.requiredMM, Literal(float(rr["mm"]), datatype=XSD.decimal)))
        if rr.get("total_days") is not None:
            g.add((rr_uri, PM.requiredTotalDays, Literal(float(rr["total_days"]), datatype=XSD.decimal)))
        if rr.get("total_hours") is not None:
            g.add((rr_uri, PM.requiredTotalHours, Literal(float(rr["total_hours"]), datatype=XSD.decimal)))
        if rr.get("task_count") is not None:
            g.add((rr_uri, PM.requiredTaskCount, Literal(int(rr["task_count"]), datatype=XSD.integer)))
        for skill in rr.get("skills") or []:
            g.add((rr_uri, PM.requiredSkill, Literal(skill)))
        g.add((proj_uri, PM.requiresRole, rr_uri))

    _insert_data(g)
    return len(g)


# ──────────────────────────────────────────────────────────────
# Task 상태 수정
# ──────────────────────────────────────────────────────────────

_ROLE_ALIASES: dict[str, list[str]] = {
    "PM": ["PM", "pm"],
    "기획자": ["기획자", "기획", "PL", "플래너"],
    "개발자": ["개발자", "BE", "FE", "백엔드", "프론트엔드", "frontend", "backend"],
    "UIUX 디자이너": ["UIUX 디자이너", "디자이너", "디자인", "UX", "UI", "UIUX"],
    "QA": ["QA", "qa", "테스터"],
    "DBA": ["DBA", "dba"],
    "인프라": ["인프라", "infra", "DevOps"],
}


def _role_aliases(role: str) -> list[str]:
    """배정 역할명에 해당하는 WBS assigneeRole 후보 목록 반환."""
    for canonical, aliases in _ROLE_ALIASES.items():
        if role in aliases or role == canonical:
            return aliases
    return [role]


def assign_wbs_by_role(project_id: str, assignments: list[dict]) -> int:
    """역할(assigneeRole)이 일치하는 WBS 태스크에 담당자(assignedTo)를 배정하고
    상태를 '미진행'으로 변경한다.

    assignments: [{"person_id": str, "role": str}, ...]
    Returns: 배정된 태스크 수 합계
    """
    total = 0
    for a in assignments:
        person_id = a["person_id"]
        role = a["role"]
        role_values = _role_aliases(role)
        role_in = ", ".join(f'"{r}"' for r in role_values)

        fuseki.update(f"""
{PREFIX}
DELETE {{
  ?t pm:assignedTo ?oldPerson .
  ?t pm:taskStatus ?oldStatus .
}}
INSERT {{
  ?t pm:assignedTo ?person .
  ?t pm:taskStatus "미진행" .
}}
WHERE {{
  ?proj pm:projectId "{project_id}" ;
        pm:hasTask ?t .
  ?t pm:assigneeRole ?assigneeRole ;
     pm:taskStatus ?oldStatus .
  BIND(inst:person_{person_id} AS ?person)
  OPTIONAL {{
    ?t pm:assignedTo ?oldPerson .
  }}
  FILTER(
    ?assigneeRole IN ({role_in})
    &&
    ?oldStatus IN ("미진행", "TODO")
  )
}}
""")

        # 배정된 태스크 수 조회 (상태가 미진행으로 변경된 건수)
        rows = _q(f"""
SELECT (COUNT(?t) AS ?cnt)
WHERE {{
  ?proj pm:projectId "{project_id}" ; pm:hasTask ?t .
  ?t pm:assigneeRole ?assigneeRole ;
     pm:taskStatus ?status .
  FILTER(?assigneeRole IN ({role_in}) && ?status = "미진행")
}}
""")
        cnt = int(rows[0].get("cnt") or 0) if rows else 0
        logger.info(
            "assign_wbs_by_role: project=%s person=%s role=%s matched=%d",
            project_id, person_id, role, cnt,
        )
        total += cnt

    return total


_STATUS_PROGRESS: dict[str, int] = {
    "미진행": 0,
    "진행": 50,
    "완료": 100,
}


def update_task_schedule(
    task_id: str,
    planned_start: str | None,
    planned_end: str | None,
    planned_hours: float | None,
) -> None:
    """태스크의 planned_start / dueDate / plannedHours를 멱등 갱신.

    값이 None이면 해당 필드는 건드리지 않음. 각 필드를 별도 UPDATE로 처리해
    OPTIONAL 변수가 unbound일 때 INSERT만 수행되도록 한다.
    """
    if planned_start is not None:
        fuseki.update(f"""
{PREFIX}
DELETE {{ ?t pm:plannedStart ?old . }}
INSERT {{ ?t pm:plannedStart "{planned_start}"^^xsd:date . }}
WHERE  {{ ?t a pm:Task ; pm:taskId "{task_id}" .
          OPTIONAL {{ ?t pm:plannedStart ?old . }} }}
""")
    if planned_end is not None:
        fuseki.update(f"""
{PREFIX}
DELETE {{ ?t pm:dueDate ?old . }}
INSERT {{ ?t pm:dueDate "{planned_end}"^^xsd:date . }}
WHERE  {{ ?t a pm:Task ; pm:taskId "{task_id}" .
          OPTIONAL {{ ?t pm:dueDate ?old . }} }}
""")
    if planned_hours is not None:
        fuseki.update(f"""
{PREFIX}
DELETE {{ ?t pm:plannedHours ?old . }}
INSERT {{ ?t pm:plannedHours "{float(planned_hours)}"^^xsd:decimal . }}
WHERE  {{ ?t a pm:Task ; pm:taskId "{task_id}" .
          OPTIONAL {{ ?t pm:plannedHours ?old . }} }}
""")


def update_task_status(task_id: str, new_status: str) -> None:
    """Fuseki에서 task의 taskStatus와 progressPercent를 업데이트."""
    new_progress = _STATUS_PROGRESS.get(new_status, 0)
    # taskStatus와 progressPercent를 각각 별도 UPDATE로 처리.
    # OPTIONAL 변수를 DELETE에 쓰면 unbound 시 기존 트리플이 삭제되지 않아 중복 적재됨.
    fuseki.update(f"""
{PREFIX}
DELETE {{ ?t pm:taskStatus ?old . }}
INSERT {{ ?t pm:taskStatus "{new_status}" . }}
WHERE  {{ ?t a pm:Task ; pm:taskId "{task_id}" ; pm:taskStatus ?old . }}
""")
    fuseki.update(f"""
{PREFIX}
DELETE {{ ?t pm:progressPercent ?old . }}
INSERT {{ ?t pm:progressPercent {new_progress} . }}
WHERE  {{ ?t a pm:Task ; pm:taskId "{task_id}" .
          OPTIONAL {{ ?t pm:progressPercent ?old . }} }}
""")


# ──────────────────────────────────────────────────────────────
# Task 단건 추가
# ──────────────────────────────────────────────────────────────

def insert_single_task(
    project_id: str,
    task_id: str,
    wbs_code: str,
    task_name: str,
    planned_start: str | None,
    planned_end: str | None,
    planned_hours: float | None,
    description: str | None,
    assignee_role: str | None = None,
    assignee_person_id: str | None = None,
    estimated_days: float | None = None,
    depends_on_codes: list[str] | None = None,
    req_id: str | None = None,
) -> None:
    """단일 WBS 작업을 Fuseki에 추가. 초기 status = '미진행'."""
    proj_uri = _project_uri(project_id)
    # task_id 기반 URI 사용: wbs_code 기반이면 동일 wbs_code 재생성 시 URI 충돌로 데이터가 덮어쓰지 않고 누적됨
    task_uri = URIRef(f"{INST}task_{task_id.lower()}")
    g = Graph()
    g.add((task_uri, RDF.type, PM.Task))
    g.add((task_uri, PM.taskId, Literal(task_id)))
    g.add((task_uri, PM.wbsCode, Literal(wbs_code)))
    g.add((task_uri, PM.taskName, Literal(task_name)))
    g.add((task_uri, PM.taskStatus, Literal("미진행")))
    g.add((task_uri, PM.progressPercent, Literal(0, datatype=XSD.integer)))
    if planned_start:
        g.add((task_uri, PM.plannedStart, Literal(planned_start)))
    if planned_end:
        g.add((task_uri, PM.dueDate, Literal(planned_end)))
    if planned_hours is not None:
        g.add((task_uri, PM.plannedHours, Literal(float(planned_hours), datatype=XSD.decimal)))
    if estimated_days is not None:
        g.add((task_uri, PM.estimatedDays, Literal(float(estimated_days), datatype=XSD.decimal)))
    if description:
        g.add((task_uri, PM.taskDescription, Literal(description)))
    if assignee_role:
        g.add((task_uri, PM.assigneeRole, Literal(assignee_role)))
    g.add((proj_uri, PM.hasTask, task_uri))
    _insert_data(g)

    # assignee, depends_on 은 URI 조회가 필요하므로 UPDATE로 처리
    if assignee_person_id:
        fuseki.update(f"""
{PREFIX}
INSERT {{ ?t pm:assignedTo ?person . ?t pm:taskStatus "미진행" . }}
WHERE {{
  ?t pm:taskId "{task_id}" .
  OPTIONAL {{ ?person pm:personId "{assignee_person_id}" . }}
}}
""")

    dep_list = [c for c in (depends_on_codes or []) if c]
    if dep_list:
        dep_values = ", ".join(f'"{c}"' for c in dep_list)
        fuseki.update(f"""
{PREFIX}
INSERT {{ ?t pm:dependsOn ?dep . }}
WHERE {{
  ?t pm:taskId "{task_id}" .
  ?dep pm:wbsCode ?depCode .
  FILTER(?depCode IN ({dep_values}))
}}
""")

    if req_id:
        fuseki.update(f"""
{PREFIX}
INSERT {{ ?t pm:implementsRequirement ?req . }}
WHERE {{
  ?t pm:taskId "{task_id}" .
  ?req pm:requirementId "{req_id}" .
}}
""")


# ──────────────────────────────────────────────────────────────
# Dashboard queries
# ──────────────────────────────────────────────────────────────

def get_task_summary(project_id: str | None = None) -> dict:
    """전체 태스크 상태별 카운트. project_id 지정 시 해당 프로젝트만 집계."""
    if project_id:
        proj_filter = f'?proj pm:projectId "{project_id}" ; pm:hasTask ?t .'
        where = f"WHERE {{\n  {proj_filter}\n  ?t pm:taskStatus ?status .\n}}"
    else:
        where = "WHERE {\n  ?t a pm:Task ; pm:taskStatus ?status .\n}"
    rows = _q(f"""
SELECT ?status (COUNT(?t) AS ?cnt)
{where}
GROUP BY ?status
""")
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["status"]] = int(r.get("cnt") or 0)

    total = sum(counts.values())
    completed = counts.get("완료", 0)
    in_progress = counts.get("진행", 0)
    not_started = counts.get("미진행", 0)
    delayed = total - completed - in_progress - not_started
    if delayed < 0:
        delayed = 0
    return {
        "total": total,
        "completed": completed,
        "in_progress": in_progress,
        "delayed": delayed,
        "not_started": not_started,
    }


def get_team_member_count() -> int:
    rows = _q("SELECT (COUNT(DISTINCT ?p) AS ?cnt) WHERE { ?p a pm:Person . }")
    return int(rows[0].get("cnt") or 0) if rows else 0


def list_my_projects(person_name: str) -> list[dict]:
    """로그인 사용자가 담당자인 태스크가 있는 프로젝트 목록."""
    rows = _q(f"""
SELECT ?projectId ?projectName ?domain ?status ?startDate ?endDate
       (COUNT(?t) AS ?taskCount)
       (AVG(?progress) AS ?avgProgress)
WHERE {{
  ?proj a pm:Project ;
        pm:projectId ?projectId ;
        pm:projectName ?projectName ;
        pm:projectStatus ?status ;
        pm:hasTask ?t .
  ?t pm:assignedTo ?person ;
     pm:progressPercent ?progress .
  ?person pm:personName "{person_name}" .
  OPTIONAL {{ ?proj pm:projectDomain ?domain . }}
  OPTIONAL {{ ?proj pm:startDate ?startDate . }}
  OPTIONAL {{ ?proj pm:endDate ?endDate . }}
}}
GROUP BY ?projectId ?projectName ?domain ?status ?startDate ?endDate
ORDER BY ?projectId
""")
    return [
        {
            "project_id": r["projectId"],
            "project_name": r["projectName"],
            "domain": r.get("domain"),
            "status": r["status"],
            "start_date": str(r["startDate"]) if r.get("startDate") else None,
            "end_date": str(r["endDate"]) if r.get("endDate") else None,
            "progress": round(float(r.get("avgProgress") or 0), 1),
            "my_task_count": int(r.get("taskCount") or 0),
        }
        for r in rows
    ]
def list_all_projects() -> list[dict]:
    """모든 프로젝트 목록."""
    rows = _q("""
SELECT ?projectId ?projectName ?domain ?status ?startDate ?endDate ?taskStatus (COUNT(?t) AS ?cnt)
WHERE {
  ?proj a pm:Project ;
        pm:projectId ?projectId ;
        pm:projectName ?projectName ;
        pm:projectStatus ?status ;
        pm:hasTask ?t .
  ?t pm:taskStatus ?taskStatus .
  OPTIONAL { ?proj pm:projectDomain ?domain . }
  OPTIONAL { ?proj pm:startDate ?startDate . }
  OPTIONAL { ?proj pm:endDate ?endDate . }
}
GROUP BY ?projectId ?projectName ?domain ?status ?startDate ?endDate ?taskStatus
ORDER BY ?projectId
""")

    projects: dict[str, dict] = {}
    for r in rows:
        pid = r["projectId"]
        if pid not in projects:
            projects[pid] = {
                "project_id": pid,
                "project_name": r["projectName"],
                "domain": r.get("domain"),
                "status": r["status"],
                "start_date": str(r["startDate"]) if r.get("startDate") else None,
                "end_date": str(r["endDate"]) if r.get("endDate") else None,
                "total": 0,
                "completed": 0,
            }
        cnt = int(r.get("cnt") or 0)
        projects[pid]["total"] += cnt
        if r.get("taskStatus") == "완료":
            projects[pid]["completed"] += cnt

    result = []
    for p in projects.values():
        total = p["total"]
        progress = round(p["completed"] / total * 100, 1) if total > 0 else 0.0
        result.append({
            "project_id": p["project_id"],
            "project_name": p["project_name"],
            "domain": p["domain"],
            "status": p["status"],
            "start_date": p["start_date"],
            "end_date": p["end_date"],
            "progress": progress,
            "my_task_count": total,
        })
    return result


def list_my_todos(person_name: str, project_id: str | None = None) -> list[dict]:
    """로그인 사용자에게 배정된 WBS 태스크 (완료 제외). project_id 지정 시 해당 프로젝트만."""
    proj_filter = f'FILTER(?projectId = "{project_id}")' if project_id else ""
    rows = _q(f"""
SELECT ?projectId ?projectName ?taskId ?taskName ?wbsCode ?status ?progress ?dueDate ?plannedHours
WHERE {{
  ?proj a pm:Project ;
        pm:projectId ?projectId ;
        pm:projectName ?projectName ;
        pm:hasTask ?t .
  ?t pm:taskId ?taskId ;
     pm:taskName ?taskName ;
     pm:wbsCode ?wbsCode ;
     pm:taskStatus ?status ;
     pm:progressPercent ?progress ;
     pm:assignedTo ?person .
  ?person pm:personName "{person_name}" .
  {proj_filter}
  FILTER(?status != "완료")
  OPTIONAL {{ ?t pm:dueDate ?dueDate . }}
  OPTIONAL {{ ?t pm:plannedHours ?plannedHours . }}
}}
ORDER BY ?projectId ?wbsCode
""")
    return [
        {
            "task_id": r["taskId"],
            "task_name": r["taskName"],
            "wbs_code": r["wbsCode"],
            "project_id": r["projectId"],
            "project_name": r["projectName"],
            "status": r["status"],
            "progress": float(r.get("progress") or 0),
            "due_date": r.get("dueDate"),
            "planned_hours": float(r["plannedHours"]) if r.get("plannedHours") else None,
        }
        for r in rows
    ]


def get_progress_by_role(project_id: str | None = None) -> list[dict]:
    """역할별 태스크 완료율. project_id 지정 시 해당 프로젝트만."""
    if project_id:
        where = f"""WHERE {{
  ?proj pm:projectId "{project_id}" ; pm:hasTask ?t .
  ?t pm:taskStatus ?status ;
     pm:assigneeRole ?assigneeRole .
}}"""
    else:
        where = """WHERE {
  ?t a pm:Task ;
     pm:taskStatus ?status ;
     pm:assigneeRole ?assigneeRole .
}"""
    rows = _q(f"""
SELECT ?assigneeRole ?status (COUNT(?t) AS ?cnt)
{where}
GROUP BY ?assigneeRole ?status
ORDER BY ?assigneeRole
""")
    by_role: dict[str, dict] = {}
    for r in rows:
        role = r["assigneeRole"]
        status = r["status"]
        cnt = int(r.get("cnt") or 0)
        entry = by_role.setdefault(role, {"total": 0, "completed": 0, "in_progress": 0})
        entry["total"] += cnt
        if status == "완료":
            entry["completed"] += cnt
        elif status == "진행":
            entry["in_progress"] += cnt

    result = []
    for role, entry in by_role.items():
        total = entry["total"]
        completed = entry["completed"]
        rate = round(completed / total, 2) if total > 0 else 0.0
        result.append({
            "role": role,
            "total_tasks": total,
            "completed": completed,
            "in_progress": entry["in_progress"],
            "completion_rate": rate,
        })
    result.sort(key=lambda x: x["role"])
    return result


def get_team_status(project_id: str | None = None) -> list[dict]:
    """팀원별 진행 중/완료 태스크 수. project_id 지정 시 해당 프로젝트 소속 인원만."""
    if project_id:
        rows = _q(f"""
SELECT ?personId ?personName ?role ?grade ?availabilityScore ?status (COUNT(?t) AS ?cnt)
WHERE {{
  ?p a pm:Person ;
     pm:personId ?personId ;
     pm:personName ?personName ;
     pm:participatesIn ?proj .
  ?proj pm:projectId "{project_id}" .
  OPTIONAL {{ ?p pm:role ?role . }}
  OPTIONAL {{ ?p pm:grade ?grade . }}
  OPTIONAL {{ ?p pm:availabilityScore ?availabilityScore . }}
  OPTIONAL {{
    ?proj pm:hasTask ?t .
    ?t pm:assignedTo ?p ; pm:taskStatus ?status .
  }}
}}
GROUP BY ?personId ?personName ?role ?grade ?availabilityScore ?status
ORDER BY ?personId
""")
    else:
        rows = _q("""
SELECT ?personId ?personName ?role ?grade ?availabilityScore ?status (COUNT(?t) AS ?cnt)
WHERE {
  ?p a pm:Person ;
     pm:personId ?personId ;
     pm:personName ?personName .
  OPTIONAL { ?p pm:role ?role . }
  OPTIONAL { ?p pm:grade ?grade . }
  OPTIONAL { ?p pm:availabilityScore ?availabilityScore . }
  OPTIONAL {
    ?t pm:assignedTo ?p ;
       pm:taskStatus ?status .
  }
}
GROUP BY ?personId ?personName ?role ?grade ?availabilityScore ?status
ORDER BY ?personId
""")
    people: dict[str, dict] = {}
    for r in rows:
        pid = r["personId"]
        person = people.setdefault(pid, {
            "person_id": pid,
            "person_name": r["personName"],
            "role": r.get("role"),
            "grade": r.get("grade"),
            "availability_score": float(r["availabilityScore"]) if r.get("availabilityScore") else None,
            "active_task_count": 0,
            "completed_task_count": 0,
        })
        status = r.get("status")
        cnt = int(r.get("cnt") or 0)
        if status == "완료":
            person["completed_task_count"] += cnt
        elif status in ("진행", "미진행"):
            person["active_task_count"] += cnt
    return list(people.values())


def list_wbs_overview(limit: int = 50, offset: int = 0, project_id: str | None = None) -> tuple[list[dict], int]:
    """전체 WBS 태스크 목록 (페이지네이션). project_id 지정 시 해당 프로젝트만."""
    proj_filter = f'FILTER(?projectId = "{project_id}")' if project_id else ""
    count_q = f"""
SELECT (COUNT(?t) AS ?cnt)
WHERE {{
  ?proj a pm:Project ; pm:projectId ?projectId ; pm:hasTask ?t .
  {proj_filter}
}}""" if project_id else "SELECT (COUNT(?t) AS ?cnt) WHERE { ?t a pm:Task . }"
    count_rows = _q(count_q)
    total = int(count_rows[0].get("cnt") or 0) if count_rows else 0

    rows = _q(f"""
SELECT ?projectId ?projectName ?taskId ?taskName ?wbsCode
       ?assigneeRole ?assigneeName ?status ?progress ?plannedStart ?dueDate ?plannedHours
WHERE {{
  ?proj a pm:Project ;
        pm:projectId ?projectId ;
        pm:projectName ?projectName ;
        pm:hasTask ?t .
  ?t pm:taskId ?taskId ;
     pm:taskName ?taskName ;
     pm:wbsCode ?wbsCode ;
     pm:taskStatus ?status ;
     pm:progressPercent ?progress .
  {proj_filter}
  OPTIONAL {{ ?t pm:assigneeRole ?assigneeRole . }}
  OPTIONAL {{ ?t pm:assignedTo ?person . ?person pm:personName ?assigneeName . }}
  OPTIONAL {{ ?t pm:plannedStart ?plannedStart . }}
  OPTIONAL {{ ?t pm:dueDate ?dueDate . }}
  OPTIONAL {{ ?t pm:plannedHours ?plannedHours . }}
}}
ORDER BY ?projectId ?wbsCode
LIMIT {limit} OFFSET {offset}
""")
    items = [
        {
            "project_id": r["projectId"],
            "project_name": r["projectName"],
            "task_id": r["taskId"],
            "task_name": r["taskName"],
            "wbs_code": r["wbsCode"],
            "assignee_role": r.get("assigneeRole"),
            "assignee_name": r.get("assigneeName"),
            "status": r["status"],
            "progress": float(r.get("progress") or 0),
            "planned_start": r.get("plannedStart"),
            "due_date": r.get("dueDate"),
            "planned_hours": float(r["plannedHours"]) if r.get("plannedHours") else None,
        }
        for r in rows
    ]
    return items, total


def get_project_pm_names(project_id: str) -> list[str]:
    """프로젝트에 participatesIn으로 연결된 PM 역할 Person의 이름 목록을 반환."""
    rows = _q(f"""
SELECT ?personName
WHERE {{
  ?person pm:participatesIn ?proj ;
          pm:role "PM" ;
          pm:personName ?personName .
  ?proj pm:projectId "{project_id}" .
}}
""")
    return [r["personName"] for r in rows if r.get("personName")]


def get_project_required_roles(project_id: str) -> list[dict]:
    """프로젝트의 RequiredRole 인스턴스들을 조회한다.

    RFP 분석/확정 시 적재된 역할별 필요 인원·스킬을 반환.
    각 항목: {"role": str, "count": int|None, "skills": [str], "mm": float|None,
              "total_days": float|None, "total_hours": float|None, "task_count": int|None}
    """
    rows = _q(f"""
SELECT ?roleName ?count ?mm ?totalDays ?totalHours ?taskCount ?skill
WHERE {{
  ?proj pm:projectId "{project_id}" ; pm:requiresRole ?rr .
  ?rr pm:roleName ?roleName .
  OPTIONAL {{ ?rr pm:requiredCount ?count . }}
  OPTIONAL {{ ?rr pm:requiredMM ?mm . }}
  OPTIONAL {{ ?rr pm:requiredTotalDays ?totalDays . }}
  OPTIONAL {{ ?rr pm:requiredTotalHours ?totalHours . }}
  OPTIONAL {{ ?rr pm:requiredTaskCount ?taskCount . }}
  OPTIONAL {{ ?rr pm:requiredSkill ?skill . }}
}}
""")
    role_map: dict[str, dict] = {}
    for r in rows:
        role = r.get("roleName")
        if not role:
            continue
        if role not in role_map:
            role_map[role] = {
                "role": role,
                "count": int(r["count"]) if r.get("count") is not None else None,
                "mm": float(r["mm"]) if r.get("mm") is not None else None,
                "total_days": float(r["totalDays"]) if r.get("totalDays") is not None else None,
                "total_hours": float(r["totalHours"]) if r.get("totalHours") is not None else None,
                "task_count": int(r["taskCount"]) if r.get("taskCount") is not None else None,
                "skills": [],
            }
        skill = r.get("skill")
        if skill and skill not in role_map[role]["skills"]:
            role_map[role]["skills"].append(skill)
    # role 알파벳 정렬로 안정성 확보
    return sorted(role_map.values(), key=lambda x: x["role"])


def get_project_member_names(project_id: str) -> list[str]:
    """프로젝트에 participatesIn으로 연결된 모든 Person 이름(역할 무관)."""
    rows = _q(f"""
SELECT DISTINCT ?personName
WHERE {{
  ?person pm:participatesIn ?proj ;
          pm:personName ?personName .
  ?proj pm:projectId "{project_id}" .
}}
""")
    return [r["personName"] for r in rows if r.get("personName")]


def get_project_integration_ids(project_id: str) -> dict:
    """프로젝트의 googleSlideId, gitlabProjectId를 반환."""
    rows = _q(f"""
SELECT ?slideId ?gitlabId
WHERE {{
  ?proj pm:projectId "{project_id}" .
  OPTIONAL {{ ?proj pm:googleSlideId ?slideId . }}
  OPTIONAL {{ ?proj pm:gitlabProjectId ?gitlabId . }}
}}
LIMIT 1
""")
    r = rows[0] if rows else {}
    return {
        "google_slide_id": r.get("slideId"),
        "gitlab_project_id": r.get("gitlabId"),
    }


def update_project_integration_ids(
    project_id: str,
    google_slide_id: str | None = None,
    gitlab_project_id: str | None = None,
    gitlab_repo_url: str | None = None,
) -> None:
    """프로젝트에 Google Slides ID 및 GitLab 저장소 정보를 저장합니다."""
    proj_uri = _project_uri(project_id)
    triples_delete = []
    triples_insert = []

    if google_slide_id:
        triples_delete.append("?proj pm:googleSlideId ?oldSlideId .")
        triples_insert.append(f'?proj pm:googleSlideId "{google_slide_id}" .')
    if gitlab_project_id:
        triples_delete.append("?proj pm:gitlabProjectId ?oldGitlabId .")
        triples_insert.append(f'?proj pm:gitlabProjectId "{gitlab_project_id}" .')
    if gitlab_repo_url:
        triples_delete.append("?proj pm:gitlabRepoUrl ?oldRepoUrl .")
        triples_insert.append(f'?proj pm:gitlabRepoUrl "{gitlab_repo_url}" .')

    if not triples_insert:
        return

    delete_block = "\n  ".join(triples_delete)
    insert_block = "\n  ".join(triples_insert)
    optional_block = "\n  ".join(f"OPTIONAL {{ {t} }}" for t in triples_delete)

    fuseki.update(f"""
{PREFIX}
DELETE {{
  {delete_block}
}}
INSERT {{
  {insert_block}
}}
WHERE {{
  BIND(<{proj_uri}> AS ?proj)
  {optional_block}
}}
""")
    logger.info(
        "프로젝트 연동 ID 저장: project=%s slide=%s gitlab=%s",
        project_id, google_slide_id, gitlab_project_id,
    )


def delete_project(project_id: str) -> None:
    """프로젝트와 연결된 모든 트리플을 삭제합니다 (롤백용)."""
    proj_uri = _project_uri(project_id)
    fuseki.update(f"""
{PREFIX}
DELETE {{
  <{proj_uri}> ?p ?o .
}}
WHERE {{
  <{proj_uri}> ?p ?o .
}}
""")
    logger.warning("프로젝트 트리플 삭제(롤백): project=%s", project_id)
