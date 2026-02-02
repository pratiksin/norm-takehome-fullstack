This repository contains a client and server codebase. 

## Server Repository:

This codebase contains a list of laws (`docs/laws.pdf`) taken from the fictional series “Game of Thrones” (randomly pulled from a wiki fandom site... unfortunately knowledge of the series does not provide an edge on this assignment). The server is a FastAPI app that indexes the PDF and exposes a `/query?q=` endpoint.

### Run with Docker Compose (recommended)

1. Create a `.env` file from the example and set your OpenAI key:

   cp .env.example .env
   # then edit .env and set OPENAI_API_KEY

2. Build and start both services:

   docker compose up --build

3. Frontend will be available at http://localhost:3000 and backend at http://localhost:8000 (OpenAPI docs at /docs).

> Note: The backend will read `OPENAI_API_KEY` from the environment at container start. Do not hardcode secrets into `Dockerfile`.

## Client Repository 

In the `frontend` folder you'll find a NextJS app. For development, you can run it locally using:

```bash
cd frontend
npm install
npm run dev
```

When running via Docker Compose the frontend image is built and uses `http://backend:8000` as the API base so no extra configuration should be necessary.
