"""モデルごとの方言を吸収する層。

呼び出し側は「どのモデルか」「どれくらい考えさせるか」だけを指定し、
Bedrock Converse API のどのフィールドに何を入れるかはここが決める。
Nova と Claude では思考モードの指定フィールドが違い、
片方の形式をもう片方に送ると ValidationException になるため、
分岐をモデル定義側に閉じ込めている。
"""

from __future__ import annotations

from typing import Any

# 思考の深さ。呼び出し側はこの語彙だけを使う。
REASONING_LEVELS = ("off", "low", "medium", "high")


def is_nova(model_id: str) -> bool:
    return "amazon.nova" in model_id.lower()


def is_claude(model_id: str) -> bool:
    return "anthropic.claude" in model_id.lower()


def reasoning_fields(model_id: str, effort: str) -> dict[str, Any]:
    """additionalModelRequestFields に載せる思考モードの指定を返す。

    Nova   : {"reasoningConfig": {"type": "enabled", "maxReasoningEffort": "medium"}}
    Claude : {"thinking": {"type": "enabled", "budget_tokens": N}}
    """
    if effort not in REASONING_LEVELS:
        raise ValueError(f"reasoning_effort は {REASONING_LEVELS} のいずれか: {effort!r}")
    if effort == "off":
        return {}

    if is_nova(model_id):
        return {"reasoningConfig": {"type": "enabled", "maxReasoningEffort": effort}}
    if is_claude(model_id):
        # Claude 側は budget_tokens 指定。maxTokens > budget_tokens である必要がある。
        budget = {"low": 2048, "medium": 8192, "high": 16384}[effort]
        return {"thinking": {"type": "enabled", "budget_tokens": budget}}

    raise ValueError(f"思考モードの方言が未定義のモデル: {model_id}")


def default_temperature(model_id: str) -> float:
    """既定の temperature。

    Nova は temperature=0 で書き起こしが degeneration する既知の癖があるため
    0 にはしない。構造化出力寄りのタスクなので低めに置く。
    """
    return 0.3 if is_nova(model_id) else 0.3
