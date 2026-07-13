import { useState, useRef, useEffect, useCallback } from "react";
import "./index.css";
import {
  fetchDocuments,
  uploadPDF,
  deleteDocument,
  sendChat,
  translateText,
  type Document,
  type ChatMessage,
  type Citation,
} from "./api";

// ── Voice Recognition ──────────────────────────────────────────────────────
const SpeechRecognition =
  (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

// ──────────────────────────────────────────────────────────────────────────
export default function App() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [conversationId, setConversationId] = useState<string>(() => crypto.randomUUID());
  const [language, setLanguage] = useState<"en" | "hi">("en");
  const [isLoading, setIsLoading] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [isDragOver, setIsDragOver] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [apiKey, setApiKey] = useState("");
  const [ttsEnabled, setTtsEnabled] = useState(false);
  const [processingDocs, setProcessingDocs] = useState<Set<number>>(new Set());
  const [selectedDocIds, setSelectedDocIds] = useState<Set<number>>(new Set());
  const [translatingIdx, setTranslatingIdx] = useState<number | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const recognitionRef = useRef<any>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Scroll to bottom on new message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  // Load documents on mount
  useEffect(() => {
    loadDocuments();
  }, []);

  // Poll for indexing status updates for documents that are pending/processing
  useEffect(() => {
    if (processingDocs.size === 0) return;
    const interval = setInterval(async () => {
      const docs = await fetchDocuments();
      setDocuments(docs);
      setProcessingDocs((prev) => {
        const updated = new Set(prev);
        docs.forEach((d) => {
          // Stop polling once indexing is complete (success or failure)
          if (d.indexing_status === "ready" || d.indexing_status === "failed") {
            updated.delete(d.id);
          }
        });
        return updated;
      });
    }, 3000);
    return () => clearInterval(interval);
  }, [processingDocs]);

  async function loadDocuments() {
    try {
      const docs = await fetchDocuments();
      setDocuments(docs);
      setSelectedDocIds((prev) => {
        if (prev.size === 0 && docs.length > 0) {
          return new Set(docs.map((d) => d.id));
        }
        const activeIds = new Set(docs.map((d) => d.id));
        return new Set(Array.from(prev).filter((id) => activeIds.has(id)));
      });
    } catch (_) {}
  }

  // ── File Upload ────────────────────────────────────────────────────────
  async function handleFiles(files: FileList | File[]) {
    const pdfs = Array.from(files).filter((f) => f.name.endsWith(".pdf"));
    if (!pdfs.length) return;
    setIsUploading(true);
    try {
      for (const file of pdfs) {
        const result = await uploadPDF(file);
        // Add to processing set — poll until indexing_status changes to ready/failed
        if (result.indexing_status === "pending" || result.indexing_status === "processing") {
          setProcessingDocs((prev) => new Set([...prev, result.id]));
        }
        setSelectedDocIds((prev) => new Set([...prev, result.id]));
      }
      await loadDocuments();
    } catch (e: any) {
      alert(e.message);
    } finally {
      setIsUploading(false);
    }
  }

  async function handleDelete(docId: number) {
    if (!confirm("Delete this document and all its data?")) return;
    try {
      await deleteDocument(docId);
      setDocuments((prev) => prev.filter((d) => d.id !== docId));
      setSelectedDocIds((prev) => {
        const next = new Set(prev);
        next.delete(docId);
        return next;
      });
    } catch (e: any) {
      alert(e.message);
    }
  }

  const toggleDocSelection = (id: number) => {
    setSelectedDocIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const handleSelectAllDocs = () => {
    setSelectedDocIds(new Set(documents.map((d) => d.id)));
  };

  const handleClearDocsSelection = () => {
    setSelectedDocIds(new Set());
  };

  async function handleTranslateMessage(index: number, currentText: string, currentLang: "en" | "hi") {
    const targetLang = currentLang === "hi" ? "en" : "hi";
    setTranslatingIdx(index);
    try {
      const res = await translateText({
        text: currentText,
        target_lang: targetLang,
        apiKey: apiKey || undefined,
      });
      setMessages((prev) => {
        const updated = [...prev];
        updated[index] = {
          ...updated[index],
          content: res.translated_text,
          language: targetLang,
        };
        return updated;
      });
    } catch (e: any) {
      alert("Translation failed: " + e.message);
    } finally {
      setTranslatingIdx(null);
    }
  }

  // ── Chat Send ──────────────────────────────────────────────────────────
  // Check if any selected documents are still being indexed
  const selectedDocsNotReady = documents.filter(
    (d) => selectedDocIds.has(d.id) && d.indexing_status !== "ready"
  );
  const hasIndexingDocs = selectedDocsNotReady.length > 0;

  async function handleSend() {
    const q = question.trim();
    if (!q || isLoading) return;
    if (hasIndexingDocs) {
      alert(`⏳ Please wait — these documents are still being indexed:\n${selectedDocsNotReady.map(d => `• ${d.filename} (${d.indexing_status})`).join("\n")}`);
      return;
    }

    const userMsg: ChatMessage = { sender: "user", content: q, language };
    setMessages((prev) => [...prev, userMsg]);
    setQuestion("");
    setIsLoading(true);

    try {
      const res = await sendChat({
        question: q,
        language,
        conversation_id: conversationId,
        conversation_history: messages,
        doc_ids: selectedDocIds.size > 0 ? Array.from(selectedDocIds) : undefined,
        apiKey: apiKey || undefined,
      });
      setConversationId(res.conversation_id);

      const botMsg: ChatMessage = {
        sender: "bot",
        content: res.answer,
        citations: res.citations,
        language,
      };
      setMessages((prev) => [...prev, botMsg]);

      if (ttsEnabled) speakText(res.answer, language);
    } catch (e: any) {
      setMessages((prev) => [
        ...prev,
        { sender: "bot", content: `⚠️ Error: ${e.message}`, citations: [], language },
      ]);
    } finally {
      setIsLoading(false);
    }
  }

  // ── Text-to-Speech ─────────────────────────────────────────────────────
  function speakText(text: string, lang: string) {
    window.speechSynthesis.cancel();
    const utter = new SpeechSynthesisUtterance(text);
    utter.lang = lang === "hi" ? "hi-IN" : "en-US";
    utter.rate = 0.95;
    window.speechSynthesis.speak(utter);
  }

  // ── Voice Input ────────────────────────────────────────────────────────
  const startRecording = useCallback(() => {
    if (!SpeechRecognition) {
      alert("Speech recognition is not supported in this browser. Please use Google Chrome.");
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = language === "hi" ? "hi-IN" : "en-US";
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;

    let finalTranscript = "";

    recognition.onresult = (event: any) => {
      let interim = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        if (result.isFinal) {
          finalTranscript += result[0].transcript + " ";
        } else {
          interim += result[0].transcript;
        }
      }
      setQuestion(finalTranscript + interim);
    };

    recognition.onerror = (event: any) => {
      console.error("Speech recognition error:", event.error);
      setIsRecording(false);
      if (event.error === "not-allowed" || event.error === "permission-denied") {
        alert("Microphone access denied. Please allow microphone permission in your browser settings and try again.");
      } else if (event.error === "no-speech") {
        alert("No speech detected. Please try again and speak clearly.");
      } else if (event.error === "network") {
        alert("Network error during speech recognition. Please check your internet connection.");
      } else {
        alert(`Speech recognition error: ${event.error}`);
      }
    };

    recognition.onend = () => {
      setIsRecording(false);
    };

    try {
      recognition.start();
      recognitionRef.current = recognition;
      setIsRecording(true);
    } catch (err: any) {
      console.error("Failed to start speech recognition:", err);
      alert("Failed to start speech recognition. Please make sure microphone access is allowed.");
      setIsRecording(false);
    }
  }, [language]);

  const stopRecording = useCallback(() => {
    if (recognitionRef.current) {
      recognitionRef.current.stop();
      recognitionRef.current = null;
    }
    setIsRecording(false);
  }, []);

  // Auto-resize textarea
  function handleTextareaInput(e: React.ChangeEvent<HTMLTextAreaElement>) {
    setQuestion(e.target.value);
    const el = textareaRef.current;
    if (el) { el.style.height = "auto"; el.style.height = el.scrollHeight + "px"; }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); }
  }

  // ── Render ─────────────────────────────────────────────────────────────
  return (
    <div className="app-container">
      {/* Header */}
      <header className="header">
        <div className="header-brand">
          <div className="header-logo">🎓</div>
          <div>
            <div className="header-title">EduAI Assistant</div>
            <div className="header-subtitle">AI-Powered PDF Learning</div>
          </div>
        </div>
        <div className="header-actions">
          <div className="status-badge">
            <div className="status-dot" />
            Online
          </div>
          <button className="btn btn-ghost btn-icon" onClick={() => setShowSettings(true)} title="Settings">⚙️</button>
          <button
            className="btn btn-ghost btn-icon"
            onClick={() => setTtsEnabled((v) => !v)}
            title={ttsEnabled ? "TTS On" : "TTS Off"}
            style={{ color: ttsEnabled ? "#22d3ee" : "" }}
          >
            🔊
          </button>
        </div>
      </header>

      {/* Main layout */}
      <div className="main-layout">
        {/* Sidebar */}
        <aside className="sidebar">
          <div className="sidebar-section">
            <p className="sidebar-title">Upload Materials</p>
            <div
              className={`dropzone${isDragOver ? " drag-over" : ""}`}
              onClick={() => fileInputRef.current?.click()}
              onDragOver={(e) => { e.preventDefault(); setIsDragOver(true); }}
              onDragLeave={() => setIsDragOver(false)}
              onDrop={(e) => { e.preventDefault(); setIsDragOver(false); handleFiles(e.dataTransfer.files); }}
            >
              <div className="dropzone-icon">{isUploading ? "⏳" : "📂"}</div>
              <div className="dropzone-text">
                {isUploading ? "Uploading..." : <><strong>Click or drag</strong> PDF files here</>}
              </div>
            </div>
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf"
              multiple
              style={{ display: "none" }}
              onChange={(e) => e.target.files && handleFiles(e.target.files)}
            />
          </div>

          <div className="sidebar-section" style={{ borderBottom: "none", paddingBottom: 0 }}>
            <p className="sidebar-title" style={{ marginBottom: 4 }}>Documents ({documents.length})</p>
            {documents.length > 0 && (
              <div className="selection-controls">
                <button className="btn-link" onClick={handleSelectAllDocs}>Select All</button>
                <span className="separator">|</span>
                <button className="btn-link" onClick={handleClearDocsSelection}>Clear</button>
              </div>
            )}
          </div>

          <div className="doc-list">
            {documents.length === 0 ? (
              <div style={{ textAlign: "center", padding: "24px 0", color: "var(--text-muted)", fontSize: 13 }}>
                <div style={{ fontSize: 32, marginBottom: 8 }}>📭</div>
                No documents yet.<br />Upload a PDF to get started.
              </div>
            ) : (
              documents.map((doc) => (
                <div 
                  className={`doc-item${selectedDocIds.has(doc.id) ? " selected" : ""}`} 
                  key={doc.id}
                  onClick={() => toggleDocSelection(doc.id)}
                  style={{ cursor: "pointer" }}
                >
                  <input
                    type="checkbox"
                    className="doc-checkbox"
                    checked={selectedDocIds.has(doc.id)}
                    onChange={() => {}} // toggled by parent div click
                    onClick={(e) => e.stopPropagation()}
                  />
                  <div className="doc-icon">📄</div>
                  <div className="doc-info">
                    <div className="doc-name" title={doc.filename}>{doc.filename}</div>
                    {doc.indexing_status === "pending" || doc.indexing_status === "processing" ? (
                      <div className="doc-processing">⏳ {doc.indexing_status === "pending" ? "Queued…" : "Indexing…"}</div>
                    ) : doc.indexing_status === "failed" ? (
                      <div className="doc-processing" style={{ color: "#f87171" }}>❌ Indexing failed — try re-uploading</div>
                    ) : (
                      <div className="doc-meta">
                        ✅ {doc.chunk_count > 0 ? `${doc.chunk_count} chunks` : doc.page_count > 0 ? `${doc.page_count} pages` : "Ready"} · {new Date(doc.upload_time).toLocaleDateString()}
                      </div>
                    )}
                  </div>
                  <button 
                    className="btn-danger btn" 
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDelete(doc.id);
                    }} 
                    title="Delete"
                  >
                    🗑️
                  </button>
                </div>
              ))
            )}
          </div>
        </aside>

        {/* Chat workspace */}
        <main className="chat-area">
          <div className="messages-container">
            {messages.length === 0 ? (
              <div className="welcome-screen">
                <div className="welcome-icon">🎓</div>
                <div className="welcome-title">Welcome to EduAI</div>
                <div className="welcome-subtitle">
                  Upload your study materials and ask any question. I'll answer strictly from your PDFs in both English and Hindi.
                </div>
                <div className="welcome-chips">
                  {["What is this topic about?", "Explain the key concepts", "Give me a summary", "What are the important points?"].map((q) => (
                    <div className="chip" key={q} onClick={() => setQuestion(q)}>{q}</div>
                  ))}
                </div>
              </div>
            ) : (
              messages.map((msg, i) => (
                <div className={`message ${msg.sender}`} key={i}>
                  <div className="message-avatar">
                    {msg.sender === "user" ? "👤" : "🤖"}
                  </div>
                  <div className="message-content">
                    <div className="message-bubble">{msg.content}</div>
                    {msg.sender === "bot" && msg.citations && msg.citations.length > 0 && (
                      <div className="citations">
                        {msg.citations.slice(0, 3).map((c: Citation, ci: number) => (
                          <div className="citation-card" key={ci}>
                            <div className="citation-header">
                              📄 {c.doc_name} · Page {c.page_number}
                            </div>
                            <div className="citation-snippet">{c.snippet}</div>
                          </div>
                        ))}
                      </div>
                    )}
                    {msg.sender === "bot" && (
                      <div className="message-actions">
                        <button className="tts-btn" onClick={() => speakText(msg.content, msg.language || "en")}>
                          🔊 Read aloud
                        </button>
                        <button 
                          className="translate-btn" 
                          disabled={translatingIdx === i}
                          onClick={() => handleTranslateMessage(i, msg.content, msg.language || "en")}
                        >
                          {translatingIdx === i ? "⏳ Translating..." : `🌐 Translate to ${msg.language === "hi" ? "English" : "Hindi"}`}
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              ))
            )}
            {isLoading && (
              <div className="message bot">
                <div className="message-avatar">🤖</div>
                <div className="thinking">
                  <div className="thinking-dots">
                    <span /><span /><span />
                  </div>
                  Thinking…
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Input bar */}
          <div className="input-bar">
            <div className="input-toolbar">
              <div className="lang-toggle">
                <button className={`lang-btn${language === "en" ? " active" : ""}`} onClick={() => setLanguage("en")}>EN</button>
                <button className={`lang-btn${language === "hi" ? " active" : ""}`} onClick={() => setLanguage("hi")}>हि</button>
              </div>
              <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
                {language === "hi" ? "हिंदी में उत्तर देगा" : "Answers in English"}
              </span>
              {isRecording && (
                <div className="voice-wave-container">
                  <span className="bar" />
                  <span className="bar" />
                  <span className="bar" />
                  <span className="bar" />
                  <span className="bar" />
                </div>
              )}
              <div className="spacer" />
              <button
                className={`voice-btn ${isRecording ? "recording" : "idle"}`}
                onClick={isRecording ? stopRecording : startRecording}
                disabled={documents.length === 0 || selectedDocIds.size === 0}
                title={isRecording ? "Stop recording" : "Voice input"}
              >
                {isRecording ? "⏹" : "🎤"}
              </button>
            </div>
            <div className="input-row">
              <textarea
                ref={textareaRef}
                className="text-input"
                placeholder={
                  documents.length === 0
                    ? "Please upload a PDF document in the sidebar first..."
                    : selectedDocIds.size === 0
                    ? "Please check at least one PDF in the sidebar..."
                    : hasIndexingDocs
                    ? "⏳ Waiting for document indexing to finish..."
                    : language === "hi"
                    ? "यहाँ प्रश्न पूछें…"
                    : "Ask a question about your PDFs…"
                }
                value={question}
                onChange={handleTextareaInput}
                onKeyDown={handleKeyDown}
                rows={1}
                disabled={documents.length === 0 || selectedDocIds.size === 0 || hasIndexingDocs}
              />
              <button
                className="btn btn-primary"
                onClick={handleSend}
                disabled={!question.trim() || isLoading || documents.length === 0 || selectedDocIds.size === 0 || hasIndexingDocs}
                style={{ height: 44, paddingLeft: 20, paddingRight: 20 }}
              >
                Send ➤
              </button>
            </div>
          </div>
        </main>
      </div>

      {/* Settings Modal */}
      {showSettings && (
        <div className="modal-overlay" onClick={() => setShowSettings(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-title">⚙️ Settings</div>
            <div className="form-group">
              <label className="form-label">Gemini API Key</label>
              <input
                className="form-input"
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="AIzaSy…"
              />
              <div className="form-hint">
                Leave blank if configured in backend <code>.env</code> file.
                Get yours at <a href="https://aistudio.google.com/app/apikey" target="_blank" rel="noreferrer" style={{ color: "var(--primary)" }}>AI Studio</a>.
              </div>
            </div>
            <div className="modal-actions">
              <button className="btn btn-ghost" onClick={() => setShowSettings(false)}>Cancel</button>
              <button className="btn btn-primary" onClick={() => setShowSettings(false)}>Save</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
