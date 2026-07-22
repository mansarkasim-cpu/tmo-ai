from typing import List, Optional, Dict, Any

try:
    from langchain.embeddings import HuggingFaceEmbeddings
except Exception:
    HuggingFaceEmbeddings = None

import numpy as np


# Minimal in-memory vector store fallback. Stores embeddings and metadata and
# performs cosine-similarity search using numpy. This avoids requiring
# `langchain.vectorstores.FAISS` to be present at import time.
class _SimpleDoc:
    def __init__(self, page_content: str, metadata: dict | None = None):
        self.page_content = page_content
        self.metadata = metadata or {}


class SimpleVectorStore:
    def __init__(self, embeddings):
        self.embeddings = embeddings
        self._vectors: np.ndarray | None = None
        self._docs: list[_SimpleDoc] = []

    @classmethod
    def from_documents(cls, docs: list, embeddings):
        inst = cls(embeddings)
        inst.add_documents(docs)
        return inst

    def add_documents(self, docs: list):
        texts = [d.page_content if hasattr(d, 'page_content') else d['page_content'] for d in docs]
        embs = np.array(self.embeddings.embed_documents(texts), dtype=np.float32)
        if self._vectors is None:
            self._vectors = embs
        else:
            self._vectors = np.vstack([self._vectors, embs])

        for d in docs:
            if hasattr(d, 'page_content'):
                self._docs.append(d)
            else:
                self._docs.append(_SimpleDoc(d['page_content'], d.get('metadata')))

    def similarity_search_with_score(self, query: str, k: int = 4):
        if self._vectors is None or len(self._docs) == 0:
            return []
        q_emb = np.array(self.embeddings.embed_query(query), dtype=np.float32)
        # cosine similarity
        vecs = self._vectors
        # normalize
        q_norm = q_emb / (np.linalg.norm(q_emb) + 1e-12)
        v_norm = vecs / (np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-12)
        sims = (v_norm @ q_norm).astype(np.float32)
        idx = np.argsort(-sims)[:k]
        results = []
        for i in idx:
            doc = self._docs[i]
            score = float(sims[i])
            results.append((doc, score))
        return results

from app.services.pdf_service import get_document


class _SentenceTransformerEmbeddings:
    """Minimal wrapper providing `embed_documents` and `embed_query`
    using `sentence_transformers.SentenceTransformer` for environments
    where LangChain's `HuggingFaceEmbeddings` is not available.
    """

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        try:
            from sentence_transformers import SentenceTransformer
        except Exception as e:
            raise RuntimeError(
                "sentence-transformers is required if langchain HuggingFaceEmbeddings is not available. "
                "Install with: pip install sentence-transformers"
            ) from e
        self.model = SentenceTransformer(model_name)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [emb.tolist() for emb in self.model.encode(texts, show_progress_bar=False, convert_to_tensor=False)]

    def embed_query(self, text: str) -> List[float]:
        emb = self.model.encode([text], show_progress_bar=False, convert_to_tensor=False)
        return emb[0].tolist()


class KBManager:
    """Simple LangChain-compatible KB manager using FAISS + HuggingFaceEmbeddings.

    This keeps one FAISS index for all documents and stores metadata with
    `document_id` and `chunk` so results can be traced back to the source.
    """

    def __init__(self, embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"):
        if HuggingFaceEmbeddings is not None:
            try:
                self.embeddings = HuggingFaceEmbeddings(model_name=embedding_model)
            except Exception:
                # fallback to local sentence-transformers wrapper
                self.embeddings = _SentenceTransformerEmbeddings(model_name=embedding_model)
        else:
            self.embeddings = _SentenceTransformerEmbeddings(model_name=embedding_model)
        self.index: Optional[Any] = None

    def _chunk_text(self, text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
        if not text:
            return []
        chunks: List[str] = []
        start = 0
        length = len(text)
        while start < length:
            end = start + chunk_size
            chunk = text[start:end]
            chunks.append(chunk)
            start = max(end - overlap, end)
        return chunks

    def index_document(self, document_id: str, chunk_size: int = 500, overlap: int = 50) -> Dict[str, Any]:
        """Load a document by id (from pdf_service) and index it into the FAISS store.

        Returns metadata about how many chunks were indexed.
        """
        text = get_document(document_id)
        if text is None:
            raise ValueError("Document not found: %s" % document_id)

        chunks = self._chunk_text(text, chunk_size=chunk_size, overlap=overlap)
        docs: List[dict] = []
        for i, c in enumerate(chunks):
            docs.append({"page_content": c, "metadata": {"document_id": document_id, "chunk": i}})

        if not docs:
            return {"document_id": document_id, "chunks_indexed": 0}

        if self.index is None:
            # use langchain FAISS if it's available under that name, otherwise use the simple fallback
            try:
                from langchain.vectorstores import FAISS

                # FAISS expects langchain Document objects; construct minimal wrapper if needed
                class _DocWrapper:
                    def __init__(self, page_content, metadata):
                        self.page_content = page_content
                        self.metadata = metadata

                wrapped = [_DocWrapper(d["page_content"], d.get("metadata")) for d in docs]
                self.index = FAISS.from_documents(wrapped, self.embeddings)
            except Exception:
                self.index = SimpleVectorStore.from_documents(docs, self.embeddings)
        else:
            try:
                self.index.add_documents(docs)
            except Exception:
                # if underlying index is FAISS it may expect Document objects
                try:
                    from langchain.docstore.document import Document as _LCDoc

                    wrapped = [_LCDoc(page_content=d["page_content"], metadata=d.get("metadata")) for d in docs]
                    self.index.add_documents(wrapped)
                except Exception:
                    # fallback to simple store
                    if hasattr(self.index, 'add_documents'):
                        self.index.add_documents(docs)

        return {"document_id": document_id, "chunks_indexed": len(docs)}

    def search(self, query: str, k: int = 4) -> List[Dict[str, Any]]:
        """Return top-k search results with metadata and similarity scores.

        Raises RuntimeError if the index is empty/uninitialized.
        """
        if self.index is None:
            raise RuntimeError("KB index is empty. Index documents first.")

        results = self.index.similarity_search_with_score(query, k=k)
        out: List[Dict[str, Any]] = []
        for doc, score in results:
            meta = doc.metadata or {}
            out.append({"document_id": meta.get("document_id"), "chunk": meta.get("chunk"), "text": doc.page_content, "score": float(score)})
        return out


# singleton instance used by the API
kb = KBManager()
