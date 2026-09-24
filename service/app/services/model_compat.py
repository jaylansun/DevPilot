"""结构化工具调用的供应商适配；仅向明确支持的官方模型发送扩展参数。"""

from urllib.parse import urlsplit

from app.config import Settings


def structured_output_extra_body(settings: Settings) -> dict | None:
    # MiMo 的工具调用关闭深度思考，避免推理占用结构化输出的预算与时限。
    # https://mimo.mi.com/docs/en-US/quick-start/faq/api-integration
    if urlsplit(
        settings.llm_base_url
    ).hostname == "api.xiaomimimo.com" and settings.model_name in {
        "mimo-v2.5",
        "mimo-v2.5-pro",
    }:
        return {"thinking": {"type": "disabled"}}
    return None
