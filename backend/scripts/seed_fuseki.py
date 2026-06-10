"""Fuseki Person 인스턴스 적재 스크립트

실행:
    cd backend
    uv run python scripts/seed_fuseki.py
"""
import pathlib
from app.db import fuseki

TTL_FILE = pathlib.Path(__file__).parent.parent / "db" / "seeds" / "002_persons.ttl"


def seed() -> None:
    ttl = TTL_FILE.read_text(encoding="utf-8")

    # SPARQL INSERT DATA (Turtle 형식 인라인)
    sparql = f"""
INSERT DATA {{
  GRAPH <https://ontology.example.org/instances#persons> {{
{ttl}
  }}
}}
"""
    # Fuseki는 Named Graph INSERT 대신 기본 그래프에 직접 적재
    # rdflib로 파싱 후 N-Triples로 변환해서 INSERT DATA
    from rdflib import Graph as RdfGraph
    g = RdfGraph()
    g.parse(data=ttl, format="turtle")
    nt = g.serialize(format="nt")

    fuseki.update(f"INSERT DATA {{\n{nt}\n}}")
    print(f"✓ {len(g)} 트리플 적재 완료 ({TTL_FILE.name})")

    # 적재 확인
    from app.db.sparql_repo import list_persons_for_matching
    persons = list_persons_for_matching()
    print(f"\n적재된 Person: {len(persons)}명")
    for p in persons:
        print(f"  {p['person_id']:8s} | {p['role']:12s} | {p['person_name']} | 가용성: {p.get('availability_score')}")


if __name__ == "__main__":
    seed()
