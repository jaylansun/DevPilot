from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

MODEL_NAME = "BAAI/bge-small-zh-v1.5"


@dataclass(frozen=True)
class DocumentChunk:
    text: str
    heading: str


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
    """单实例后台线程使用；原文向量化在本机 CPU 完成，不发送给在线模型。"""

    def __init__(self, data_dir: Path, embedding_model=None):
        self.data_dir = data_dir
        self._embedding_model = embedding_model
        self._collection = None

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

    def delete_document(self, project_id: UUID, document_id: UUID) -> None:
        self.collection.delete(
            where={
                "$and": [
                    {"project_id": str(project_id)},
                    {"document_id": str(document_id)},
                ]
            }
        )

    def delete_project(self, project_id: UUID) -> None:
        self.collection.delete(where={"project_id": str(project_id)})
