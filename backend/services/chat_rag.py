import os
from google.genai import types
from dotenv import load_dotenv
from services.vector_store import search_chunks
from services.llm_service import LLMService

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
llm_service = LLMService()

SYSTEM_PROMPT = """You are an AI-powered educational assistant that helps students understand their course materials.

CRITICAL RULES:
1. Answer ONLY using information from the provided PDF context below. Never use external knowledge, assumptions, or information not present in the context.
2. You MAY paraphrase, synthesize, and explain information from the context — you do not need a verbatim match.
3. If the context does not contain enough information to answer the question, reply exactly:
   - "I'm sorry, I couldn't find an answer to that in the uploaded documents." (English)
   - "मुझे क्षमा करें, मुझे अपलोड किए गए दस्तावेज़ों में इसका उत्तर नहीं मिला।" (Hindi)
4. Always cite the document name and page number for each piece of information you use.
5. If the user asks in Hindi, respond in Hindi. If in English, respond in English.
6. Never hallucinate, assume, or extrapolate beyond what the context states.
"""


def build_context(chunks: list[dict]) -> str:
    if not chunks:
        return "No relevant content found in the uploaded documents."
    ctx = ""
    for i, chunk in enumerate(chunks, 1):
        ctx += f"\n[Source {i}: {chunk['doc_name']}, Page {chunk['page_number']}]\n{chunk['text']}\n"
    return ctx


def get_answer(
    question: str,
    language: str = "en",
    conversation_history: list[dict] | None = None,
    doc_ids: list[int] | None = None,
    api_key: str | None = None,
) -> dict:
    """
    Main RAG function. Retrieves context and generates an answer from LLM Service.

    Returns:
        {"answer": str, "citations": [...]}
    """
    key = api_key or GEMINI_API_KEY

    # Retrieve relevant chunks
    chunks = search_chunks(query=question, top_k=5, doc_ids=doc_ids, api_key=key)
    print("="*60)
    print("Retrieved", len(chunks), "chunks")

    for c in chunks:
        print(c["score"])
        print(c["doc_name"])
        print(c["page_number"])
        print(c["text"][:200])

    print("="*60)       
    context = build_context(chunks)

    # Language instruction
    lang_instruction = "Please respond in Hindi (Devanagari script)." if language == "hi" else "Please respond in English."

    # Build conversation history for multi-turn context
    history = []
    if conversation_history:
        for msg in conversation_history[-6:]:  # last 3 turns
            role = "user" if msg["sender"] == "user" else "model"
            history.append(types.Content(role=role, parts=[types.Part(text=msg["content"])]))

    prompt = f"""{lang_instruction}

CONTEXT FROM UPLOADED PDFS:
{context}

STUDENT QUESTION: {question}

Please answer strictly from the context. Cite sources at the end."""

    answer_text = llm_service.generate(
        prompt=prompt,
        system_instruction=SYSTEM_PROMPT,
        history=history,
        api_key=key,
    )

    citations = [
        {
            "doc_name": chunk["doc_name"],
            "page_number": chunk["page_number"],
            "snippet": chunk["text"][:200] + "..." if len(chunk["text"]) > 200 else chunk["text"],
            "score": round(chunk["score"], 3),
        }
        for chunk in chunks
    ]

    return {
        "answer": answer_text,
        "citations": citations,
    }
