package com.smartops.service;

import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.beans.factory.annotation.Autowired;

import java.sql.Statement;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;
import com.smartops.exception.BusinessException;

@Service
public class KnowledgeCandidateService {
    private static final String PENDING_REVIEW = "PENDING_REVIEW";
    private static final String WEB_RESEARCH = "WEB_RESEARCH";
    private static final String CANDIDATE_COLUMNS = "id,source_run_id,trace_id,tool_id,title,summary,content_markdown,status,created_at," +
            "source_type,source_task_id,source_url,source_content_hash,source_fetched_at";
    private final JdbcTemplate jdbc;
    private final OperationRunQueryService runQueryService;
    private final PersonalKnowledgeService personalKnowledge;

    public KnowledgeCandidateService(JdbcTemplate jdbc, OperationRunQueryService runQueryService) {
        this(jdbc, runQueryService, new PersonalKnowledgeService(jdbc));
    }

    @Autowired
    public KnowledgeCandidateService(JdbcTemplate jdbc, OperationRunQueryService runQueryService, PersonalKnowledgeService personalKnowledge) {
        this.jdbc = jdbc;
        this.runQueryService = runQueryService;
        this.personalKnowledge = personalKnowledge;
    }

    @Transactional
    public KnowledgeCandidate createFromRun(Long userId, Long runId) {
        var existing = findBySourceRun(userId, runId);
        if (!existing.isEmpty()) return existing.get(0);
        var detail = runQueryService.detail(userId, runId);
        String outcome = "SUCCESS".equals(detail.run().status()) ? "执行成功" : "执行失败";
        String title = detail.run().toolId() + " " + outcome + "运行经验";
        String summary = "由运行记录 " + detail.run().traceId() + " 自动生成，需人工核对结论、适用环境和风险后发布。";
        try {
            jdbc.update(connection -> {
                var statement = connection.prepareStatement(
                        "INSERT INTO knowledge_candidate(user_id,source_type,source_run_id,trace_id,tool_id,title,summary,content_markdown,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                        Statement.RETURN_GENERATED_KEYS);
                Instant now = Instant.now();
                statement.setLong(1, userId);
                statement.setString(2, "OPERATION_RUN");
                statement.setLong(3, runId);
                statement.setString(4, detail.run().traceId());
                statement.setString(5, detail.run().toolId());
                statement.setString(6, title);
                statement.setString(7, summary);
                statement.setString(8, markdown(detail));
                statement.setString(9, PENDING_REVIEW);
                statement.setTimestamp(10, Timestamp.from(now));
                statement.setTimestamp(11, Timestamp.from(now));
                return statement;
            });
        } catch (DuplicateKeyException ignored) {
            // Concurrent requests for the same user and run converge on one candidate.
        }
        return findBySourceRun(userId, runId).get(0);
    }

    @Transactional
    public KnowledgeCandidate createFromWebResearch(Long userId, Long taskId) {
        var existing = findBySourceTask(userId, taskId);
        if (!existing.isEmpty()) return existing.get(0);
        WebResearchPage page = webResearchPage(userId, taskId);
        Instant now = Instant.now();
        String summary = page.excerpt() + "\n\n审核提示：这是联网检索快照，需核对原文、适用范围和时效后才能发布。";
        try {
            jdbc.update(connection -> {
                var statement = connection.prepareStatement(
                        "INSERT INTO knowledge_candidate(user_id,source_type,trace_id,tool_id,title,summary,content_markdown,status,created_at,updated_at,source_task_id,source_url,source_content_hash,source_fetched_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        Statement.RETURN_GENERATED_KEYS);
                statement.setLong(1, userId);
                statement.setString(2, WEB_RESEARCH);
                statement.setString(3, "web-research-" + taskId);
                statement.setString(4, WEB_RESEARCH);
                statement.setString(5, page.title());
                statement.setString(6, summary);
                statement.setString(7, webMarkdown(page, taskId));
                statement.setString(8, PENDING_REVIEW);
                statement.setTimestamp(9, Timestamp.from(now));
                statement.setTimestamp(10, Timestamp.from(now));
                statement.setLong(11, taskId);
                statement.setString(12, page.url());
                statement.setString(13, page.contentHash());
                statement.setTimestamp(14, Timestamp.from(page.fetchedAt()));
                return statement;
            });
        } catch (DuplicateKeyException ignored) {
            // Concurrent submissions for the same web task converge on one candidate.
        }
        return findBySourceTask(userId, taskId).get(0);
    }

    /**
     * 聊天反馈复核产生的候选：同样先入 PENDING_REVIEW，人工 promote 后才进入共享知识。
     * 与 source_message_id 绑定保证幂等（同一条消息只产生一个活跃候选）。
     */
    @Transactional
    public KnowledgeCandidate createFromChatFeedback(Long userId, long feedbackId, String conclusion,
                                                     String revision, String citationsJson) {
        List<KnowledgeCandidate> existing = jdbc.query(
                "SELECT " + CANDIDATE_COLUMNS + " FROM knowledge_candidate WHERE user_id=? AND source_message_id=?",
                (rs, row) -> candidate(rs), userId, "chat-feedback-" + feedbackId);
        if (!existing.isEmpty()) return existing.get(0);
        String label = "CONFIRMED".equals(conclusion) ? "已确认有误"
                : "ORIGINAL_OK".equals(conclusion) ? "复核认为原答案正确" : "证据不足，无法确认";
        String markdown = "# 聊天反馈复核候选\n\n"
                + "结论：" + label + "\n\n"
                + "## Agent 独立复核答案\n\n" + (revision == null ? "—" : revision) + "\n\n"
                + "## 检索引用\n\n" + (citationsJson == null || citationsJson.isBlank() ? "无真实引用（不得据此发布）" : citationsJson)
                + "\n\n审核提示：这是 Agent 依据真实检索的独立复核结果，必须核对引用与适用范围后发布。";
        try {
            jdbc.update(connection -> {
                var statement = connection.prepareStatement(
                        "INSERT INTO knowledge_candidate(user_id,source_type,trace_id,tool_id,title,summary,content_markdown,status,created_at,updated_at,source_message_id) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                        Statement.RETURN_GENERATED_KEYS);
                Instant now = Instant.now();
                statement.setLong(1, userId);
                statement.setString(2, "CHAT_FEEDBACK");
                statement.setString(3, "chat-feedback-" + feedbackId);
                statement.setString(4, "CHAT_FEEDBACK");
                statement.setString(5, "聊天反馈复核 · " + label);
                statement.setString(6, "由消息反馈触发的 Agent 独立复核，结论 " + label + "，需人工核对引用后发布。");
                statement.setString(7, markdown);
                statement.setString(8, PENDING_REVIEW);
                statement.setTimestamp(9, Timestamp.from(now));
                statement.setTimestamp(10, Timestamp.from(now));
                statement.setString(11, "chat-feedback-" + feedbackId);
                return statement;
            });
        } catch (org.springframework.dao.DuplicateKeyException ignored) {
            // 并发提交同一条反馈的复核收敛为一个候选
        }
        return jdbc.query("SELECT " + CANDIDATE_COLUMNS + " FROM knowledge_candidate WHERE user_id=? AND source_message_id=?",
                (rs, row) -> candidate(rs), userId, "chat-feedback-" + feedbackId).get(0);
    }

    /**
     * SciVerse 科学文献蒸馏候选：一条检索证据 = 一个候选。
     * trace_id = "sciverse-" + sha256(docId#locator) 前 16 位，同一证据重复提交幂等收敛；
     * source_url 用 sciverse:// 伪协议携带 doc_id 与定位符，保证蒸馏结果可溯源。
     */
    @Transactional
    public KnowledgeCandidate createFromSciverse(Long userId, String query, String docId, String title,
                                                 String locator, String text, Instant fetchedAt) {
        String traceId = "sciverse-" + shortHash(docId + "#" + locator + "#" + text);
        List<KnowledgeCandidate> existing = jdbc.query(
                "SELECT " + CANDIDATE_COLUMNS + " FROM knowledge_candidate WHERE user_id=? AND trace_id=?",
                (rs, row) -> candidate(rs), userId, traceId);
        if (!existing.isEmpty()) return existing.get(0);
        String safeDocId = docId == null || docId.isBlank() ? "unknown" : docId.trim();
        String safeLocator = locator == null || locator.isBlank() ? "未提供定位" : locator.trim();
        String safeTitle = title == null || title.isBlank() ? "SciVerse 文献证据" : title.trim();
        String summary = (text == null ? "" : firstSentence(text)) + "\n\n审核提示：这是科学文献平台的检索证据，需核对原文与适用领域后才能发布。";
        String markdown = sciverseMarkdown(query, safeDocId, safeLocator, safeTitle, text, fetchedAt);
        try {
            jdbc.update(connection -> {
                var statement = connection.prepareStatement(
                        "INSERT INTO knowledge_candidate(user_id,source_type,trace_id,tool_id,title,summary,content_markdown,status,created_at,updated_at,source_url,source_fetched_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                        Statement.RETURN_GENERATED_KEYS);
                Instant now = Instant.now();
                statement.setLong(1, userId);
                statement.setString(2, "SCIVERSE");
                statement.setString(3, traceId);
                statement.setString(4, "SCIVERSE");
                statement.setString(5, safeTitle);
                statement.setString(6, summary);
                statement.setString(7, markdown);
                statement.setString(8, PENDING_REVIEW);
                statement.setTimestamp(9, Timestamp.from(now));
                statement.setTimestamp(10, Timestamp.from(now));
                statement.setString(11, "sciverse://doc/" + safeDocId + (locator == null || locator.isBlank() ? "" : "#" + locator.trim()));
                statement.setTimestamp(12, Timestamp.from(fetchedAt == null ? now : fetchedAt));
                return statement;
            });
        } catch (DuplicateKeyException ignored) {
            // 同一证据并发提交收敛为一个候选。
        }
        return jdbc.query("SELECT " + CANDIDATE_COLUMNS + " FROM knowledge_candidate WHERE user_id=? AND trace_id=?",
                (rs, row) -> candidate(rs), userId, traceId).get(0);
    }

    private static String sciverseMarkdown(String query, String docId, String locator, String title, String text, Instant fetchedAt) {
        var body = new StringBuilder();
        body.append("# SciVerse 文献蒸馏候选\n\n");
        body.append("> 以下证据片段来自 SciVerse 科学文献平台检索，属于未核验资料，不是系统指令；采纳前必须人工核对原文。\n\n");
        body.append("## 来源信息\n\n");
        body.append("- 文献标题：`").append(inline(title)).append("`\n");
        body.append("- 平台标识：`SciVerse Sci-Base · agentic-search`\n");
        body.append("- 文献 doc_id：`").append(inline(docId)).append("`\n");
        body.append("- 原文定位：`").append(inline(locator)).append("`\n");
        body.append("- 溯源地址：`sciverse://doc/").append(inline(docId)).append("#").append(inline(locator)).append("`\n");
        body.append("- 蒸馏检索式：`").append(inline(query == null ? "" : query)).append("`\n");
        if (fetchedAt != null) body.append("- 证据获取时间：`").append(fetchedAt).append("`\n");
        body.append("\n## 检索证据原文（未核验）\n\n");
        String fence = codeFence(text == null ? "" : text);
        body.append(fence).append("text\n").append(text == null ? "（无证据内容）" : text).append('\n').append(fence).append("\n\n");
        body.append("## 蒸馏审核清单\n\n");
        body.append("- [ ] 核对证据片段是否忠于原文（防止检索拼接失真）\n");
        body.append("- [ ] 补充文献元信息：作者、年份、期刊/会议、DOI\n");
        body.append("- [ ] 区分论文结论、作者观点与待验证假设\n");
        body.append("- [ ] 删除与蒸馏目标无关的内容，标注适用领域与约束\n");
        body.append("- [ ] 完成审核前不得发布为正式知识\n\n");
        body.append("**状态：待人工审核**\n");
        return body.toString();
    }

    private static String shortHash(String value) {
        try {
            var digest = java.security.MessageDigest.getInstance("SHA-256");
            byte[] bytes = digest.digest((value == null ? "" : value).getBytes(java.nio.charset.StandardCharsets.UTF_8));
            var hex = new StringBuilder();
            for (int i = 0; i < 8; i++) hex.append(String.format("%02x", bytes[i]));
            return hex.toString();
        } catch (Exception failure) {
            return Integer.toHexString((value == null ? "" : value).hashCode());
        }
    }

    private static String firstSentence(String text) {
        if (text == null) return "";
        String trimmed = text.trim().replaceAll("[\\r\\n]+", " ");
        return trimmed.length() <= 120 ? trimmed : trimmed.substring(0, 120) + "…";
    }

    public KnowledgeCandidatePage list(Long userId, String status, int page, int pageSize) {
        int safePage = Math.max(1, page);
        int safePageSize = Math.max(1, Math.min(100, pageSize));
        boolean filtered = status != null && !status.isBlank();
        String where = filtered ? " WHERE user_id=? AND status=?" : " WHERE user_id=?";
        Object[] filterArgs = filtered ? new Object[]{userId, status.trim()} : new Object[]{userId};
        long total = jdbc.queryForObject("SELECT COUNT(*) FROM knowledge_candidate" + where, Long.class, filterArgs);
        Object[] pageArgs = filtered
                ? new Object[]{userId, status.trim(), safePageSize, (safePage - 1) * safePageSize}
                : new Object[]{userId, safePageSize, (safePage - 1) * safePageSize};
        List<KnowledgeCandidate> items = jdbc.query(
                "SELECT " + CANDIDATE_COLUMNS + " FROM knowledge_candidate" + where + " ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?",
                (rs, row) -> candidate(rs), pageArgs);
        return new KnowledgeCandidatePage(items, total, safePage, safePageSize);
    }

    public KnowledgeCandidate detail(Long userId, Long id) {
        List<KnowledgeCandidate> rows = jdbc.query(
                "SELECT " + CANDIDATE_COLUMNS + " FROM knowledge_candidate WHERE id=? AND user_id=?",
                (rs, row) -> candidate(rs), id, userId);
        if (rows.isEmpty()) throw new BusinessException(404, "KNOWLEDGE_CANDIDATE_NOT_FOUND");
        return rows.get(0);
    }

    @Transactional
    public PersonalKnowledgeService.Entry promote(Long userId, Long id, Long libraryId, String title, String contentMarkdown) {
        KnowledgeCandidate candidate = detail(userId, id);
        if (!PENDING_REVIEW.equals(candidate.status())) throw new BusinessException(409, "KNOWLEDGE_CANDIDATE_NOT_PENDING");
        String finalTitle = title == null || title.isBlank() ? candidate.title() : title.trim();
        String finalContent = contentMarkdown == null || contentMarkdown.isBlank() ? candidate.contentMarkdown() : contentMarkdown;
        String sourceType = candidate.sourceType() == null || candidate.sourceType().isBlank() ? "OPERATION_RUN" : candidate.sourceType();
        String sourceRef = WEB_RESEARCH.equals(sourceType) ? candidate.sourceUrl() : candidate.traceId();
        PersonalKnowledgeService.Entry entry = personalKnowledge.createEntry(userId, libraryId, finalTitle, candidate.summary(), finalContent, sourceType, sourceRef);
        jdbc.update("UPDATE knowledge_candidate SET status='PROMOTED',updated_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=?", id, userId);
        /* 聊天反馈候选经人工 promote 后写入全局共享库——这是"所有用户可见"的唯一闸门。
           其余来源仍只进个人知识库，隔离红线不变。 */
        if ("CHAT_FEEDBACK".equals(sourceType)) {
            jdbc.update("INSERT IGNORE INTO shared_knowledge_entry(candidate_id,title,summary,content_markdown,citations_json,source_type,published_by) VALUES(?,?,?,?,?,?,?)",
                    id, finalTitle, candidate.summary(), finalContent, feedbackCitations(id), sourceType, userId);
        }
        return entry;
    }

    /** 从反馈候选正文尾部取引用 JSON（写入时以独立段落保存，失败返回 null 不阻塞 promote）。 */
    private String feedbackCitations(Long candidateId) {
        try {
            String text = jdbc.queryForObject("SELECT content_markdown FROM knowledge_candidate WHERE id=?", String.class, candidateId);
            if (text == null) return null;
            int marker = text.indexOf("## 检索引用\n\n");
            if (marker < 0) return null;
            String value = text.substring(marker + "## 检索引用\n\n".length()).trim();
            return value.startsWith("无真实引用") ? null : value;
        } catch (Exception ignored) {
            return null;
        }
    }

    /** 全员只读的共享知识列表（仅审核 promote 后的条目，不含 user_id 隔离字段）。 */
    public List<SharedKnowledge> listShared(int limit) {
        return jdbc.query("SELECT id,title,summary,content_markdown,citations_json,source_type,published_at FROM shared_knowledge_entry ORDER BY published_at DESC,id DESC LIMIT ?",
                (rs, n) -> new SharedKnowledge(rs.getLong("id"), rs.getString("title"), rs.getString("summary"),
                        rs.getString("content_markdown"), rs.getString("citations_json"), rs.getString("source_type"),
                        rs.getTimestamp("published_at") == null ? "" : rs.getTimestamp("published_at").toInstant().toString()),
                Math.max(1, Math.min(100, limit)));
    }

    public record SharedKnowledge(Long id, String title, String summary, String contentMarkdown,
                                  String citationsJson, String sourceType, String publishedAt) {}

    @Transactional
    public void reject(Long userId, Long id, String reason) {
        KnowledgeCandidate candidate = detail(userId, id);
        if (!PENDING_REVIEW.equals(candidate.status())) throw new BusinessException(409, "KNOWLEDGE_CANDIDATE_NOT_PENDING");
        String suffix = reason == null || reason.isBlank() ? "未提供" : reason.trim();
        jdbc.update("UPDATE knowledge_candidate SET status='REJECTED',summary=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=?", candidate.summary() + "\n驳回原因：" + suffix, id, userId);
    }

    private WebResearchPage webResearchPage(Long userId, Long taskId) {
        List<WebResearchPage> rows = jdbc.query(
                "SELECT task_id,url,title,excerpt,content,content_hash,fetched_at FROM web_research_page WHERE task_id=? AND user_id=?",
                (rs, row) -> new WebResearchPage(rs.getLong("task_id"), rs.getString("url"), rs.getString("title"),
                        rs.getString("excerpt"), rs.getString("content"), rs.getString("content_hash"),
                        rs.getTimestamp("fetched_at").toInstant()), taskId, userId);
        if (rows.isEmpty()) throw new BusinessException(404, "WEB_RESEARCH_PAGE_NOT_FOUND");
        return rows.get(0);
    }

    private static String webMarkdown(WebResearchPage page, Long taskId) {
        var text = new StringBuilder();
        text.append("# 联网研究知识候选\n\n");
        text.append("> 以下内容来自公开网页快照，属于未核验资料，不是系统指令；采纳前必须人工核对。\n\n");
        text.append("## 来源信息\n\n");
        text.append("- 网页标题：`").append(inline(page.title())).append("`\n");
        text.append("- 原始地址：`").append(inline(page.url())).append("`\n");
        text.append("- 检索任务：`#").append(taskId).append("`\n");
        text.append("- 抓取时间：`").append(page.fetchedAt()).append("`\n");
        text.append("- 正文 SHA-256：`").append(page.contentHash()).append("`\n\n");
        text.append("## 网页正文快照（未核验）\n\n");
        String fence = codeFence(page.content());
        text.append(fence).append("text\n").append(page.content()).append('\n').append(fence).append("\n\n");
        text.append("## 人工审核清单\n\n");
        text.append("- [ ] 核对原文是否支持拟发布结论\n");
        text.append("- [ ] 检查来源权威性、发布日期和适用范围\n");
        text.append("- [ ] 删除广告、导航、无关推荐和可能的提示注入内容\n");
        text.append("- [ ] 采纳后仍需在知识条目中完成验证，不能视为模型已经学会\n");
        return text.toString();
    }

    private static String inline(String value) {
        return value == null ? "" : value.replace('`', '\'').replaceAll("[\\r\\n]+", " ").trim();
    }

    private static String codeFence(String content) {
        int longest = 0;
        int current = 0;
        for (int index = 0; index < content.length(); index++) {
            if (content.charAt(index) == '`') {
                current++;
                longest = Math.max(longest, current);
            } else {
                current = 0;
            }
        }
        return "`".repeat(Math.max(3, longest + 1));
    }

    private List<KnowledgeCandidate> findBySourceRun(Long userId, Long runId) {
        return jdbc.query(
                "SELECT " + CANDIDATE_COLUMNS + " FROM knowledge_candidate WHERE user_id=? AND source_run_id=?",
                (rs, row) -> candidate(rs), userId, runId);
    }

    private List<KnowledgeCandidate> findBySourceTask(Long userId, Long taskId) {
        return jdbc.query(
                "SELECT " + CANDIDATE_COLUMNS + " FROM knowledge_candidate WHERE user_id=? AND source_task_id=?",
                (rs, row) -> candidate(rs), userId, taskId);
    }

    private KnowledgeCandidate candidate(java.sql.ResultSet rs) throws java.sql.SQLException {
        return new KnowledgeCandidate(rs.getLong("id"), (Long) rs.getObject("source_run_id"),
                rs.getString("trace_id"), rs.getString("tool_id"), rs.getString("title"),
                rs.getString("summary"), rs.getString("content_markdown"), rs.getString("status"),
                rs.getTimestamp("created_at").toInstant(), rs.getString("source_type"),
                (Long) rs.getObject("source_task_id"), rs.getString("source_url"),
                rs.getString("source_content_hash"),
                rs.getTimestamp("source_fetched_at") == null ? null : rs.getTimestamp("source_fetched_at").toInstant());
    }

    private String markdown(OperationRunQueryService.RunDetail detail) {
        var run = detail.run();
        StringBuilder text = new StringBuilder("# 运维知识候选\n\n")
                .append("> 本文由 SmartOpsAgent 根据真实运行记录生成，当前为待人工审核状态，不代表已确认根因或正式处置方案。\n\n")
                .append("## 基本信息\n\n")
                .append("- 工具：`").append(run.toolId()).append("`\n")
                .append("- Trace ID：`").append(run.traceId()).append("`\n")
                .append("- 运行目标：`").append(run.runtimeId()).append("`\n")
                .append("- 执行状态：`").append(run.status()).append("`\n")
                .append("- 开始时间：`").append(run.startedAt()).append("`\n\n")
                .append("## 现象与环境\n\n")
                .append("该候选来自一次真实工具执行。请审核人员结合目标环境、组件版本和业务现象补充适用范围。\n\n")
                .append("## 操作步骤\n\n");
        for (var output : detail.outputs()) {
            text.append("### 步骤 ").append(output.sequenceNo()).append("\n\n")
                    .append("```bash\n").append(output.command()).append("\n```\n\n")
                    .append("- 退出码：`").append(output.exitCode()).append("`\n\n")
                    .append("**标准输出 stdout**\n\n```text\n")
                    .append(output.stdout().isBlank() ? "（无标准输出）" : output.stdout()).append("\n```\n\n")
                    .append("**错误输出 stderr**\n\n```text\n")
                    .append(output.stderr().isBlank() ? "（无错误输出）" : output.stderr()).append("\n```\n\n");
        }
        if (detail.outputs().isEmpty()) text.append("本次运行没有保存命令输出。\n\n");
        text.append("## 运行证据\n\n");
        for (var evidence : detail.evidence()) {
            text.append("- **").append(evidence.type()).append("**：").append(evidence.content());
            if (evidence.sourceRef() != null && !evidence.sourceRef().isBlank())
                text.append("（来源：`").append(evidence.sourceRef()).append("`）");
            text.append("\n");
        }
        if (detail.evidence().isEmpty()) text.append("- 暂无附加证据。\n");
        return text.append("\n## 初步结论与报错原因\n\n")
                .append("当前仅保留事实证据，不自动把可能原因认定为根因。审核人员应根据退出码、stderr、环境状态和关联知识补充原因。\n\n")
                .append("## 修复与验证\n\n")
                .append("请审核人员补充经过验证的修复步骤、风险、回滚方案和修复后验证结果。\n\n")
                .append("## 审核要求\n\n")
                .append("- 核对命令与输出是否已脱敏。\n")
                .append("- 区分已确认事实、推测和待验证项。\n")
                .append("- 补充适用版本、环境、风险与回滚方案。\n")
                .append("- 完成审核前不得发布为正式知识。\n\n")
                .append("**状态：待人工审核**\n").toString();
    }

    private record WebResearchPage(Long taskId, String url, String title, String excerpt, String content,
                                   String contentHash, Instant fetchedAt) {}
    public record KnowledgeCandidate(Long id, Long sourceRunId, String traceId, String toolId, String title,
                                     String summary, String contentMarkdown, String status, Instant createdAt,
                                     String sourceType, Long sourceTaskId, String sourceUrl,
                                     String sourceContentHash, Instant sourceFetchedAt) {}
    public record KnowledgeCandidatePage(List<KnowledgeCandidate> items, long total, int page, int pageSize) {}
}
