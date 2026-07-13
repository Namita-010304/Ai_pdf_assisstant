import os
import uuid
import json
import shutil
from pathlib import Path
from datetime import datetime

from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, BackgroundTasks, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from dotenv import load_dotenv

load_dotenv() 

from database import get_db, create_tables
from models import Document, Message
from services.pdf_processor import extract_text_from_pdf, chunk_text
from services.vector_store import upsert_chunks, delete_chunks_by_doc, count_chunks, get_collection_info, search_chunks
from services.chat_rag import get_answer
from services.llm_service import LLMService

llm_service = LLMService()

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = FastAPI(
    title="AI PDF Learning Assistant API",
    description="RAG-powered PDF Q&A for students",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    create_tables()


# ─────────────────────────── Schemas ───────────────────────────

class ChatRequest(BaseModel):
    question: str
    language: str = "en"          # "en" or "hi"
    conversation_id: str = ""
    conversation_history: list[dict] = []
    doc_ids: list[int] | None = None


class DeleteResponse(BaseModel):
    message: str


class TranslateRequest(BaseModel):
    text: str
    target_lang: str             # "en" or "hi"


# ─────────────────────────── Endpoints ───────────────────────────

@app.get("/")
async def root():
    return {"status": "ok", "message": "AI PDF Learning Assistant API is running"}


@app.get("/documents")
def list_documents(db: Session = Depends(get_db)):
    docs = db.query(Document).order_by(Document.upload_time.desc()).all()
    return [
        {
            "id": d.id,
            "filename": d.original_name,
            "page_count": d.page_count,
            "chunk_count": d.chunk_count,
            "indexing_status": d.indexing_status,
            "upload_time": d.upload_time.isoformat(),
        }
        for d in docs
    ]


@app.get("/documents/{doc_id}/status")
def get_document_status(doc_id: int, db: Session = Depends(get_db)):
    """Poll this endpoint to check indexing progress for a specific document."""
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    return {
        "id": doc.id,
        "filename": doc.original_name,
        "indexing_status": doc.indexing_status,
        "page_count": doc.page_count,
        "chunk_count": doc.chunk_count,
    }


def _process_pdf_background(file_path: str, doc_id: int, original_name: str, db_url: str):
    """Background task: extract, chunk, embed and store PDF content."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from models import Document

    connect_args = {}
    if db_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    engine = create_engine(db_url, pool_pre_ping=True, connect_args=connect_args)
    SessionBg = sessionmaker(bind=engine)
    db = SessionBg()

    try:
        # Mark as processing
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if doc:
            doc.indexing_status = "processing"
            db.commit()

        print(f"[INFO] Starting PDF processing for doc_id={doc_id}, file={original_name}")
        pages = extract_text_from_pdf(file_path)
        print(f"[INFO] Extracted {len(pages)} pages from {original_name}")

        if not pages:
            raise ValueError("No text could be extracted from the PDF (it may be image-only or corrupted).")

        chunks = chunk_text(pages, doc_id=doc_id, doc_name=original_name)
        print(f"[INFO] Created {len(chunks)} chunks for doc_id={doc_id}")

        if not chunks:
            raise ValueError("PDF yielded no text chunks after splitting.")

        stored_count = upsert_chunks(chunks)

        # Verify storage via Qdrant count
        verified_count = count_chunks(doc_id)
        print(f"[INFO] Verified {verified_count} chunks in Qdrant for doc_id={doc_id}")

        doc = db.query(Document).filter(Document.id == doc_id).first()
        if doc:
            doc.page_count = max((p["page_number"] for p in pages), default=0)
            doc.chunk_count = verified_count
            doc.indexing_status = "ready" if verified_count > 0 else "failed"
            db.commit()
            print(f"[INFO] doc_id={doc_id} marked as '{doc.indexing_status}' with {verified_count} chunks")

    except Exception as e:
        print(f"[ERROR] Background PDF processing failed for doc_id={doc_id}: {e}")
        try:
            doc = db.query(Document).filter(Document.id == doc_id).first()
            if doc:
                doc.indexing_status = "failed"
                db.commit()
        except Exception as inner_e:
            print(f"[ERROR] Could not update indexing_status to failed: {inner_e}")
    finally:
        db.close()


@app.post("/upload")
async def upload_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    safe_name = f"{uuid.uuid4()}_{file.filename}"
    file_path = os.path.join(UPLOAD_DIR, safe_name)

    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    doc = Document(
        filename=safe_name,
        original_name=file.filename,
        file_path=file_path,
        page_count=0,
        chunk_count=0,
        indexing_status="pending",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    from database import DATABASE_URL as db_url
    background_tasks.add_task(
        _process_pdf_background, file_path, doc.id, file.filename, db_url
    )

    return {
        "id": doc.id,
        "filename": file.filename,
        "indexing_status": "pending",
        "message": "PDF uploaded and processing started.",
    }


@app.delete("/documents/{doc_id}")
def delete_document(doc_id: int, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    # Remove from vector store
    try:
        delete_chunks_by_doc(doc_id)
    except Exception:
        pass

    # Remove file from disk
    try:
        if os.path.exists(doc.file_path):
            os.remove(doc.file_path)
    except Exception:
        pass

    db.delete(doc)
    db.commit()
    return {"message": f"Document '{doc.original_name}' deleted successfully."}


@app.post("/chat")
def chat(
    req: ChatRequest,
    db: Session = Depends(get_db),
    x_api_key: str | None = Header(default=None),
):
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    # Warn if any selected docs are still processing
    if req.doc_ids:
        not_ready = []
        for doc_id in req.doc_ids:
            doc = db.query(Document).filter(Document.id == doc_id).first()
            if doc and doc.indexing_status not in ("ready",):
                not_ready.append(f"{doc.original_name} ({doc.indexing_status})")
        if not_ready:
            raise HTTPException(
                status_code=409,
                detail=f"Some documents are not ready yet: {', '.join(not_ready)}. Please wait for indexing to complete."
            )

    conversation_id = req.conversation_id or str(uuid.uuid4())

    try:
        result = get_answer(
            question=req.question,
            language=req.language,
            conversation_history=req.conversation_history,
            doc_ids=req.doc_ids,
            api_key=x_api_key,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI error: {str(e)}")

    # Save messages to DB
    user_msg = Message(
        conversation_id=conversation_id,
        sender="user",
        content=req.question,
        language=req.language,
    )
    bot_msg = Message(
        conversation_id=conversation_id,
        sender="bot",
        content=result["answer"],
        language=req.language,
        citations=json.dumps(result["citations"]),
    )
    db.add_all([user_msg, bot_msg])
    db.commit()

    return {
        "conversation_id": conversation_id,
        "answer": result["answer"],
        "citations": result["citations"],
    }


@app.post("/translate")
def translate(
    req: TranslateRequest,
    x_api_key: str | None = Header(default=None),
):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty.")

    try:
        translated_text = llm_service.translate(
            text=req.text,
            target_lang=req.target_lang,
            api_key=x_api_key,
        )
        return {"translated_text": translated_text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Translation error: {str(e)}")


@app.get("/history")
def get_history(conversation_id: str, db: Session = Depends(get_db)):
    msgs = db.query(Message).filter(
        Message.conversation_id == conversation_id
    ).order_by(Message.timestamp.asc()).all()

    return [
        {
            "sender": m.sender,
            "content": m.content,
            "language": m.language,
            "citations": json.loads(m.citations) if m.citations else [],
            "timestamp": m.timestamp.isoformat(),
        }
        for m in msgs
    ]


# ─────────────────────────── Debug Endpoints ───────────────────────────

@app.get("/debug/qdrant-status")
def debug_qdrant_status():
    """Check how many vectors are stored in Qdrant. Use this to verify embeddings on Render."""
    try:
        info = get_collection_info()
        return {"ok": True, **info}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/debug/search")
def debug_search(
    q: str = Query(..., description="Search query"),
    doc_id: int | None = Query(None, description="Optional doc_id filter"),
    top_k: int = Query(5, description="Number of results"),
    x_api_key: str | None = Header(default=None),
):
    """Raw retrieval test — use to debug why chunks are/aren't being found."""
    try:
        from database import DATABASE_URL
        doc_ids = [doc_id] if doc_id else None
        key = x_api_key or os.getenv("GEMINI_API_KEY", "")
        chunks = search_chunks(query=q, top_k=top_k, doc_ids=doc_ids, api_key=key)
        return {
            "query": q,
            "chunk_count": len(chunks),
            "chunks": [
                {
                    "doc_name": c["doc_name"],
                    "page_number": c["page_number"],
                    "score": round(c["score"], 4),
                    "text_preview": c["text"][:300],
                }
                for c in chunks
            ],
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}
