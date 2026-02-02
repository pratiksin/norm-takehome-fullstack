from pydantic import BaseModel
import qdrant_client
# New LlamaIndex Imports
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.llms.openai import OpenAI
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.core import (
    VectorStoreIndex,
    StorageContext,
    ServiceContext,
    Settings,          
    Document,
)
from llama_index.core.query_engine import CitationQueryEngine
from dataclasses import dataclass
import os
import re
# from pypdf import PdfReader
import PyPDF2
from pathlib import Path
from typing import List, Tuple

# --- GLOBAL SETTINGS (Modern LlamaIndex) ---
key=os.environ.get('OPENAI_API_KEY')
Settings.llm = OpenAI(api_key=key, model="gpt-4")
Settings.embed_model = OpenAIEmbedding(api_key=key)


@dataclass
class Citation:
    source: str
    text: str

class Output(BaseModel):
    query: str
    response: str
    citations: list[Citation]


class DocumentService:
    """
    Service to load the pdf and extract its contents into llama_index Documents.
    """

    def __init__(self, pdf_path: str | None = None) -> None:
        if pdf_path is None:
            # assuming utils.py is in app/, and laws.pdf in app/docs/
            base_dir = Path(__file__).resolve().parent.parent
            self.pdf_path = base_dir / "docs" / "laws.pdf"
        else:
            self.pdf_path = Path(pdf_path)
    
    def _extract_raw_text(self) -> str:
        """Extract text from the PDF using pypdf (or PyPDF2)."""
        import pypdf  # or PyPDF2 if that's what you installed

        raw_text_parts: list[str] = []
        with self.pdf_path.open("rb") as f:
            reader = pypdf.PdfReader(f)
            for page in reader.pages:
                page_text = page.extract_text() or ""
                raw_text_parts.append(page_text)
        return "\n".join(raw_text_parts)

    def _normalize_lines(self, raw_text: str) -> List[str]:
       
        raw_lines = [ln.strip() for ln in raw_text.splitlines()]
        paragraphs: List[str] = []
        buffer: List[str] = []

        def flush_buffer():
            if buffer:
                paragraphs.append(" ".join(buffer).strip())
                buffer.clear()

        # heuristic: lines that clearly start a new bullet / section
        new_block_re = re.compile(r"^\d+(\.\d+)*\.$")  # e.g. "10.", "10.1.", "10.1.1."
        for ln in raw_lines:
            if not ln:
                flush_buffer()
                continue

            if new_block_re.match(ln):
                # standalone subsection marker like "10.1."
                flush_buffer()
                paragraphs.append(ln)
            else:
                buffer.append(ln)

        flush_buffer()
        return paragraphs

    def create_documents(self) -> List[Document]:
        raw_text = self._extract_raw_text()
        paragraphs = self._normalize_lines(raw_text)

        # law id and name:
        #   "10."  -> law id
        #   "Watch" -> law name
        law_id_re = re.compile(r"^(\d+)\.\s*$")
        subsection_re = re.compile(r"^(\d+(?:\.\d+)+\.)\s*(.*)$")

        laws: List[Tuple[str, str, List[str]]] = []  # (law_id, law_name, paras)
        current_law_id: str | None = None
        current_law_name: str | None = None
        current_paras: List[str] = []
        expecting_name = False

        def flush_law():
            if current_law_id and current_law_name and current_paras:
                laws.append((current_law_id, current_law_name, current_paras.copy()))

        for para in paragraphs:
            m_id = law_id_re.match(para)
            if m_id:
                flush_law()
                current_law_id = m_id.group(1)
                current_law_name = None
                current_paras = []
                expecting_name = True
                continue

            if expecting_name:
                name = para.strip()
                if name:
                    current_law_name = name
                    expecting_name = False
                continue

            if current_law_id is not None:
                current_paras.append(para)

        flush_law()

        docs: List[Document] = []
        for law_id, law_name, law_paras in laws:
            formatted_lines: List[str] = []

            for para in law_paras:
                # subsection marker on its own line (from _normalize_lines)
                m_sub = subsection_re.match(para)
                if m_sub:
                    number = m_sub.group(1).rstrip(".")
                    rest = m_sub.group(2).strip()

                    depth = number.count(".") + 1
                    indent = "  " * (depth - 1)
                    if rest:
                        formatted_lines.append(f"{indent}{number}. {rest}")
                    else:
                        formatted_lines.append(f"{indent}{number}.")
                    continue

                # paragraph that begins with a subsection number and text
                m_inline = subsection_re.match(para)
                if m_inline:
                    number = m_inline.group(1).rstrip(".")
                    rest = m_inline.group(2).strip()
                    depth = number.count(".") + 1
                    indent = "  " * (depth - 1)
                    formatted_lines.append(f"{indent}{number}. {rest}")
                else:
                    if not formatted_lines:
                        formatted_lines.append(para)
                    else:
                        formatted_lines[-1] = formatted_lines[-1] + " " + para

            text = " ".join(formatted_lines).strip()
            metadata = {
                "LawId": law_id,
                "LawName": law_name,
                "Section": f"Law {law_id} – {law_name}",
            }

            docs.append(
                Document(
                    metadata=metadata,
                    text=text,
                )
            )

        return docs



class QdrantService:
    def __init__(self, k: int = 2):
        self.index = None
        self.k = k
        self.collection_name = 'westeros_laws'
    
    def connect(self) -> None:
        """Initializes the Qdrant Client and creates the empty VectorStoreIndex."""
        # Allow using an external Qdrant container via QDRANT_URL env var.
        # If QDRANT_URL is not set, fall back to in-memory client (useful for tests).
        qdrant_url = os.environ.get("QDRANT_URL")
        if qdrant_url:
            # Example: http://qdrant:6333
            client = qdrant_client.QdrantClient(url=qdrant_url)
        else:
            client = qdrant_client.QdrantClient(location=":memory:")

        # Initialize the QdrantVectorStore
        vstore = QdrantVectorStore(client=client, collection_name=self.collection_name)
        
        # Initialize StorageContext (used for index creation)
        storage_context = StorageContext.from_defaults(vector_store=vstore)
        

        # The index is created here, but is empty until 'load' is called
        self.index = VectorStoreIndex.from_vector_store(
            vector_store=vstore,
            storage_context=storage_context # Use storage_context with modern core
        )

    def load(self, docs=list[Document]):
        """Inserts documents into the initialized index."""
        if not self.index:
            raise ValueError("Qdrant Index not connected. Call connect() first.")
        
        # Insert nodes into the index. This populates the Qdrant collection.
        # This will use the default chunking/embedding logic defined in Settings.
        # for doc in docs:
        #    self.index.insert(doc)
        self.index.insert_nodes(docs)
    
    def query(self, query_str: str) -> Output:
        if not self.index:
            raise ValueError("Index not initialized. The startup process failed.")

        # Create the CitationQueryEngine
        query_engine = CitationQueryEngine.from_args(
            self.index,
            similarity_top_k=self.k,
            citation_chunk_size=512,
        )

        response_obj = query_engine.query(query_str)
        
        # Extract Citations from source nodes
        citations_list = []
        for node in response_obj.source_nodes:
            source_label = node.metadata.get("Section", "Unknown Law")
            citations_list.append(
                Citation(
                    source=source_label,
                    text=node.get_content().strip()
                )
            )

        output = Output(
            query=query_str, 
            response=str(response_obj), 
            citations=citations_list
        )
        
        return output