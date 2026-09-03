import ast
import os
from pathlib import Path

from dotenv import load_dotenv
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
                        calls = [n.func.attr for n in ast.walk(node) 
                                 if isinstance(n, ast.Call) and hasattr(n.func, "attr")]
                        # Extract the function name and arguments
                    
                        # Store the fact (you can customize this as needed)
                        facts.append((node.name, module_path, calls))
    return facts


def neo4j_connection(driver, facts):
    with driver.session() as session:
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
            print(f"Inserted fact for test: {test_name}")


def main():
    facts = get_repo_path()
    print("Inserting facts into Neo4j...")
    driver = GraphDatabase.driver(uri, auth=(username, password))
    try:
        neo4j_connection(driver, facts)
    finally:
        driver.close()


if __name__ == "__main__":
    main()

