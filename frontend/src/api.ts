const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

export interface Document {
  id: number;
  filename: string;
  page_count: number;
  upload_time: string;
}

export interface Citation {
  doc_name: string;
  page_number: number;
  snippet: string;
  score: number;
}

export interface ChatMessage {
  sender: "user" | "bot";
  content: string;
  citations?: Citation[];
  timestamp?: string;
  language?: "en" | "hi";
}

export interface ChatResponse {
  conversation_id: string;
  answer: string;
  citations: Citation[];
}

export async function fetchDocuments(): Promise<Document[]> {
  const res = await fetch(`${API_BASE}/documents`);
  if (!res.ok) throw new Error("Failed to fetch documents");
  return res.json();
}

export async function uploadPDF(file: File): Promise<{ id: number; filename: string; message: string }> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${API_BASE}/upload`, { method: "POST", body: formData });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "Upload failed");
  }
  return res.json();
}

export async function deleteDocument(docId: number): Promise<void> {
  const res = await fetch(`${API_BASE}/documents/${docId}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Delete failed");
}

export async function sendChat(params: {
  question: string;
  language: string;
  conversation_id: string;
  conversation_history: ChatMessage[];
  doc_ids?: number[];
  apiKey?: string;
}): Promise<ChatResponse> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (params.apiKey) headers["x-api-key"] = params.apiKey;

  const res = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      question: params.question,
      language: params.language,
      conversation_id: params.conversation_id,
      conversation_history: params.conversation_history,
      doc_ids: params.doc_ids,
    }),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "Chat error");
  }
  return res.json();
}

export async function translateText(params: {
  text: string;
  target_lang: string;
  apiKey?: string;
}): Promise<{ translated_text: string }> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (params.apiKey) headers["x-api-key"] = params.apiKey;

  const res = await fetch(`${API_BASE}/translate`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      text: params.text,
      target_lang: params.target_lang,
    }),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "Translation error");
  }
  return res.json();
}
