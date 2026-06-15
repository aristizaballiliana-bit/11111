"""
ingest.py
解析 Word/PDF 文档，切分文本，调用 Voyage embedding，存入 Chroma 向量库。
通过 API 接口调用（在 main.py 中暴露 /upload 接口），不需要单独命令行运行。
"""

import os
import io
import chromadb
import voyageai
from pypdf import PdfReader
from docx import Document
from openpyxl import load_workbook
from pptx import Presentation

VOYAGE_API_KEY = os.environ.get("VOYAGE_API_KEY")
CHROMA_PATH = os.environ.get("CHROMA_PATH", "./chroma_db")

# 初始化客户端
chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
collection = chroma_client.get_or_create_collection(name="product_docs")

vo = None
if VOYAGE_API_KEY:
    vo = voyageai.Client(api_key=VOYAGE_API_KEY)


def extract_text_from_pdf(file_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(file_bytes))
    text = ""
    for page in reader.pages:
        page_text = page.extract_text() or ""
        text += page_text + "\n"
    return text


def extract_text_from_docx(file_bytes: bytes) -> str:
    doc = Document(io.BytesIO(file_bytes))
    text = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
    # 同时提取表格内容
    for table in doc.tables:
        for row in table.rows:
            row_text = " | ".join(cell.text for cell in row.cells)
            text += "\n" + row_text
    return text


def extract_text_from_xlsx(file_bytes: bytes) -> str:
    """解析Excel，按工作表逐行提取单元格内容"""
    wb = load_workbook(io.BytesIO(file_bytes), data_only=True)
    text_parts = []
    for sheet in wb.worksheets:
        text_parts.append(f"【工作表: {sheet.title}】")
        for row in sheet.iter_rows(values_only=True):
            cells = [str(c) for c in row if c is not None and str(c).strip() != ""]
            if cells:
                text_parts.append(" | ".join(cells))
    return "\n".join(text_parts)


def extract_text_from_txt(file_bytes: bytes) -> str:
    for enc in ("utf-8", "gbk", "gb2312"):
        try:
            return file_bytes.decode(enc)
        except UnicodeDecodeError:
            continue
    return file_bytes.decode("utf-8", errors="ignore")


def extract_text_from_pptx(file_bytes: bytes) -> str:
    """解析PPT，按幻灯片提取文本框/表格内容及备注"""
    prs = Presentation(io.BytesIO(file_bytes))
    text_parts = []
    for i, slide in enumerate(prs.slides, start=1):
        slide_texts = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    line = "".join(run.text for run in para.runs)
                    if line.strip():
                        slide_texts.append(line.strip())
            if shape.has_table:
                for row in shape.table.rows:
                    cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                    if cells:
                        slide_texts.append(" | ".join(cells))
        if slide.has_notes_slide:
            notes = slide.notes_slide.notes_text_frame.text
            if notes.strip():
                slide_texts.append(f"[备注] {notes.strip()}")
        if slide_texts:
            text_parts.append(f"【幻灯片 {i}】\n" + "\n".join(slide_texts))
    return "\n\n".join(text_parts)


def extract_text_any(filename: str, file_bytes: bytes) -> str:
    """根据文件名后缀解析文本内容，不做切分/向量化"""
    name = filename.lower()
    if name.endswith(".pdf"):
        return extract_text_from_pdf(file_bytes)
    elif name.endswith(".docx"):
        return extract_text_from_docx(file_bytes)
    elif name.endswith((".xlsx", ".xlsm")):
        return extract_text_from_xlsx(file_bytes)
    elif name.endswith(".pptx"):
        return extract_text_from_pptx(file_bytes)
    elif name.endswith(".txt"):
        return extract_text_from_txt(file_bytes)
    else:
        raise ValueError("仅支持 .pdf、.docx、.xlsx、.pptx、.txt 文件")


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list:
    """按字符数切分文本，保留一定重叠，避免上下文断裂"""
    text = text.strip()
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk.strip())
        start += chunk_size - overlap
    return chunks


def embed_texts(texts: list) -> list:
    """调用 Voyage AI 做 embedding"""
    if not vo:
        raise RuntimeError("VOYAGE_API_KEY 未配置")
    result = vo.embed(texts, model="voyage-3", input_type="document")
    return result.embeddings


def ingest_document(filename: str, file_bytes: bytes, metadata: dict = None) -> dict:
    """
    主入口：传入文件名和字节内容，解析、切分、向量化、存入 Chroma
    返回处理结果摘要
    """
    metadata = metadata or {}

    text = extract_text_any(filename, file_bytes)

    chunks = chunk_text(text)
    if not chunks:
        return {"filename": filename, "chunks_added": 0, "message": "未提取到文本内容"}

    embeddings = embed_texts(chunks)

    ids = [f"{filename}_{i}" for i in range(len(chunks))]
    metadatas = [{"source": filename, **metadata} for _ in chunks]

    collection.add(
        ids=ids,
        embeddings=embeddings,
        documents=chunks,
        metadatas=metadatas,
    )

    return {"filename": filename, "chunks_added": len(chunks)}


def query_knowledge_base(query: str, top_k: int = 5) -> list:
    """检索知识库，返回相关文档片段"""
    if not vo:
        raise RuntimeError("VOYAGE_API_KEY 未配置")

    query_embedding = vo.embed([query], model="voyage-3", input_type="query").embeddings[0]

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
    )

    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]

    return [{"text": d, "source": m.get("source", "未知")} for d, m in zip(docs, metas)]


def list_documents() -> list:
    """列出知识库中已有的文档来源"""
    all_data = collection.get()
    sources = set()
    for m in all_data.get("metadatas", []):
        if m and "source" in m:
            sources.add(m["source"])
    return list(sources)


def delete_document(filename: str) -> dict:
    """删除指定文件的所有向量"""
    all_data = collection.get()
    ids_to_delete = [
        id_ for id_, m in zip(all_data["ids"], all_data["metadatas"])
        if m and m.get("source") == filename
    ]
    if ids_to_delete:
        collection.delete(ids=ids_to_delete)
    return {"filename": filename, "deleted_chunks": len(ids_to_delete)}
