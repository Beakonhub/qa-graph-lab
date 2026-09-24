import os
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase
from neo4j_graphrag.embeddings import SentenceTransformerEmbeddings
from neo4j_graphrag.experimental.pipeline.kg_builder import SimpleKGPipeline
from neo4j_graphrag.components.text_splitters.fixed_size_splitter import FixedSizeSplitter


from neo4j_graphrag.llm import AnthropicLLM

PROJECT_ROOT = Path(__file__).resolve().parent.parent
text = Path(PROJECT_ROOT / "todo-requirements.md").read_text()


load_dotenv(Path(__file__).parent / ".env")

driver = GraphDatabase.driver(
    os.environ["NEO4J_URI"],
    auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"]),
)

llm = AnthropicLLM(
    model_name="claude-opus-5",
    api_key=os.environ["API_KEY"],
    model_params={"max_tokens": 8192, "temperature": 0}
)
# neo4j_graphrag's Anthropic structured-output path (open-map property
# restoration) doesn't round-trip correctly for this schema, causing
# "LLM response has improper format" on valid extractions. Fall back to
# plain prompt-based JSON extraction instead.
llm.supports_structured_output = False
embedder = SentenceTransformerEmbeddings()

# your requirements doc is only a few KB — one big chunk, no overlap
splitter = FixedSizeSplitter(chunk_size=50000, chunk_overlap=0)

kg = SimpleKGPipeline(
    llm=llm,                       # your OpenAI/Anthropic/Ollama model
    driver=driver,                 # the neo4j driver you already use
    embedder=embedder,
    entities=["Requirement", "Feature", "TestCase", "Defect", "Component"],
    relations=["IMPLEMENTS", "VERIFIES", "COVERS", "AFFECTS", "FOUND_IN"],
    from_pdf=False,                # ← drop the PDF; pass text
)

ALLOWED = {"Requirement", "Feature", "TestCase", "Defect", "Component"}


def validate_graph():
    FRAMEWORK = {"Document", "Chunk", "__Entity__", "__KGBuilder__"}
    with driver.session() as s:
        total = s.run("MATCH (n) RETURN count(n) AS n").single()["n"]
        assert total > 0, "Empty graph — extraction produced nothing."

        counts = {r["l"]: r["n"] for r in s.run(
            "MATCH (n) UNWIND labels(n) AS l RETURN l, count(*) AS n")}
        print("counts:", counts)

        off = [l for l in counts if l not in FRAMEWORK
               and l not in {"Requirement","Feature","TestCase","Defect","Component"}
               and not l.startswith("__")]
        print("OFF-ONTOLOGY (real hallucinations):", off)

        reqs = counts.get("Requirement", 0)
        print(f"Requirements: {reqs} extracted vs 19 in source",
              "✓" if reqs == 19 else " mismatch — investigate")

        print("Untested requirements:",
              [dict(r) for r in s.run(
                  "MATCH (r:Requirement) WHERE NOT (r)<-[:VERIFIES]-() RETURN r.name")])


async def main():
    await kg.run_async(text=text)
    validate_graph()


if __name__ == "__main__":
    import asyncio

    try:
        asyncio.run(main())
    finally:
        driver.close()
