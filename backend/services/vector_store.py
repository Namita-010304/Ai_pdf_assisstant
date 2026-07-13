import os
import uuid
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct, Filter, FieldCondition,
    MatchValue, MatchAny, FilterSelector, PayloadSchemaType
)
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

QDRANT_PATH = os.getenv("QDRANT_PATH", "./qdrant_db")
QDRANT_URL = os.getenv("QDRANT_URL", "")          # Qdrant Cloud URL
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")  # Qdrant Cloud API Key
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
COLLECTION_NAME = "pdf_chunks"
VECTOR_SIZE = 3072  # gemini-embedding-2 dimension

_client = None
_genai_client = None


def get_genai_client(api_key: str | None = None):
    global _genai_client
    key = api_key or GEMINI_API_KEY
    if _genai_client is None or api_key:
        _genai_client = genai.Client(api_key=key)
    return _genai_client


def get_client() -> QdrantClient:
    global _client
    if _client is None:
        if QDRANT_URL:
            # Cloud mode — Qdrant Cloud
            _client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
        else:
            # Local mode — file-based storage
            _client = QdrantClient(path=QDRANT_PATH)
        _ensure_collection()
    return _client


def _ensure_collection():
    client = _client
    existing = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME in existing:
        try:
            info = client.get_collection(COLLECTION_NAME)
            vectors = info.config.params.vectors
            size = getattr(vectors, "size", None)
            if size is not None and size != VECTOR_SIZE:
                print(f"[INFO] Recreating collection {COLLECTION_NAME} due to vector size mismatch ({size} != {VECTOR_SIZE})")
                client.delete_collection(COLLECTION_NAME)
                existing.remove(COLLECTION_NAME)
        except Exception as e:
            print(f"[WARNING] Size check failed: {e}. Recreating collection.")
            try:
                client.delete_collection(COLLECTION_NAME)
                if COLLECTION_NAME in existing:
                    existing.remove(COLLECTION_NAME)
            except Exception:
                pass

    if COLLECTION_NAME not in existing:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )

    # 👇 ADD THIS (Fix 2)
    try:
        client.create_payload_index(
            collection_name=COLLECTION_NAME,
            field_name="doc_id",
            field_schema=PayloadSchemaType.INTEGER,
        )
    except Exception as e:
        print(f"Payload index already exists: {e}")


def _embed(text: str, api_key: str | None = None) -> list[float]:
    gc = get_genai_client(api_key)
    result = gc.models.embed_content(
        model="gemini-embedding-2",
        contents=text,
        config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT"),
    )
    return result.embeddings[0].values


def _embed_batch(texts: list[str], api_key: str | None = None) -> list[list[float]]:
    if not texts:
        return []
    gc = get_genai_client(api_key)
    result = gc.models.embed_content(
        model="gemini-embedding-2",
        contents=texts,
        config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT"),
    )
    return [e.values for e in result.embeddings]


def _embed_query(text: str, api_key: str | None = None) -> list[float]:
    gc = get_genai_client(api_key)
    result = gc.models.embed_content(
        model="gemini-embedding-2",
        contents=text,
        config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY"),
    )
    return result.embeddings[0].values


def upsert_chunks(chunks: list[dict], api_key: str | None = None) -> int:
    """Embed and store a list of chunks in Qdrant. Returns number of chunks stored."""
    if not chunks:
        print("[WARNING] upsert_chunks called with empty list — nothing to store.")
        return 0

    client = get_client()
    points = []

    print(f"[INFO] Embedding {len(chunks)} chunks...")

    # Batch embedding requests to Gemini (e.g., in groups of 100)
    embed_batch_size = 100
    for i in range(0, len(chunks), embed_batch_size):
        chunk_batch = chunks[i : i + embed_batch_size]
        texts = [c["text"] for c in chunk_batch]
        try:
            vectors = _embed_batch(texts, api_key)
            print(f"[INFO] Embedded batch {i // embed_batch_size + 1}: {len(vectors)} vectors")
        except Exception as e:
            print(f"[ERROR] Batch embedding failed: {e}. Retrying individually as fallback.")
            vectors = []
            for j, t in enumerate(texts):
                try:
                    vectors.append(_embed(t, api_key))
                except Exception as e2:
                    print(f"[ERROR] Individual embed failed for chunk {i+j}: {e2}")
                    raise

        for chunk, vector in zip(chunk_batch, vectors):
            point = PointStruct(
                id=str(uuid.uuid4()),
                vector=vector,
                payload={
                    "doc_id": chunk["doc_id"],
                    "doc_name": chunk["doc_name"],
                    "page_number": chunk["page_number"],
                    "text": chunk["text"],
                }
            )
            points.append(point)

    # Upsert points to Qdrant in batches of 50
    qdrant_batch_size = 50
    for i in range(0, len(points), qdrant_batch_size):
        client.upsert(collection_name=COLLECTION_NAME, points=points[i : i + qdrant_batch_size])
        print(f"[INFO] Upserted batch to Qdrant: points {i+1}–{min(i+qdrant_batch_size, len(points))} of {len(points)}")

    print(f"[INFO] Upsert complete: {len(points)} chunks stored in Qdrant.")
    return len(points)


def search_chunks(query: str, top_k: int = 5, doc_ids: list[int] | None = None, api_key: str | None = None) -> list[dict]:
    """Semantic search for relevant chunks. Optionally filter by document IDs."""
    client = get_client()
    query_vector = _embed_query(query, api_key)

    query_filter = None
    if doc_ids:
        query_filter = Filter(
            must=[FieldCondition(key="doc_id", match=MatchAny(any=doc_ids))]
        )

    # qdrant-client >=1.7 uses query_points; .search() was removed in v1.7+
    response = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        limit=top_k,
        query_filter=query_filter,
        with_payload=True,
    )

    return [
        {
            "doc_id": r.payload["doc_id"],
            "doc_name": r.payload["doc_name"],
            "page_number": r.payload["page_number"],
            "text": r.payload["text"],
            "score": r.score,
        }
        for r in response.points
    ]


def count_chunks(doc_id: int) -> int:
    """Return the number of chunks stored in Qdrant for a given doc_id."""
    client = get_client()
    result = client.count(
        collection_name=COLLECTION_NAME,
        count_filter=Filter(
            must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
        ),
        exact=True,
    )
    return result.count


def get_collection_info() -> dict:
    """Return total vector count and collection status for debugging."""
    client = get_client()
    info = client.get_collection(COLLECTION_NAME)
    return {
        "vectors_count": info.vectors_count,
        "points_count": info.points_count,
        "status": str(info.status),
        "collection": COLLECTION_NAME,
    }


def delete_chunks_by_doc(doc_id: int):
    """Remove all chunks belonging to a document from the vector store."""
    client = get_client()
    client.delete(
        collection_name=COLLECTION_NAME,
        points_selector=FilterSelector(
            filter=Filter(
                must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
            )
        )
    )
