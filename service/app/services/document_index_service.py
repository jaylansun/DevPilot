from dataclasses import dataclass
from functools import wraps
from math import isfinite
from pathlib import Path
from threading import RLock
from uuid import UUID

MODEL_NAME = "BAAI/bge-small-zh-v1.5"


@dataclass(frozen=True)
class DocumentChunk:
    text: str
    heading: str


@dataclass(frozen=True)
class RetrievedChunk:
    document_id: UUID
    chunk_index: int
    text: str
    heading: str
    score: float


def serialized(method):
    """后台索引和在线检索共用一个实例，串行访问模型与向量库。"""

    @wraps(method)
    def wrapped(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapped


def split_document(content: str, filename: str) -> list[DocumentChunk]:
    """先按 Markdown 标题分组，再按中文标点切成不超过 400 字符的块。"""
    from langchain_text_splitters import (
        MarkdownHeaderTextSplitter,
        RecursiveCharacterTextSplitter,
    )

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=400,
        chunk_overlap=60,
        separators=["\n\n", "\n", "。", "！", "？", "；", " ", ""],
    )
    if filename.lower().endswith(".md"):
        sections = MarkdownHeaderTextSplitter(
            headers_to_split_on=[("#" * level, f"h{level}") for level in range(1, 7)],
            strip_headers=False,
        ).split_text(content)
        chunks = []
        for section in sections:
            # 标题也是不可信输入，限制元数据长度，避免长标题被复制到每个片段。
            heading = " / ".join(
                str(section.metadata[key])[:256] for key in sorted(section.metadata)
            )[:512]
            chunks.extend(
                DocumentChunk(part, heading)
                for part in splitter.split_text(section.page_content)
                if part.strip()
            )
        return chunks
    return [
        DocumentChunk(part, "") for part in splitter.split_text(content) if part.strip()
    ]


class DocumentIndexService:
    """单进程内共享；切分、向量化和检索均在服务器本地完成。"""

    def __init__(self, data_dir: Path, embedding_model=None):
        self.data_dir = data_dir
        self._embedding_model = embedding_model
        self._collection = None
        self._lock = RLock()

    @property
    def collection(self):
        if self._collection is None:
            import chromadb
            from chromadb.config import Settings

            client = chromadb.PersistentClient(
                path=str(self.data_dir / "chroma"),
                settings=Settings(anonymized_telemetry=False),
            )
            # 固定模型版本和维度，避免后续误把另一种模型的向量写入同一个集合。
            self._collection = client.get_or_create_collection(
                "devpilot_bge_small_zh_v1_5",
                embedding_function=None,
                metadata={
                    "hnsw:space": "cosine",
                    "embedding_model": MODEL_NAME,
                    "schema_version": 1,
                },
            )
        return self._collection

    @property
    def embedding_model(self):
        if self._embedding_model is None:
            from fastembed import TextEmbedding

            self._embedding_model = TextEmbedding(
                model_name=MODEL_NAME,
                cache_dir=str(self.data_dir / "models"),
                threads=2,
            )
        return self._embedding_model

    @serialized
    def index(
        self, project_id: UUID, document_id: UUID, filename: str, content: str
    ) -> int:
        chunks = split_document(content, filename)
        if not chunks:
            raise ValueError("没有可索引的文本")
        self.delete_document(project_id, document_id)
        for offset in range(0, len(chunks), 32):
            batch = chunks[offset : offset + 32]
            vectors = [
                vector.tolist()
                for vector in self.embedding_model.embed(
                    [chunk.text for chunk in batch],
                    batch_size=32,
                )
            ]
            self.collection.upsert(
                ids=[f"{document_id}:{offset + i}" for i in range(len(batch))],
                documents=[chunk.text for chunk in batch],
                embeddings=vectors,
                metadatas=[
                    {
                        "project_id": str(project_id),
                        "document_id": str(document_id),
                        "filename": filename,
                        "chunk_index": offset + i,
                        "heading": chunk.heading,
                    }
                    for i, chunk in enumerate(batch)
                ],
            )
        return len(chunks)

    @serialized
    def delete_document(self, project_id: UUID, document_id: UUID) -> None:
        self.collection.delete(
            where={
                "$and": [
                    {"project_id": str(project_id)},
                    {"document_id": str(document_id)},
                ]
            }
        )

    @serialized
    def delete_project(self, project_id: UUID) -> None:
        self.collection.delete(where={"project_id": str(project_id)})

    @serialized
    def search(
        self,
        project_id: UUID,
        document_ids: list[UUID],
        question: str,
        *,
        limit: int = 4,
        min_score: float = 0.5,
    ) -> list[RetrievedChunk]:
        """同时过滤项目和数据库确认已就绪的文档，不能只依赖相似度。"""
        if not document_ids:
            return []
        allowed = {str(value) for value in document_ids}
        vector = next(iter(self.embedding_model.query_embed(question))).tolist()
        result = self.collection.query(
            query_embeddings=[vector],
            n_results=limit,
            where={
                "$and": [
                    {"project_id": str(project_id)},
                    {"document_id": {"$in": sorted(allowed)}},
                ]
            },
            include=["documents", "metadatas", "distances"],
        )
        chunks = []
        seen = set()
        for text, metadata, distance in zip(
            result["documents"][0], result["metadatas"][0], result["distances"][0]
        ):
            if not text or not metadata or distance is None:
                continue
            score = 1 - float(distance)
            doc_id = str(metadata.get("document_id", ""))
            chunk_index = metadata.get("chunk_index")
            if (
                metadata.get("project_id") != str(project_id)
                or doc_id not in allowed
                or not isinstance(chunk_index, int)
                or chunk_index < 0
                or not isfinite(score)
                or score < min_score
                or (doc_id, chunk_index) in seen
            ):
                continue
            seen.add((doc_id, chunk_index))
            chunks.append(
                RetrievedChunk(
                    UUID(doc_id),
                    chunk_index,
                    text[:400],
                    str(metadata.get("heading", ""))[:512],
                    score,
                )
            )
        return chunks
