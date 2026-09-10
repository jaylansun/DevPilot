from app.main import app


def test_auth_routes_follow_project_plan() -> None:
    paths = app.openapi()["paths"]

    assert "/api/v1/auth/token" in paths
    assert "post" in paths["/api/v1/auth/token"]
    assert "/api/v1/me" in paths
    assert "get" in paths["/api/v1/me"]
    assert "/api/v1/auth/register" not in paths
