package com.smartops.service.modelconfig;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

import java.util.List;

/**
 * 路由意图词表：把"用户说了什么"映射成"需要什么模型能力"。
 *
 * <p>词表放在配置里而不是代码里，运营新增一个意图词不需要发版；
 * 未配置时使用内置默认词表，保证空配置下行为不变。</p>
 */
@Component
@ConfigurationProperties(prefix = "smartops.model.routing")
public class ModelRoutingProperties {

    private List<IntentPattern> intentPatterns = List.of();

    public List<IntentPattern> getIntentPatterns() {
        return intentPatterns;
    }

    public void setIntentPatterns(List<IntentPattern> intentPatterns) {
        this.intentPatterns = intentPatterns == null ? List.of() : intentPatterns;
    }

    public static class IntentPattern {
        private String keyword;
        private String capability;

        public IntentPattern() {
        }

        public IntentPattern(String keyword, String capability) {
            this.keyword = keyword;
            this.capability = capability;
        }

        public String getKeyword() {
            return keyword;
        }

        public void setKeyword(String keyword) {
            this.keyword = keyword;
        }

        public String getCapability() {
            return capability;
        }

        public void setCapability(String capability) {
            this.capability = capability;
        }
    }

    /** 内置默认词表：与历史硬编码行为保持一致。 */
    public static List<IntentPattern> defaultPatterns() {
        return List.of(
                new IntentPattern("看图", "vision"),
                new IntentPattern("截图", "vision"),
                new IntentPattern("图片", "vision"),
                new IntentPattern("图像", "vision"),
                new IntentPattern("vision", "vision"),
                new IntentPattern("理解图", "vision"),
                new IntentPattern("诊断", "reasoning"),
                new IntentPattern("分析", "reasoning"),
                new IntentPattern("排查", "reasoning"),
                new IntentPattern("根因", "reasoning"),
                new IntentPattern("复杂", "reasoning"),
                new IntentPattern("规划", "reasoning"),
                new IntentPattern("temperature", "reasoning"),
                new IntentPattern("工具", "tool-calling"),
                new IntentPattern("调用", "tool-calling"),
                new IntentPattern("agent", "tool-calling"),
                new IntentPattern("function", "tool-calling"),
                new IntentPattern("tool", "tool-calling"),
                new IntentPattern("简单", "fast"),
                new IntentPattern("快速", "fast"),
                new IntentPattern("快", "fast"),
                new IntentPattern("便宜", "cheap"),
                new IntentPattern("省钱", "cheap"),
                new IntentPattern("cheap", "cheap")
        );
    }
}
