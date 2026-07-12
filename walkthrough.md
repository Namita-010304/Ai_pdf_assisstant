# AI-Powered PDF Learning Assistant — Walkthrough

## What Was Built & Changed

### Backend (Python + FastAPI)

| File | Change |
|------|--------|
| [chat_rag.py](file:///d:/ai%20powered%20pdf%20assisstant/backend/services/chat_rag.py) | Upgraded `SYSTEM_PROMPT` for strict zero-hallucination — returns exact "not found" message in English or Hindi |
| [vector_store.py](file:///d:/ai%20powered%20pdf%20assisstant/backend/services/vector_store.py) | Switched embedding model to `gemini-embedding-2` (3072-dim), migrated from deprecated `.search()` to `.query_points()`, added `FilterSelector` for document deletes, added auto-collection recreation on dimension mismatch |
| [main.py](file:///d:/ai%20powered%20pdf%20assisstant/backend/main.py) | Added `TranslateRequest` schema and `POST /translate` endpoint for real-time Hindi↔English translation via Gemini |

### Frontend (React + TypeScript)

| File | Change |
|------|--------|
| [api.ts](file:///d:/ai%20powered%20pdf%20assisstant/frontend/src/api.ts) | Added `translateText()` client function |
| [App.tsx](file:///d:/ai%20powered%20pdf%20assisstant/frontend/src/App.tsx) | Added PDF checkbox selection, "Select All / Clear" controls, per-message translate button, voice waveform bars, context-aware placeholder text, and disabled inputs when no docs selected |
| [index.css](file:///d:/ai%20powered%20pdf%20assisstant/frontend/src/index.css) | Added styles for: selected doc glow border, checkboxes, translate button, message-actions row, and animated soundwave bars |

---

## Verification Results ✅

All 5 automated backend tests passed:

| Test | Query | Result |
|------|-------|--------|
| 1 — In-context EN | "Who devised Schrödinger's cat?" | ✅ Correct answer with page citation |
| 2 — In-context HI | "What is superposition?" | ✅ Full Hindi answer with citation |
| 3 — Out-of-context EN | "What is the capital of France?" | ✅ `"I'm sorry, I couldn't find an answer..."` |
| 4 — Out-of-context HI | "Who is the Prime Minister of India?" | ✅ Hindi not-found message |
| 5 — Translation | English → Hindi | ✅ Accurate Hindi translation |

---

## How to Run the Application

### Backend
```powershell
cd "d:\ai powered pdf assisstant\backend"
..\venv\Scripts\python -m uvicorn main:app --reload --port 8000
```
➡ API running at **http://localhost:8000**
➡ API docs at **http://localhost:8000/docs**

### Frontend
```powershell
cd "d:\ai powered pdf assisstant\frontend"
npm run dev
```
➡ App running at **http://localhost:3000**

---

## Feature Guide

| Feature | How to Use |
|---------|-----------|
| **Upload PDFs** | Drag & drop or click the upload area in the left sidebar |
| **Select PDFs to Query** | Check/uncheck document checkboxes — only selected PDFs are searched |
| **Ask a Question (Text)** | Type in the input box and press Enter or click Send |
| **Ask a Question (Voice)** | Click the 🎤 mic button, speak, watch the wave animation |
| **Switch Language** | Click `EN` or `हि` toggle above the input box |
| **Translate a Response** | Click `🌐 Translate to Hindi/English` under any bot reply |
| **Read Aloud** | Click `🔊 Read aloud` under any bot reply |
| **View Sources** | Citation cards appear below each bot answer showing PDF name + page |
| **Delete a PDF** | Click 🗑️ button on any document card in the sidebar |

> [!IMPORTANT]
> Make sure your Gemini API Key is set in `backend/.env` as `GEMINI_API_KEY=...`
> and your MySQL server is running before starting the backend.
