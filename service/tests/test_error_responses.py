from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.error_handlers import register_error_handlers
from app.middleware import request_id_middleware


def create_test_app() -> FastAPI:
    app = FastAPI()
    app.middleware("http")(request_id_middleware)
    register_error_handlers(app)

    @app.get("/numbers")
    async def read_number(value: int) -> dict[str, int]:
        return {"value": value}

    return app


def test_not_found_uses_chinese_error_response() -> None:
    with TestClient(create_test_app()) as client:
        response = client.get("/not-found", headers={"X-Request-ID": "not-found-test"})

    assert response.status_code == 404
    assert response.headers["X-Request-ID"] == "not-found-test"
    assert response.json() == {
        "error": {
            "code": "not_found",
            "message": "请求的资源不存在",
            "request_id": "not-found-test",
            "details": None,
        }
    }


def test_validation_error_uses_chinese_message() -> None:
    with TestClient(create_test_app()) as client:
        response = client.get("/numbers", params={"value": "错误的数字"})

    body = response.json()
    assert response.status_code == 422
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["message"] == "请求参数校验失败"
    assert body["error"]["details"][0]["message"] == "必须是有效的整数"
