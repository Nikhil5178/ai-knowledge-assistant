import os
import io
import re
from typing import List, Dict, Any

import numpy as np
import faiss
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

APP_NAME = "AI Knowledge Assistant"
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
MAX_FILE_BYTES = int(os.getenv("MAX_FILE_MB", "10")) * 1024 * 1024
CHUNK_SIZE = 900
CHUNK_OVERLAP = 150
TOP_K = 4

app = FastAPI(title=APP_NAME, version="1.0.0", description="A retrieval-augmented document question-answering app.")
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app.mount(
    "/static",
    StaticFiles(directory=str(STATIC_DIR)),
    name="static"
)
# In-memory demo storage: documents are available only while this server process is running.
embedder = None
doc_chunks: List[Dict[str, Any]] = []
faiss_index = None

def get_embedder():
    global embedder

    if embedder is None:
        embedder = SentenceTransformer(EMBEDDING_MODEL)

    return embedder

class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1500)

class AskResponse(BaseModel):
    answer: str
    sources: List[Dict[str, Any]]


def extract_text(filename: str, data: bytes) -> str:
    ext = os.path.splitext(filename.lower())[1]
    try:
        if ext == ".pdf":
            reader = PdfReader(io.BytesIO(data))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        if ext in {".txt", ".md", ".csv"}:
            return data.decode("utf-8", errors="replace")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not read file: {exc}")
    raise HTTPException(status_code=400, detail="Unsupported file type. Upload PDF, TXT, MD, or CSV.")


def split_text(text: str) -> List[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        if end < len(text):
            boundary = text.rfind(" ", start + CHUNK_SIZE // 2, end)
            if boundary > start:
                end = boundary
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(end - CHUNK_OVERLAP, start + 1)
    return chunks


def rebuild_index() -> None:
    global faiss_index

    if not doc_chunks:
        faiss_index = None
        return

    vectors = get_embedder().encode(
        [item["text"] for item in doc_chunks],
        normalize_embeddings=True
    )

    vectors = np.asarray(vectors, dtype="float32")
    faiss_index = faiss.IndexFlatIP(vectors.shape[1])
    faiss_index.add(vectors)


@app.get("/", response_class=HTMLResponse)
def home():
    index_file = STATIC_DIR / "index.html"

    if not index_file.exists():
        raise HTTPException(
            status_code=500,
            detail="Homepage file not found."
        )

    return index_file.read_text(encoding="utf-8")
@app.get("/api/health")
def health():
    return {"status": "ok", "documents_chunks": len(doc_chunks), "llm_configured": bool(os.getenv("GROQ_API_KEY"))}

@app.post("/api/upload")
async def upload_document(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Please choose a file.")
    data = await file.read()
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail=f"File is too large. Maximum size is {MAX_FILE_BYTES // (1024 * 1024)} MB.")
    text = extract_text(file.filename, data)
    chunks = split_text(text)
    if not chunks:
        raise HTTPException(status_code=400, detail="No readable text found. Scanned PDFs need OCR before upload.")
    # Replace chunks for a file with the same name, then append the new content.
    global doc_chunks
    doc_chunks = [c for c in doc_chunks if c["filename"] != file.filename]
    doc_chunks.extend({"filename": file.filename, "chunk_id": i + 1, "text": chunk} for i, chunk in enumerate(chunks))
    rebuild_index()
    return {"message": f"Indexed {len(chunks)} text chunks from {file.filename}.", "filename": file.filename, "chunks": len(chunks), "total_chunks": len(doc_chunks)}

@app.get("/api/documents")
def documents():
    summary: Dict[str, int] = {}
    for chunk in doc_chunks:
        summary[chunk["filename"]] = summary.get(chunk["filename"], 0) + 1
    return {"documents": [{"filename": name, "chunks": count} for name, count in sorted(summary.items())], "total_chunks": len(doc_chunks)}

@app.delete("/api/documents")
def clear_documents():
    global doc_chunks, faiss_index
    doc_chunks = []
    faiss_index = None
    return {"message": "All uploaded documents cleared."}

@app.post("/api/ask", response_model=AskResponse)
def ask(request: AskRequest):
    if not doc_chunks or faiss_index is None:
        raise HTTPException(status_code=400, detail="Upload at least one document before asking a question.")
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="Missing GROQ_API_KEY. Add your Groq API key to the environment variables.")
    query_vector = get_embedder().encode(
    [request.question],
    normalize_embeddings=True
)
    query_vector = np.asarray(query_vector, dtype="float32")
    k = min(TOP_K, len(doc_chunks))
    scores, indices = faiss_index.search(query_vector, k)
    selected = []
    for score, idx in zip(scores[0], indices[0]):
        if idx >= 0:
            item = doc_chunks[int(idx)]
            selected.append({"filename": item["filename"], "chunk_id": item["chunk_id"], "text": item["text"], "score": float(score)})
    context = "\n\n".join(f"[Source: {x['filename']} | chunk {x['chunk_id']}]\n{x['text']}" for x in selected)
    client = Groq(api_key=api_key)
    try:
        completion = client.chat.completions.create(
            model=GROQ_MODEL,
            temperature=0.2,
            messages=[
                {"role": "system", "content": "You are a careful document question-answering assistant. Answer using only the supplied context. If the context does not contain the answer, say you could not find it in the uploaded documents. Do not invent facts. Keep answers clear and concise. Cite supporting sources using [filename, chunk N]."},
                {"role": "user", "content": f"QUESTION:\n{request.question}\n\nDOCUMENT CONTEXT:\n{context}"}
            ],
        )
        answer = completion.choices[0].message.content or "I couldn't generate an answer. Please try again."
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"The language model request failed: {exc}")
    sources = [{"filename": x["filename"], "chunk_id": x["chunk_id"], "score": round(x["score"], 3), "preview": x["text"][:220] + ("…" if len(x["text"]) > 220 else "")} for x in selected]
    return AskResponse(answer=answer, sources=sources)
