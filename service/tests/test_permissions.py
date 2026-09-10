import pytest

from app.api.dependencies import require_roles
from app.errors import ApiError
from app.models.user import User, UserRole


@pytest.mark.asyncio
async def test_reviewer_can_use_reviewer_dependency() -> None:
    reviewer = User(
        username="reviewer_test",
        password_hash="测试哈希",
        role=UserRole.REVIEWER,
    )
    check_role = require_roles(UserRole.REVIEWER)

    assert await check_role(reviewer) is reviewer


@pytest.mark.asyncio
async def test_member_is_rejected_by_reviewer_dependency() -> None:
    member = User(
        username="member_test",
        password_hash="测试哈希",
        role=UserRole.MEMBER,
    )
    check_role = require_roles(UserRole.REVIEWER)

    with pytest.raises(ApiError) as error:
        await check_role(member)

    assert error.value.status_code == 403
    assert error.value.code == "insufficient_permissions"
