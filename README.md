# Set up

A FastAPI backend and React + TypeScript frontend.

## Run locally

In one terminal, start the API:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

In another terminal, start the UI:

```bash
cd frontend
npm install
npm run dev
```

Open the URL shown in the terminal (normally `http://localhost:5173`). The frontend calls at `http://localhost:8000`.