"""固定用例的离线引用契约测试，不把假模型通过率当成真实 RAG 质量。"""

import json
from pathlib import Path
from uuid import uuid4

import pytest

from app.cli import evaluate_rag
from app.config import Settings
from app.schemas.rag_vo import GroundedAnswerVO, RagSourceVO
from app.services.rag_service import build_answer

DATASET = json.loads(
    (Path(__file__).parent / "fixtures/rag_evaluation.json").read_text(encoding="utf-8")
)


@pytest.mark.parametrize("case", DATASET["cases"], ids=lambda case: case["id"])
def test_fixed_question_citation_contract(case):
    expected = case["expected_filename"]
    if expected is None:
        result = build_answer(
            GroundedAnswerVO(
                answer="没有依据",
                source_ids=[],
                insufficient_evidence=True,
            ),
            [],
            "live",
        )
        assert result.status == "insufficient_evidence"
        assert result.sources == []
    else:
        doc = next(doc for doc in DATASET["documents"] if doc["filename"] == expected)
        assert all(keyword in doc["content"] for keyword in case["keywords"])
        source = RagSourceVO(
            source_id=1,
            document_id=uuid4(),
            filename=expected,
            chunk_index=0,
            heading="",
            text=doc["content"],
        )
        result = build_answer(
            GroundedAnswerVO(
                answer=doc["content"] + "[1]",
                source_ids=[1],
                insufficient_evidence=False,
            ),
            [source],
            "live",
        )
        assert result.sources[0].filename == expected
        assert result.sources[0].text == doc["content"]


async def test_evaluation_uses_isolated_index_and_does_not_call_online_model(
    tmp_path, monkeypatch
):
    import numpy as np

    class FakeEmbedding:
        def __init__(self, **_):
            pass

        def embed(self, texts, **_):
            return [np.ones(512, dtype=np.float32) / np.sqrt(512) for _ in texts]

        def query_embed(self, question):
            return iter(self.embed([question]))

    async def forbidden(*_):
        pytest.fail("默认评估不允许调用在线模型")

    monkeypatch.setattr("fastembed.TextEmbedding", FakeEmbedding)
    monkeypatch.setattr(evaluate_rag.RagModelService, "answer", forbidden)
    config = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://unused",
        jwt_secret="测试",
        knowledge_data_dir=tmp_path,
    )
    monkeypatch.setattr(evaluate_rag, "get_settings", lambda: config)
    report = await evaluate_rag.evaluate(DATASET, live=False)
    assert len(report["cases"]) == 12
    assert report["answerable_cases"] == 10
    assert report["retrieval_hits"] == 10
    assert report["answer_passed"] is None
