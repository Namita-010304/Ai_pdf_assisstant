import os
import uuid
import json
import shutil
from pathlib import Path
from datetime import datetime

from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, BackgroundTasks, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from dotenv import load_dotenv

load_dotenv()

from database import get_db, create_tables
from models import Document, Message
from services.pdf_processor import extract_text_from_pdf, chunk_text
from services.vector_store import upsert_chunks, delete_chunks_by_doc
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
            "upload_time": d.upload_time.isoformat(),
        }
        for d in docs
    ]


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
        pages = extract_text_from_pdf(file_path)
        chunks = chunk_text(pages, doc_id=doc_id, doc_name=original_name)
        upsert_chunks(chunks)

        doc = db.query(Document).filter(Document.id == doc_id).first()
        if doc:
            doc.page_count = max((p["page_number"] for p in pages), default=0)
            db.commit()
    except Exception as e:
        print(f"[ERROR] Background PDF processing failed: {e}")
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
