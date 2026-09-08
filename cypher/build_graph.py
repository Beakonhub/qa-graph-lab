import ast
import json
import os
from pathlib import Path
import collections

from dotenv import load_dotenv
import networkx as nx
from neo4j import GraphDatabase

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env", override=True)

uri = os.getenv("URI")
username = os.getenv("AUTH_USERNAME")
password = os.getenv("AUTH_PASSWORD")

def get_repo_path(path=None):
    """
    Get the repository path from the environment variable REPO_PATH.
    If not set, return a default path.
    """
    repo_path = Path(path or os.getenv("REPO_PATH") or PROJECT_ROOT).expanduser()
    if not repo_path.is_dir():
        raise RuntimeError(f"Repository path does not exist: {repo_path}")

    facts = []
    for root, directories, files in os.walk(repo_path):
        directories[:] = [directory for directory in directories if directory != ".venv"]
        for filename in files:
            if filename.endswith(".py") and filename.startswith("test_"):
                module_path = os.path.join(root, filename)
                with open(module_path, encoding="utf-8") as module_file:
                    tree = ast.parse(module_file.read())
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                        calls = sorted({
                            n.func.attr
                            for n in ast.walk(node)
                            if isinstance(n, ast.Call) and hasattr(n.func, "attr")
                        })
                        # Extract the function name and arguments
                    
                        # Store the fact (you can customize this as needed)
                        facts.append((node.name, module_path, calls))
    unique_facts = {}
    for test_name, module_path, calls in facts:
        unique_facts[(test_name, module_path)] = (test_name, module_path, calls)
    return list(unique_facts.values())


def build_graph(facts):
    graph = nx.DiGraph()
    for test_name, module_path, calls in facts:
        graph.add_node(test_name, type="test", module=module_path)
        for call_name in calls:
            graph.add_node(call_name, type="function")
            graph.add_edge(test_name, call_name)
    return graph


def get_graph_metrics(graph):
    return {
        "top_degree": [
            {"node": node, "degree": degree}
            for node, degree in sorted(
                graph.in_degree(), key=lambda item: item[1], reverse=True
            )[:5]
        ],
        "betweenness": [
            {"node": node, "score": score}
            for node, score in sorted(
                nx.betweenness_centrality(graph).items(),
                key=lambda item: -item[1],
            )[:5]
        ],
        "page_rank": [
            {"node": node, "score": score}
            for node, score in sorted(
                nx.pagerank(graph).items(), key=lambda item: -item[1]
            )[:5]
        ],
    }


def write_facts(facts, metrics, output_path):
    records = [
        {
            "test_name": test_name,
            "module_path": module_path,
            "calls": calls,
        }
        for test_name, module_path, calls in facts
    ]
    output = {"facts": records, "graph_metrics": metrics}
    output_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"Wrote {len(records)} test facts to {output_path}")

## Neo4j connection and fact insertion
def neo4j_connection(driver, facts):
    graph = build_graph(facts)

    with driver.session() as session:
        session.run(
            "CREATE CONSTRAINT module_path_unique IF NOT EXISTS "
            "FOR (m:Module) REQUIRE m.path IS UNIQUE"
        )
        session.run(
            "CREATE CONSTRAINT test_name_unique IF NOT EXISTS "
            "FOR (t:Test) REQUIRE t.name IS UNIQUE"
        )
        session.run(
            "CREATE CONSTRAINT function_name_unique IF NOT EXISTS "
            "FOR (fn:Function) REQUIRE fn.name IS UNIQUE"
        )

## Insert facts into Neo4j database
        for test_name, module_path, call in facts:
            session.run(
                """
                MERGE (m:Module {path: $path})
                MERGE (t:Test {name: $test_name})
                MERGE (t)-[:IN_MODULE]->(m)
                """,
                path=module_path,
                test_name=test_name,
            )
            for call_name in call:
                session.run(
                    """
                    MERGE (t:Test {name: $test})
                    MERGE (fn:Function {name: $fn})
                    MERGE (t)-[:CALLS]->(fn)
                    """,
                    test=test_name,
                    fn=call_name,
                )
                print(f"Processed fact for test: {test_name} | call: {call_name}")

    metrics = get_graph_metrics(graph)
    print("Top by degree:", metrics["top_degree"])
    print("Betweenness:", metrics["betweenness"])
    print("PageRank:", metrics["page_rank"])
    return metrics


def main():
    facts = get_repo_path()
    metrics = get_graph_metrics(build_graph(facts))
    write_facts(facts, metrics, PROJECT_ROOT / "facts.json")
    print("Inserting facts into Neo4j...")
    driver = GraphDatabase.driver(uri, auth=(username, password))
    try:
        neo4j_connection(driver, facts)
    finally:
        driver.close()


if __name__ == "__main__":
    main()