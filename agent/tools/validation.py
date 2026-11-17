"""工具参数校验与输出预算（P0 执行闭环加固）。

* `validate_arguments`：对工具声明的 `input_schema` 做 JSON Schema 常用子集校验
  （type / required / enum / properties / items / min / max），
  参数不合法以 PARAMETER 错误拒绝，不进入真实执行。
* `truncate_output`：按工具声明的 `output_limit_bytes` 截断超长输出，
  防止工具返回内容挤爆上下文窗口。
"""

from __future__ import annotations

import json
from typing import Any

from agent.tools.errors import ToolErrorCategory, ToolExecutionError

_SUPPORTED_TYPES: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "number": (int, float),
    "integer": (int,),
    "boolean": (bool,),
    "array": (list, tuple),
    "object": (dict,),
    "null": (type(None),),
}


def validate_arguments(
    schema: dict[str, Any] | None,
    arguments: dict[str, Any],
) -> None:
    """校验工具入参；不合法抛 PARAMETER 类 ToolExecutionError。schema 为空则跳过。"""

    if not schema:
        return

    if not isinstance(arguments, dict):
        raise ToolExecutionError(
            ToolErrorCategory.PARAMETER,
            f"工具参数必须是对象，收到 {type(arguments).__name__}",
        )

    for required_key in schema.get("required", []):
        if required_key not in arguments:
            raise ToolExecutionError(
                ToolErrorCategory.PARAMETER,
                f"缺少必填参数: {required_key}",
            )

    properties = schema.get("properties", {})
    for key, rule in properties.items():
        if key not in arguments:
            continue
        _validate_property(key, rule, arguments[key])

    # 未在 properties 中声明的额外参数一律拒绝，防止 LLM 幻觉出未知参数
    allowed = set(properties) | {"_meta"}
    unknown = [k for k in arguments if k not in allowed]
    if unknown:
        raise ToolExecutionError(
            ToolErrorCategory.PARAMETER,
            f"工具未声明参数: {', '.join(sorted(unknown))}",
        )


def _validate_property(key: str, rule: dict[str, Any], value: Any) -> None:
    expected = rule.get("type")
    allowed_types = _SUPPORTED_TYPES.get(expected)
    if allowed_types and not isinstance(value, allowed_types):
        # integer 接受值为整数的 float（JSON 里 1.0 语义上仍是整数）
        if expected == "integer" and isinstance(value, float) and value.is_integer():
            pass
        else:
            raise ToolExecutionError(
                ToolErrorCategory.PARAMETER,
                f"参数 {key} 类型应为 {expected}，收到 {type(value).__name__}",
            )

    enum_values = rule.get("enum")
    if enum_values is not None and value not in enum_values:
        raise ToolExecutionError(
            ToolErrorCategory.PARAMETER,
            f"参数 {key} 取值 {value!r} 不在允许范围 {enum_values!r} 内",
        )

    if "minimum" in rule and isinstance(value, (int, float)) and value < rule["minimum"]:
        raise ToolExecutionError(
            ToolErrorCategory.PARAMETER,
            f"参数 {key} 不能小于 {rule['minimum']}",
        )
    if "maximum" in rule and isinstance(value, (int, float)) and value > rule["maximum"]:
        raise ToolExecutionError(
            ToolErrorCategory.PARAMETER,
            f"参数 {key} 不能大于 {rule['maximum']}",
        )

    if expected == "array" and isinstance(value, (list, tuple)) and "items" in rule:
        for i, item in enumerate(value):
            _validate_property(f"{key}[{i}]", rule["items"], item)

    if expected == "object" and isinstance(value, dict):
        for req in rule.get("required", []):
            if req not in value:
                raise ToolExecutionError(
                    ToolErrorCategory.PARAMETER,
                    f"参数 {key} 缺少子字段: {req}",
                )
        for sub_key, sub_rule in rule.get("properties", {}).items():
            if sub_key in value:
                _validate_property(f"{key}.{sub_key}", sub_rule, value[sub_key])


def truncate_output(
    output: Any,
    limit_bytes: int,
) -> tuple[Any, bool]:
    """按字节预算截断输出，返回 (输出, 是否被截断)。

    dict/list 输出截断 JSON 文本后包一层 `{"truncated": True, "output": ...}`；
    字符串直接截断并追加标记；其他类型转文本后按字符串处理。
    """

    if limit_bytes <= 0 or output is None:
        return output, False

    if isinstance(output, str):
        encoded = output.encode("utf-8")
        if len(encoded) <= limit_bytes:
            return output, False
        cut = encoded[:limit_bytes].decode("utf-8", errors="ignore")
        return cut + f"\n...[输出已截断: 原始 {len(encoded)} 字节, 预算 {limit_bytes} 字节]", True

    try:
        text = json.dumps(output, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        text = str(output)
    encoded = text.encode("utf-8")
    if len(encoded) <= limit_bytes:
        return output, False
    cut = encoded[:limit_bytes].decode("utf-8", errors="ignore")
    return {
        "truncated": True,
        "output": cut,
        "note": f"输出已截断: 原始 {len(encoded)} 字节, 预算 {limit_bytes} 字节",
    }, True


__all__ = [
    "validate_arguments",
    "truncate_output",
]
