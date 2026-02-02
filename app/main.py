from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.utils import Output, DocumentService, QdrantService
import os

app = FastAPI(title="Westeros Legal Assistant")

# Allow CORS during local development so the Next.js frontend can call this API.
# In production, restrict origins appropriately.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global instances
qdrant_service = QdrantService(k=3)
IS_READY = False # Flag to track successful startup

@app.on_event("startup")
def startup_event():
    global IS_READY
    print("--- STARTUP: Initializing Vector Store ---")

    if not os.environ.get('OPENAI_API_KEY'):
        print("FATAL: OPENAI_API_KEY environment variable not set.")
        return

    try:
        # NOTE: Using the path where the Dockerfile copies the PDF
        doc_service = DocumentService()
        
        # 1. Connect and initialize the empty index
        qdrant_service.connect()
        print("STATUS: Qdrant Client connected.")
        
        # 2. Load and index the documents
        docs = doc_service.create_documents()
        print(f"STATUS: Parsed {len(docs)} sections from PDF.")

        qdrant_service.load(docs)
        print("STATUS: Documents successfully indexed and loaded into Qdrant.")
        IS_READY = True
        
    except FileNotFoundError as e:
        print(f"FATAL ERROR (File): {e}")
    except Exception as e:
        print(f"FATAL ERROR (Indexing): {type(e).__name__}: {e}")
    
    print("--- STARTUP: Complete ---")


@app.get("/query", response_model=Output)
def query_laws(q: str):
    """
    Accepts a query string and returns a JSON response serialized 
    from the Pydantic Output class.
    """
    if not IS_READY:
        raise HTTPException(
            status_code=503, 
            detail="Service is not ready. Data indexing failed during startup. Check Docker logs for 'FATAL ERROR'."
        )
    if not q:
        raise HTTPException(status_code=400, detail="Query string cannot be empty")
    
    try:
        result = qdrant_service.query(q)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query processing error: {str(e)}")