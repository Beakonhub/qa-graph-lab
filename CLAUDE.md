# QA Graph Lab

Neo4j knowledge-graph experiments for QA/test intelligence. Three independent pipelines:
- `cypher/build_graph.py` — parses Python `test_*.py` files with `ast`, builds a test→function call graph, writes it to Neo4j and to `facts.json`.
- `cypher/todo+ontology.py` — extracts a requirements ontology from `todo-requirements.md` into Neo4j using `neo4j_graphrag`'s `SimpleKGPipeline` with an Anthropic LLM. Non-deterministic (LLM-driven extraction); use `validate_graph()`'s off-ontology / count checks to catch drift between runs.
- `cypher/load_graph_deterministic.py` — parses the same kind of requirements doc (default `todo-app-requirements.md`, override with `--doc <path>`) by reading its markdown **tables** directly, no LLM involved. Deterministic and idempotent — same input always produces the same graph. Supports `--dry-run` to parse and print without touching Neo4j.

## Environment

- Windows 11. PowerShell is the primary shell; Git Bash is also available.
- Virtualenv at `.venv`, Python 3.10. Run scripts with `.venv\Scripts\python.exe` (or `..\.venv\Scripts\python.exe` from `cypher/`) — a bare `python` may resolve to a different interpreter without the project's packages.

## Environment variables — two separate `.env` files, check which one a script loads

- Root `.env` (loaded by `build_graph.py` via `load_dotenv(PROJECT_ROOT / ".env")`): `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `REPO_PATH`.
- `cypher/.env` (loaded by `todo+ontology.py`): `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`, `AURA_INSTANCEID`, `AURA_INSTANCENAME`, `API_KEY`.
- The key names now line up between the two files, but they're still loaded independently — a value changed in one `.env` has no effect on the other. Before wiring new env-dependent code into either script, check which `.env` its `load_dotenv()` call actually points at.
- Previously the root `.env` used `URI`/`AUTH_USERNAME`/`AUTH_PASSWORD` while `build_graph.py` read `os.environ["NEO4J_URI"]` — a straight `KeyError`. Fixed by renaming the root `.env` keys to `NEO4J_*` and having `build_graph.py::main()` reuse the module-level `uri`/`username`/`password` vars instead of re-reading `os.environ` with different names. If you see `KeyError` on a Neo4j credential again, this is the first place to check.

## Coding conventions

- **`neo4j` driver sessions**: always give `with driver.session() as s:` a real indented block covering everything that uses `s`. A one-line `with x: stmt` closes the session as soon as that statement finishes — any `s.run(...)` after it raises `neo4j.exceptions.SessionError: Session closed`.
- **Imports from `neo4j_graphrag`**: import from the stable namespace, e.g. `neo4j_graphrag.components.text_splitters.fixed_size_splitter`, not `neo4j_graphrag.experimental.components...` — the experimental path is deprecated and being removed in 2.0.
- Always close the driver in a `finally` block (see `build_graph.py::main`, `todo+ontology.py`'s `__main__` guard).
- Use `MERGE`, not `CREATE`, for nodes/relationships that may already exist, matching the existing Cypher in `build_graph.py`.

## Ontology rules (todo+ontology.py)

- Allowed node labels: `Requirement, Feature, TestCase, Defect, Component`. Framework-internal labels (`Document, Chunk, __Entity__, __KGBuilder__`, anything starting with `__`) are expected, not hallucinations.
- Allowed relationship types: `IMPLEMENTS, VERIFIES, COVERS, AFFECTS, FOUND_IN`.
- If the `entities`/`relations` lists passed to `SimpleKGPipeline` change, update `ALLOWED` and `FRAMEWORK` in `validate_graph()` to match, or the off-ontology check will misreport.

## Deliberate workarounds — do not remove without checking why

- `llm.supports_structured_output = False` in `todo+ontology.py`: `neo4j_graphrag`'s Anthropic structured-output path doesn't round-trip this schema correctly and raises "LLM response has improper format" on otherwise-valid extractions. Falls back to plain prompt-based JSON extraction instead.

## Running things

- Build the test-call graph: `cd cypher; ..\.venv\Scripts\python.exe build_graph.py`
- Build the requirements ontology graph (LLM-based): `cd cypher; ..\.venv\Scripts\python.exe "todo+ontology.py"`
- Build the requirements graph deterministically (no LLM): `cd cypher; ..\.venv\Scripts\python.exe load_graph_deterministic.py --dry-run` (parse-only) or without `--dry-run` to load into Neo4j.
