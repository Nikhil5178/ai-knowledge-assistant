# Knowly — AI Knowledge Assistant

A full-stack Retrieval-Augmented Generation (RAG) application that lets users upload documents and ask questions grounded in their content. Built with FastAPI, Sentence Transformers, FAISS, Groq, and vanilla HTML/CSS/JavaScript.

## Features

- Upload PDF, TXT, Markdown, and CSV files
- Extract and chunk text, then create semantic embeddings
- Retrieve relevant chunks with FAISS similarity search
- Generate context-grounded answers through the Groq API
- Display source filenames, chunk numbers, and similarity scores
- Clear uploaded documents from the active session
- Responsive frontend and FastAPI health endpoint

## Architecture

1. **Ingestion:** FastAPI accepts a file and extracts text (PyPDF for PDFs).
2. **Chunking:** Text is split into overlapping chunks.
3. **Embeddings:** `sentence-transformers/all-MiniLM-L6-v2` creates normalized vectors.
4. **Retrieval:** FAISS inner-product search retrieves the most relevant chunks.
5. **Generation:** Groq chat completion answers using retrieved context and includes source references.

## Run locally

Requires Python 3.11 recommended.

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS/Linux:
# source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure the model API key
# Copy .env.example to .env and replace the placeholder with your Groq API key.
# python-dotenv loads the .env file automatically. Never commit it to GitHub.

# 4. Start the server
uvicorn main:app --reload
```

Open `http://127.0.0.1:8000`. API documentation is available at `http://127.0.0.1:8000/docs`.

Get a Groq API key from the official Groq Console: https://console.groq.com/keys. Keep the key private and never commit it to GitHub.

## Deploy on Render

1. Push this folder to a new GitHub repository.
2. In Render, create a **New Web Service** and connect the repository.
3. Build command: `pip install -r requirements.txt`
4. Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Add environment variable `GROQ_API_KEY` in Render's Environment settings.
6. Deploy and wait for the first build. The embedding model download can make the first build/start slower.

You can also use the included `render.yaml` as a starting point for a Blueprint deployment.

## API endpoints

- `GET /api/health` — service health and configuration status
- `POST /api/upload` — upload one document (`multipart/form-data`, field `file`)
- `GET /api/documents` — list indexed documents
- `DELETE /api/documents` — clear the active in-memory index
- `POST /api/ask` — ask a question (`{"question":"..."}`)

## Important limitations

- **Ephemeral in-memory storage:** uploaded content and FAISS index are lost when the process restarts or the deployment sleeps/restarts. This starter project does not use persistent storage or a database for vectors.
- **Single-process demo:** the index is in memory and is not designed for multiple workers or concurrent users. Documents uploaded by users share the same process-level index.
- **Scanned PDFs:** text extraction only; scanned/image-only PDFs need OCR first.
- **API requirement:** question answering requires a valid `GROQ_API_KEY`; uploads and indexing can work without it.
- **Privacy:** do not upload confidential or sensitive documents to a public demo. Uploaded document text is sent to the configured LLM provider when asking questions.
- **Hallucinations:** answers may still be imperfect; verify important information against cited source chunks.

## Suggested next improvements

- Add authentication and per-user document isolation
- Persist files and vectors using PostgreSQL/pgvector or a vector database
- Add OCR for scanned PDFs
- Add tests, logging, rate limits, and file-content scanning
- Add streaming responses and conversation history

## License

MIT — add a `LICENSE` file if you plan to distribute this project publicly.
