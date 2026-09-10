# QA Graph Lab

This project builds a Neo4j knowledge graph from Python test files and stores graph facts for later analysis.

## Project structure

- `.env` — environment variables for Neo4j credentials and repository path
- `cypher/build_graph.py` — scans Python test files, extracts test names and call relationships, and writes them to Neo4j
- `requirements.txt` — Python dependencies for the project

## Setup

1. Create and activate a virtual environment:

```powershell
cd "C:\Users\user\qa-graph-lab"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Install dependencies:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

3. Configure Neo4j credentials in the root `.env` file:

```env
URI=neo4j+s://<your-instance>.databases.neo4j.io
AUTH_USERNAME=neo4j
AUTH_PASSWORD=<your-password>
REPO_PATH=C:/Users/user/qa-graph-lab
```

## Run the graph builder

From the project root:

```powershell
cd "C:\Users\user\qa-graph-lab\cypher"
..\.venv\Scripts\python.exe build_graph.py
```

This script will:
- locate Python test files in the repository
- parse their AST
- collect test names and function call relationships
- insert those facts into Neo4j

## Notes

- The script skips the `.venv` folder while scanning files.
- The default repository root is the current workspace.
- If `REPO_PATH` is not valid, the script raises a clear error.
- 
## Most load-bearing function
![alt text](<visualisation .png>)

## goto is the chokepoint
<video controls src="goto_observation.mp4" title="Title"></video>
