"""全流程验收使用生产应用，仅替换向量模型；不添加测试后门或重建业务记录。"""

import os
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import patch

from sqlalchemy.engine import make_url

# 在导入生产应用及创建数据库连接前拒绝不明确的测试环境。
if (
    make_url(os.environ["DATABASE_URL"]).database != "day13_test"
    or os.environ.get("AI_MODE") != "mock"
    or os.environ.get("LLM_API_KEY")
    or not Path(os.environ["KNOWLEDGE_DATA_DIR"]).is_absolute()
):
    raise RuntimeError("全流程验收必须使用独立 day13_test、绝对索引路径及离线模型")

from app.database import AsyncSessionFactory
from app.main import app
from app.main import lifespan as production_lifespan
from app.models.user_do import UserDO, UserRole
from app.security import hash_password
from app.services.document_index_service import DocumentIndexService
from sqlalchemy import select
from test_document_index_service import FakeEmbedding


@asynccontextmanager
async def lifespan(application):
    # Chroma、文档上传/分块/后台索引、服务、认证和 PostgreSQL 都走生产实现。
    # 索引只使用本次临时目录，假向量不会进入用户的真实知识库。
    with patch(
        "app.main.DocumentIndexService",
        side_effect=lambda path: DocumentIndexService(path, FakeEmbedding()),
    ):
        async with production_lifespan(application):
            async with AsyncSessionFactory.begin() as session:
                for username, role in [
                    ("day13_member", UserRole.MEMBER),
                    ("day13_reviewer", UserRole.REVIEWER),
                ]:
                    if (
                        await session.scalar(
                            select(UserDO.id).where(UserDO.username == username)
                        )
                        is None
                    ):
                        session.add(
                            UserDO(
                                username=username,
                                role=role,
                                password_hash=hash_password("day13-test-password"),
                            )
                        )
            yield


app.router.lifespan_context = lifespan
