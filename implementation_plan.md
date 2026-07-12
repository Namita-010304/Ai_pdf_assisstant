# AI-Powered PDF Learning Assistant for Students

Develop an interactive web application that allows teachers/admins to upload course materials as PDFs. The application will extract and index the text of these PDFs, allowing students to query the content using text and voice in both Hindi and English. It will retrieve relevant context using semantic search (Gemini Embeddings) and answer queries using Gemini 1.5 Flash, providing references to the source documents and page numbers.

## Proposed Changes

The project will consist of a **Node.js/Express Backend** and a **Vite/React/TypeScript Frontend**, running concurrently.

---

### Backend (Node.js & Express)

Create a backend server in the workspace directory under a `server` folder.

#### [NEW] [package.json](file:///d:/ai%20powered%20pdf%20assisstant/server/package.json)
Contains project dependencies: `express`, `cors`, `multer` (file upload), `pdfjs-dist` (PDF parsing), `@google/generative-ai` (Gemini SDK), `dotenv`, and `nodemon` (development).

#### [NEW] [index.js](file:///d:/ai%20powered%20pdf%20assisstant/server/index.js)
The main Express server setup:
- Configures middleware (CORS, file parser).
- Creates directories `uploads/` to store PDFs.
- Exposes routes:
  - `POST /api/upload`: Handles PDF upload, parses text page-by-page, generates and indexes text chunks in memory.
  - `GET /api/documents`: List uploaded PDF documents and page counts.
  - `DELETE /api/documents/:name`: Deletes a PDF and its associated chunks from the index.
  - `POST /api/query`: Takes a user prompt, retrieves relevant chunks, calls Gemini for an answer, and returns both the answer and the source references.
- Runs on port 5000.

#### [NEW] [pdfExtractor.js](file:///d:/ai%20powered%20pdf%20assisstant/server/pdfExtractor.js)
Service to extract text page-by-page from incoming PDF files using `pdfjs-dist`. It will divide text into distinct page objects containing:
- `pageNumber`: The page number.
- `text`: Extracted content.

#### [NEW] [vectorStore.js](file:///d:/ai%20powered%20pdf%20assisstant/server/vectorStore.js)
Simple in-memory vector database with JSON persistence:
- Chunking helper: Breaks text into overlapping segments (~600 characters overlapping by ~150).
- Embedding helper: Uses `@google/generative-ai` to retrieve embeddings for each text chunk.
- Query runner: Computes cosine similarity of query embedding with all indexed chunks to retrieve top-$k$ matches.
- Persistence helper: Saves/loads index data to `vector_store.json`.

#### [NEW] [.env](file:///d:/ai%20powered%20pdf%20assisstant/server/.env)
Contains server configuration like `PORT=5000` and `GEMINI_API_KEY`.

---

### Frontend (React + TypeScript + Vite)

Create a frontend app in the workspace directory under a `client` folder.

#### [NEW] [package.json](file:///d:/ai%20powered%20pdf%20assisstant/client/package.json)
Standard Vite-React-TS setup with `lucide-react` for premium icons and layout.

#### [NEW] [src/index.css](file:///d:/ai%20powered%20pdf%20assisstant/client/src/index.css)
Establish the design system:
- Elegant dark mode with CSS glassmorphism, glowing borders, smooth transitions, and responsive grid layouts.
- Vibrant, modern primary accent (`#6366f1` / Indigo) and secondary accent (`#a855f7` / Purple) colors.
- Custom fonts (using Outfit and Inter from Google Fonts).
- Responsive spacing and containers.

#### [NEW] [src/App.tsx](file:///d:/ai%20powered%20pdf%20assisstant/client/src/App.tsx)
The orchestrator of the UI:
- **Header**: Contains title, subtitle, status indicator, and Settings button (to configure backend Gemini API Key if not in `.env`).
- **Sidebar**:
  - Drag-and-drop PDF upload component with file list and size.
  - Lists uploaded documents with their page counts.
  - Interactive deletion buttons.
- **Main Chat Workspace**:
  - Chat window displaying system instructions and conversational messages.
  - Context retention support for multi-turn conversations.
  - Each bot answer lists its search sources (Document Name, Page Number, Context Snippet).
- **Control Bar**:
  - Language toggle switches (English / Hindi).
  - Speech Synthesis (Read answer aloud) toggle.
  - Modern Text Input box.
  - Voice Command button: uses the Web Speech API (`webkitSpeechRecognition`) for Speech-to-Text in English and Hindi. Show sound wave animation when recording.

#### [NEW] [src/api.ts](file:///d:/ai%20powered%20pdf%20assisstant/client/src/api.ts)
Handles API requests to the Node backend (`/api/upload`, `/api/documents`, `/api/query`, `/api/documents/:name`). Supports passing an custom API key in headers if the server does not have one loaded.

---

## Verification Plan

### Automated Verification
Since we do not have an existing testing suite, we will verify using a node script:
- Create a test script `verify_rag.js` in the backend that uploads a sample text/PDF file, processes it, retrieves chunks for a search phrase, and makes a test query against Gemini model.
- Run `node verify_rag.js` to ensure the core query flow, embeddings, and context retrieval operate correctly.

### Manual Verification
1. **Application Launch**: Run backend (`node index.js`) and frontend (`npm run dev`) and navigate to local dev URL via browser utility.
2. **Settings check**: Open settings and input Gemini API key. Ensure connectivity.
3. **Upload validation**: Upload multiple PDFs (simple 1-2 page documents and a larger document). Verify they show up in the document sidebar list with correct page counts.
4. **Q&A accuracy checking**:
   - Ask a question present in the PDF in English. Verify response is generated strictly from the PDF content and provides correct page number.
   - Switch language to Hindi and submit the query. Verify response is generated in Hindi.
5. **Speech Commands**:
   - Click voice command button and speak a query. Confirm text appears in the input and submits.
   - Activate voice output. Ask a question and confirm speaker reads the response aloud.
