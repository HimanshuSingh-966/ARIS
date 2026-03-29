# Pharma RAG - Regulatory Intelligence Platform

Pharma RAG is a comprehensive full-stack application designed to instantly search, analyze, and cite regulatory guidelines and forms across the US FDA, EMA, and India CDSCO.

It is powered by a high-end React (Vite) frontend with a beautiful **Landio-inspired Dark Mode** aesthetic, and a robust **FastAPI backend** running an advanced RAG pipeline via LangChain, Gemini 2.0, and Supabase pgvector.

## 🏗 Architecture

- **Frontend:** React + Vite + Tailwind CSS v4.
  - UI strictly follows standard LLM chatting aesthetics (Sidebar + Centered Chat column).
  - Securely integrated with **Supabase Authentication** (Email & Google OAuth).
- **Backend:** Python + FastAPI.
  - **Vector DB:** Supabase (pgvector) matches document chunks.
  - **LLM:** Google Gemini API (`gemini-2.0-flash`) acts as the primary generative engine.
  - **Failover:** Automatic transparent fallback to **Groq** (`llama-3.3-70b-versatile`) if Gemini hits Rate Limits/Quotas.
  - **Storage:** Backblaze B2 handles raw PDF document storage and form downloads via presigned URLs.

---

## 🚀 Getting Started

### 1. Environment Configuration
Copy `.env.example` to `.env` in the root directory and fill in your keys. Both the backend and the frontend read from this single root file.

```bash
cp .env.example .env
```

### 2. Running Locally (Without Docker)

You will need two terminal tabs.

**Terminal 1: FastAPI Backend**
```bash
# Assuming you are in the root directory
python -m venv venv
# Activate venv:
# Windows: .\venv\Scripts\Activate
# Mac/Linux: source venv/bin/activate
pip install -r requirements.txt

# Run the API
uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
```

**Terminal 2: React Frontend**
```bash
cd frontend
npm install
npm run dev
```
Navigate to [http://localhost:3000](http://localhost:3000).

---

## 🐳 Running with Docker

You can spin up the entire application stack in a single command using Docker Compose. Hot-reloading is fully supported in this Dockerized environment!

```bash
# Build and start the containers
docker-compose up --build

# To run in detached mode:
docker-compose up -d
```

- **Frontend:** [http://localhost:3000](http://localhost:3000)
- **Backend API Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)

To stop the containers:
```bash
docker-compose down
```

---

## 🔐 Supabase Configuration

If you are setting up the chat history and auth backend from scratch, refer to the included `supabase_setup.md` script generated in your artifacts directory. It includes:
1. Steps for Google Auth Integration.
2. The exact SQL schema required for the `chats` and `messages` tables.
3. Row Level Security (RLS) policies ensuring complete data privacy.
