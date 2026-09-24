#!/usr/bin/env python3
"""
Deterministic loader: parse the requirements markdown TABLES and MERGE the
traceability graph. No LLM — exact, idempotent, same result every run.

Usage:
    python load_graph_deterministic.py --dry-run   # parse + print, no DB needed
    python load_graph_deterministic.py             # load into Neo4j + validate
"""
import os
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
# Default: requirements doc sits next to this script. Override with --doc <path>.
DEFAULT_DOC = SCRIPT_DIR / "todo-app-requirements.md"

def resolve_doc_path(argv):
    if "--doc" in argv:
        return Path(argv[argv.index("--doc") + 1]).expanduser()
    return DEFAULT_DOC

# ---------- parsing (pure, no DB) ----------

def parse_md_tables(md: str):
    """Split markdown into tables. Each table -> {'header':[...], 'rows':[{col:val}]}."""
    blocks, cur = [], []
    for line in md.splitlines():
        if line.strip().startswith("|"):
            cur.append(line.strip())
        elif cur:
            blocks.append(cur); cur = []
    if cur:
        blocks.append(cur)

    tables = []
    for block in blocks:
        grid = [[c.strip() for c in row.strip("|").split("|")] for row in block]
        if len(grid) < 3:
            continue
        header = grid[0]
        # grid[1] is the |---|---| separator; data starts at grid[2]
        rows = [dict(zip(header, r)) for r in grid[2:] if len(r) == len(header)]
        tables.append({"header": header, "rows": rows})
    return tables

def clean(v):
    return v.strip().strip("`").strip() if v else v

def col(row, *substrings, exact=None):
    """Fetch a cell by header exact-match (preferred) or case-insensitive substring."""
    if exact:
        for k in row:
            if k.strip().lower() == exact.lower():
                return clean(row[k])
    for k in row:
        if any(s.lower() in k.lower() for s in substrings):
            return clean(row[k])
    return None

def find_table(tables, *header_hints):
    for t in tables:
        joined = " ".join(t["header"]).lower()
        if all(h.lower() in joined for h in header_hints):
            return t["rows"]
    return []

# ---------- build triples ----------

def build(md: str):
    tables = parse_md_tables(md)
    features = find_table(tables, "Feature ID")
    requirements = find_table(tables, "Req ID")
    defects = find_table(tables, "Defect ID")

    nodes = {"Feature": set(), "Requirement": set(), "TestCase": set(),
             "Defect": set(), "Component": set()}
    rels = []  # (label_a, id_a, REL, label_b, id_b)

    for r in features:
        fid = col(r, exact="Feature ID")
        if fid:
            nodes["Feature"].add(fid)

    for r in requirements:
        rid = col(r, "Req ID")
        feat = col(r, exact="Feature") or col(r, "Feature")
        tc = col(r, "Verified", "TestCase")
        if not rid:
            continue
        nodes["Requirement"].add(rid)
        if feat:
            nodes["Feature"].add(feat)
            rels.append(("Feature", feat, "IMPLEMENTS", "Requirement", rid))
        if tc:
            nodes["TestCase"].add(tc)
            rels.append(("TestCase", tc, "VERIFIES", "Requirement", rid))
            if feat:
                rels.append(("TestCase", tc, "COVERS", "Feature", feat))

    # every non-auth feature requires the auth feature
    auth = next((f for f in nodes["Feature"] if "AUTH" in f.upper()), None)
    if auth:
        for f in nodes["Feature"]:
            if f != auth:
                rels.append(("Feature", f, "REQUIRES", "Feature", auth))

    for r in defects:
        did = col(r, "Defect ID")
        comp = col(r, "Found in", "Component")
        rel_req = col(r, "Related Requirement")
        if not did:
            continue
        nodes["Defect"].add(did)
        if comp:
            nodes["Component"].add(comp)
            rels.append(("Defect", did, "FOUND_IN", "Component", comp))
        if rel_req:
            rels.append(("Defect", did, "AFFECTS", "Requirement", rel_req))

    return nodes, rels

# ---------- load + validate ----------

def load_and_validate(nodes, rels):
    from dotenv import load_dotenv
    from neo4j import GraphDatabase
    load_dotenv(Path(__file__).parent / ".env")
    driver = GraphDatabase.driver(
        os.environ["NEO4J_URI"],
        auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"]),
    )
    try:
        with driver.session() as s:
            s.run("MATCH (n) DETACH DELETE n")  # clean slate for a fair count
            for label, ids in nodes.items():
                for _id in ids:
                    s.run(f"MERGE (n:{label} {{id:$id}})", id=_id)  # label from our own set, safe
            for la, ia, rel, lb, ib in rels:
                s.run(
                    f"MATCH (a:{la} {{id:$ia}}), (b:{lb} {{id:$ib}}) "
                    f"MERGE (a)-[:{rel}]->(b)", ia=ia, ib=ib)

            # ---- validation ----
            total = s.run("MATCH (n) RETURN count(n) AS n").single()["n"]
            assert total > 0, "empty graph"
            counts = {r["l"]: r["n"] for r in s.run(
                "MATCH (n) UNWIND labels(n) AS l RETURN l, count(*) AS n")}
            print("counts:", counts)
            reqs = counts.get("Requirement", 0)
            print(f"Requirements: {reqs} vs 19 expected",
                  "OK" if reqs == 19 else "MISMATCH")
            print("Untested requirements:",
                  [r["id"] for r in s.run(
                      "MATCH (r:Requirement) WHERE NOT (r)<-[:VERIFIES]-(:TestCase) "
                      "RETURN r.id AS id")])
    finally:
        driver.close()

def get_driver():
    from dotenv import load_dotenv
    from neo4j import GraphDatabase
    load_dotenv(Path(__file__).parent / ".env")
    return GraphDatabase.driver(
        os.environ["NEO4J_URI"],
        auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"]),
    )

def query_graph(driver):
    with driver.session() as s:
        s.run(
            "MATCH (:TestCase {id: $test_id})-"
            "[v:VERIFIES]->(:Requirement {id: $requirement_id}) "
            "DELETE v",
            test_id="TC-007",
            requirement_id="REQ-007",
        )
        
def query_test_requirements(driver):
    with driver.session() as s:
        for r in s.run(
            "MATCH (r:Requirement) "
            "WHERE NOT (r)<-[:VERIFIES]-(:TestCase) "
            "RETURN r.id AS untested"
        ):
            print("Untested:", r["untested"])

def query_test_repair(driver):
    with driver.session() as s:
        s.run(
            "MATCH (t:TestCase {id:'TC-007'}), (r:Requirement {id:'REQ-007'}) "
            "MERGE (t)-[:VERIFIES]->(r)"
        ) 

# ---------- main ----------

if __name__ == "__main__":
    if "--break-link" in sys.argv:
        driver = get_driver()
        try:
            query_graph(driver)
            print("Deleted VERIFIES edge TC-007 -> REQ-007")
        finally:
            driver.close()
        sys.exit(0)

    if "--check-untested" in sys.argv:
        driver = get_driver()
        try:
            query_test_requirements(driver)
            print("Checked for untested requirements", query_test_requirements)
        finally:
            driver.close()
        sys.exit(0)

    if "--repair-link" in sys.argv:
        driver = get_driver()
        try:
            query_test_repair(driver)
            print("Restored VERIFIES edge TC-007 -> REQ-007")
        finally:
            driver.close()
        sys.exit(0)

    doc_path = resolve_doc_path(sys.argv)
    if not doc_path.exists():
        sys.exit(f"Requirements doc not found: {doc_path}\n"
                 f"Put it next to this script, or pass --doc <path>.")
    md = doc_path.read_text()
    print(f"Source: {doc_path}")
    nodes, rels = build(md)
    print("Parsed nodes:", {k: len(v) for k, v in nodes.items()})
    print("Parsed relationships:", len(rels))
    if "--dry-run" in sys.argv:
        from collections import Counter
        print("rel types:", dict(Counter(r[2] for r in rels)))
        untested = nodes["Requirement"] - {b for (_, _, rel, _, b) in rels if rel == "VERIFIES"}
        print("Untested (from parse):", sorted(untested))
    else:
        load_and_validate(nodes, rels)
