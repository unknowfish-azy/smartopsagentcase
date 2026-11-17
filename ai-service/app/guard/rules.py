"""确定性规则表。

红线（DESIGN §0/§3）：这里只有正则与解码手段，不做语义判断；
规则必须可枚举、可单测、可给审计写明判定依据（note 字段）。
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    id: str
    pattern: "re.Pattern[str]"
    action: str      # BLOCK | REDACT
    note: str        # 判定依据（给审计/日志），不含命中原文


def _compile(*rules: Rule) -> tuple[Rule, ...]:
    return tuple(rules)


# ── 输入侧：指令覆盖 / 越狱模式（BLOCK）───────────────────────────────
# 只匹配结构化意图模式，不判断自然语言语义。
INJECTION_RULES = _compile(
    Rule(
        "INJ_OVERRIDE",
        re.compile(
            r"忽略(之前|上面|以上|前面|所有|全部).{0,8}(指令|提示|规则|设定)"
            r"|ignore\s+(all\s+|any\s+)?(previous|prior|above)\s+(instructions?|prompts?|rules?)",
            re.IGNORECASE,
        ),
        "BLOCK",
        "指令覆盖模式",
    ),
    Rule(
        "INJ_ROLE",
        re.compile(
            r"你(现在)?(是|扮演|假装)(一个)?(不受限制|没有限制|无限制|DAN|开发者模式)"
            r"|developer\s+mode|jailbreak|DAN\s+mode",
            re.IGNORECASE,
        ),
        "BLOCK",
        "越狱角色扮演模式",
    ),
    Rule(
        "INJ_LEAK_PROMPT",
        re.compile(
            r"(打印|输出|复述|重复|泄露|show\s+me|reveal|repeat).{0,12}"
            r"(system\s*prompt|系统提示|初始指令|原始指令|系统设定)",
            re.IGNORECASE,
        ),
        "BLOCK",
        "系统提示套取模式",
    ),
)

# ── PII（REDACT，输入输出两侧共用）────────────────────────────────────
PII_RULES = _compile(
    Rule(
        "PII_ID",
        re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"),
        "REDACT",
        "身份证号",
    ),
    Rule(
        "PII_PHONE",
        re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
        "REDACT",
        "手机号",
    ),
    Rule(
        "PII_KEY",
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
        "REDACT",
        "私钥材料",
    ),
)

# ── 输出侧：越权承诺（REDACT）────────────────────────────────────────
# 与 F10 工具级口径对齐：只匹配「未声明工具调用却声称已执行破坏性操作」的
# 确定性字面，不做语义判断。
OUTPUT_RULES = _compile(
    Rule(
        "OUT_CLAIM_EXEC",
        re.compile(
            r"我(已经|已|刚刚).{0,8}"
            r"(执行|删除|删掉|清空|重启|关闭|停止|格式化|drop\s+database|rm\s+-rf)"
            r".{0,10}(数据库|表|服务|服务器|文件|磁盘|集群|库|生产)",
            re.IGNORECASE,
        ),
        "REDACT",
        "未经工具确认的执行声称",
    ),
)

# ── 不可见字符（绕过检测用的零宽/双向控制符）──────────────────────────
ZERO_WIDTH = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060\ufeff]")
INVISIBLE_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

REDACT_PLACEHOLDER = "[已脱敏]"
