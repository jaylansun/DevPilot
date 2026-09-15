import subprocess
import sys
from uuid import uuid4

import numpy as np

from app.services.document_index_service import DocumentIndexService, split_document


class FakeEmbedding:
    """只供测试使用，生产代码从不自动回退到假向量。"""

    def embed(self, texts, **kwargs):
        return [np.ones(512, dtype=np.float32) / np.sqrt(512) for _ in texts]

    def query_embed(self, query):
        return iter(self.embed([query]))


def test_split_keeps_headings_and_bounds_chinese_chunks():
    chunks = split_document(
        "# 产品\n## 支付\n" + "支付成功后发送通知。" * 120, "需求.md"
    )
    assert len(chunks) > 1
    assert all(0 < len(chunk.text) <= 400 for chunk in chunks)
    assert all("支付" in chunk.heading for chunk in chunks)
    assert "发送通知" in "".join(chunk.text for chunk in chunks)


def test_chroma_persists_isolates_projects_and_retry_is_idempotent(tmp_path):
    project, other_project, document, other_document = (uuid4() for _ in range(4))
    service = DocumentIndexService(tmp_path, FakeEmbedding())
    count = service.index(project, document, "需求.md", "# 需求\n中文需求。" * 120)
    service.index(other_project, other_document, "other.txt", "另一个项目的文档")
    service.index(project, document, "需求.md", "# 需求\n中文需求。" * 120)
    assert (
        len(service.collection.get(where={"project_id": str(project)})["ids"]) == count
    )
    reopened = DocumentIndexService(tmp_path, FakeEmbedding())
    assert (
        len(reopened.collection.get(where={"document_id": str(document)})["ids"])
        == count
    )
    # 独立进程读取，确认不是只从当前进程的客户端缓存取回数据。
    subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from pathlib import Path; "
            "from app.services.document_index_service import DocumentIndexService; "
            "index = DocumentIndexService(Path(sys.argv[1])); "
            "assert len(index.collection.get(where={'document_id': sys.argv[2]})['ids']) == int(sys.argv[3])",
            str(tmp_path),
            str(document),
            str(count),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    reopened.delete_document(other_project, document)
    assert (
        len(reopened.collection.get(where={"document_id": str(document)})["ids"])
        == count
    )
    reopened.delete_project(project)
    assert reopened.collection.get(where={"project_id": str(project)})["ids"] == []
    assert (
        len(reopened.collection.get(where={"project_id": str(other_project)})["ids"])
        == 1
    )


def test_long_heading_metadata_is_bounded():
    chunks = split_document("# " + "长标题" * 1000 + "\n正文", "需求.md")
    assert all(len(chunk.heading) <= 512 for chunk in chunks)


def test_search_is_scoped_to_project_and_ready_document_allowlist(tmp_path):
    project, other, ready, pending, foreign = [uuid4() for _ in range(5)]
    service = DocumentIndexService(tmp_path, FakeEmbedding())
    service.index(project, ready, "已就绪.md", "# 支付\n不能重复支付。")
    service.index(project, pending, "未就绪.md", "未就绪的部分索引")
    service.index(other, foreign, "其他项目.md", "其他项目的私有内容")
    hits = service.search(project, [ready, foreign], "如何支付？")
    assert len(hits) == 1
    assert hits[0].document_id == ready
    assert hits[0].heading == "支付"
    assert service.search(project, [], "如何支付？") == []
    service.delete_document(project, ready)
    assert service.search(project, [ready], "如何支付？") == []


def test_search_rejects_low_similarity_results(tmp_path):
    class OrthogonalEmbedding(FakeEmbedding):
        def query_embed(self, query):
            vector = np.zeros(512, dtype=np.float32)
            vector[0] = 1
            return iter([vector])

    service = DocumentIndexService(tmp_path, OrthogonalEmbedding())
    project, doc = uuid4(), uuid4()
    service.index(project, doc, "需求.md", "购物车需求")
    assert service.search(project, [doc], "无关问题", min_score=0.5) == []
