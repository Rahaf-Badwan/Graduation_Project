import os
import pickle
import numpy as np
import faiss
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer

UPLOADS_DIR = "uploads"
INDEX_DIR = "faiss_index"
INDEX_FILE = os.path.join(INDEX_DIR, "docs.index")
META_FILE = os.path.join(INDEX_DIR, "metadata.pkl")

CHUNK_SIZE = 900
CHUNK_OVERLAP = 150


def read_pdf(path: str) -> str:
    reader = PdfReader(path)
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return "\n".join(pages).strip()


def split_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP):
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start += max(1, chunk_size - overlap)
    return chunks


def main():
    if not os.path.isdir(UPLOADS_DIR):
        print(f"Uploads folder not found: {UPLOADS_DIR}")
        return

    model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

    all_chunks = []
    metadata = []

    for filename in os.listdir(UPLOADS_DIR):
        if not filename.lower().endswith(".pdf"):
            continue

        path = os.path.join(UPLOADS_DIR, filename)
        print(f"Reading: {filename}")
        text = read_pdf(path)

        if not text.strip():
            print(f"Skipped empty PDF: {filename}")
            continue

        chunks = split_text(text)
        for i, chunk in enumerate(chunks):
            all_chunks.append(chunk)
            metadata.append({
                "file": filename,
                "chunk_id": i
            })

    if not all_chunks:
        print("No PDF text found to index.")
        return

    print(f"Total chunks: {len(all_chunks)}")
    embeddings = model.encode(all_chunks, convert_to_numpy=True)
    embeddings = np.asarray(embeddings, dtype="float32")

    index = faiss.IndexFlatL2(embeddings.shape[1])
    index.add(embeddings)

    os.makedirs(INDEX_DIR, exist_ok=True)
    faiss.write_index(index, INDEX_FILE)

    with open(META_FILE, "wb") as f:
        pickle.dump({
            "chunks": all_chunks,
            "metadata": metadata
        }, f)

    print("Training/indexing complete.")
    print(f"Index saved to: {INDEX_DIR}")


if __name__ == "__main__":
    main()