package com.smartops.guard;

/**
 * 智测盾用例分类。OWASP 映射用于报告中的合规说明，不参与打分。
 */
public enum GuardCategory {

    PROMPT_INJECTION("提示注入", "LLM01: Prompt Injection"),
    JAILBREAK("越狱与角色劫持", "LLM01: Prompt Injection"),
    DATA_EXFILTRATION("敏感数据外泄", "LLM06: Sensitive Information Disclosure"),
    TOOL_ABUSE("工具滥用", "LLM08: Excessive Agency"),
    PRIVILEGE_ESCALATION("越权与审计绕过", "LLM08: Excessive Agency"),
    ROBUSTNESS("编码与鲁棒性", "LLM01: Prompt Injection");

    private final String label;
    private final String owasp;

    GuardCategory(String label, String owasp) {
        this.label = label;
        this.owasp = owasp;
    }

    public String label() {
        return label;
    }

    public String owasp() {
        return owasp;
    }
}
