import os
import pickle
import numpy as np
import faiss
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer

# ← إضافة مكتبات الـ OCR
try:
    import pytesseract
    from pdf2image import convert_from_path
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False
    print("⚠️  pytesseract / pdf2image غير مثبتين — الملفات المسحوبة ستُتخطى")
    print("   لتثبيتهم: pip install pytesseract pdf2image")

UPLOADS_DIR = "uploads"
INDEX_DIR = "faiss_index"
INDEX_FILE = os.path.join(INDEX_DIR, "docs.index")
META_FILE = os.path.join(INDEX_DIR, "metadata.pkl")

CHUNK_SIZE = 900
CHUNK_OVERLAP = 150


def read_pdf(path: str) -> str:
    """يقرأ الـ PDF — إذا كان مسحوباً يستخدم OCR تلقائياً"""
    reader = PdfReader(path)
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    full_text = "\n".join(pages).strip()

    # لو النص فاضي = PDF مسحوب (صور) → استخدم OCR
    if not full_text:
        if not OCR_AVAILABLE:
            print(f"  ⚠️  مسحوب وبدون OCR، تم تخطّي: {os.path.basename(path)}")
            return ""
        print(f"  🔍 PDF مسحوب، جاري استخدام OCR: {os.path.basename(path)}")
        try:
            images = convert_from_path(path, dpi=200)
            ocr_pages = []
            for i, img in enumerate(images):
                print(f"     صفحة {i+1}/{len(images)}...")
                text = pytesseract.image_to_string(img, lang="ara+eng")
                ocr_pages.append(text)
            full_text = "\n".join(ocr_pages).strip()
        except Exception as e:
            print(f"  ❌ فشل الـ OCR: {e}")
            return ""

    return full_text


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
        print(f"❌ فولدر الملفات غير موجود: {UPLOADS_DIR}")
        return

    model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

    all_chunks = []
    metadata = []

    pdf_files = [f for f in os.listdir(UPLOADS_DIR) if f.lower().endswith(".pdf")]
    print(f"📂 عدد ملفات الـ PDF الموجودة: {len(pdf_files)}")

    for filename in pdf_files:
        path = os.path.join(UPLOADS_DIR, filename)
        print(f"\n📄 يقرأ: {filename}")
        text = read_pdf(path)

        if not text.strip():
            print(f"  ⏭️  تم تخطي الملف (فاضي): {filename}")
            continue

        chunks = split_text(text)
        print(f"  ✅ {len(chunks)} chunk تم استخراجها")

        for i, chunk in enumerate(chunks):
            all_chunks.append(chunk)
            metadata.append({
                "file": filename,
                "chunk_id": i
            })

    if not all_chunks:
        print("\n❌ لا يوجد نص لإضافته للـ index.")
        return

    print(f"\n📊 إجمالي الـ chunks: {len(all_chunks)}")
    print("⏳ جاري إنشاء الـ embeddings...")

    embeddings = model.encode(all_chunks, convert_to_numpy=True, show_progress_bar=True)
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

    print(f"\n✅ التدريب اكتمل! الـ index حُفظ في: {INDEX_DIR}")
    print(f"   إجمالي الملفات المُدرَّبة: {len(set(m['file'] for m in metadata))}/{len(pdf_files)}")


if __name__ == "__main__":
    main()
