"""使用虚构评估资料验证真实检索；只有显式 --live 才调用在线模型。"""

import argparse
import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from app.config import get_settings
from app.schemas.rag_vo import RagSourceVO
from app.services.document_index_service import DocumentIndexService
from app.services.rag_model_service import RagModelService
from app.services.rag_service import build_answer


async def evaluate(dataset: dict, *, live: bool) -> dict:
    settings = get_settings().model_copy(update={"ai_mode": "live" if live else "mock"})
    if live and not (
        settings.model_name.strip()
        and settings.llm_base_url.strip()
        and settings.llm_api_key.get_secret_value().strip()
    ):
        raise ValueError("真实评估需要配置 MODEL_NAME、LLM_BASE_URL 和 LLM_API_KEY")
    project = uuid4()
    documents = {uuid4(): document for document in dataset["documents"]}
    with TemporaryDirectory(
        prefix="devpilot-rag-eval-", ignore_cleanup_errors=True
    ) as directory:
        # 向量库完全隔离，只复用模型缓存，不接触用户项目或真实知识库集合。
        from fastembed import TextEmbedding

        embedding = TextEmbedding(
            model_name="BAAI/bge-small-zh-v1.5",
            cache_dir=str(settings.knowledge_data_dir / "models"),
            threads=2,
        )
        index = DocumentIndexService(Path(directory), embedding)
        for doc_id, doc in documents.items():
            index.index(project, doc_id, doc["filename"], doc["content"])
        model = RagModelService(settings)
        results = []
        for case in dataset["cases"]:
            hits = index.search(
                project,
                list(documents),
                case["question"],
                min_score=settings.rag_min_score,
            )
            sources = [
                RagSourceVO(
                    source_id=i + 1,
                    document_id=hit.document_id,
                    filename=documents[hit.document_id]["filename"],
                    chunk_index=hit.chunk_index,
                    heading=hit.heading,
                    text=hit.text,
                )
                for i, hit in enumerate(hits)
            ]
            expected = case["expected_filename"]
            citation_hit = expected is not None and any(
                source.filename == expected for source in sources
            )
            row = {
                "id": case["id"],
                "retrieval_hit": citation_hit,
                "expected_answerable": expected is not None,
            }
            if live:
                if sources:
                    result = build_answer(
                        await model.answer(case["question"], sources), sources, "live"
                    )
                    row["passed"] = (
                        (
                            result.status == "answered"
                            and any(
                                source.filename == expected for source in result.sources
                            )
                            and all(
                                keyword in result.answer for keyword in case["keywords"]
                            )
                        )
                        if expected
                        else result.status == "insufficient_evidence"
                    )
                else:
                    row["passed"] = expected is None
            results.append(row)
        return {
            "mode": "真实模型自动初评，仍需人工核对事实"
            if live
            else "仅真实向量检索评估，未验证生成答案",
            "answerable_cases": sum(row["expected_answerable"] for row in results),
            "retrieval_hits": sum(row["retrieval_hit"] for row in results),
            "answer_passed": sum(row.get("passed", False) for row in results)
            if live
            else None,
            "cited_answer_passed": sum(
                row["expected_answerable"] and row.get("passed", False)
                for row in results
            )
            if live
            else None,
            "abstention_passed": sum(
                not row["expected_answerable"] and row.get("passed", False)
                for row in results
            )
            if live
            else None,
            "cases": results,
        }


def main():
    parser = argparse.ArgumentParser(
        description="知识库固定评估；--live 会发送虚构测试片段并可能产生模型费用"
    )
    parser.add_argument(
        "--dataset", type=Path, default=Path("tests/fixtures/rag_evaluation.json")
    )
    parser.add_argument(
        "--live", action="store_true", help="允许调用已配置的在线模型，可能产生费用"
    )
    args = parser.parse_args()
    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    report = asyncio.run(evaluate(dataset, live=args.live))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.live and (
        report["cited_answer_passed"] < min(10, report["answerable_cases"])
        or report["abstention_passed"]
        < len(report["cases"]) - report["answerable_cases"]
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
