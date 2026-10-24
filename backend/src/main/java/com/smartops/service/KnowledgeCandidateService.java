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
                "SELECT id,source_run_id,trace_id,tool_id,title,summary,content_markdown,status,created_at " +
                        "FROM knowledge_candidate" + where + " ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?",
                (rs, row) -> candidate(rs), pageArgs);
        return new KnowledgeCandidatePage(items, total, safePage, safePageSize);
    }

    public KnowledgeCandidate detail(Long userId, Long id) {
        List<KnowledgeCandidate> rows = jdbc.query(
                "SELECT id,source_run_id,trace_id,tool_id,title,summary,content_markdown,status,created_at " +
                        "FROM knowledge_candidate WHERE id=? AND user_id=?",
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
        PersonalKnowledgeService.Entry entry = personalKnowledge.createEntry(userId, libraryId, finalTitle, candidate.summary(), finalContent, "OPERATION_RUN", candidate.traceId());
        jdbc.update("UPDATE knowledge_candidate SET status='PROMOTED',updated_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=?", id, userId);
        return entry;
    }

    @Transactional
    public void reject(Long userId, Long id, String reason) {
        KnowledgeCandidate candidate = detail(userId, id);
        if (!PENDING_REVIEW.equals(candidate.status())) throw new BusinessException(409, "KNOWLEDGE_CANDIDATE_NOT_PENDING");
        String suffix = reason == null || reason.isBlank() ? "未提供" : reason.trim();
        jdbc.update("UPDATE knowledge_candidate SET status='REJECTED',summary=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=?", candidate.summary() + "\n驳回原因：" + suffix, id, userId);
    }

    private List<KnowledgeCandidate> findBySourceRun(Long userId, Long runId) {
        return jdbc.query(
                "SELECT id,source_run_id,trace_id,tool_id,title,summary,content_markdown,status,created_at FROM knowledge_candidate WHERE user_id=? AND source_run_id=?",
                (rs, row) -> candidate(rs), userId, runId);
    }

    private KnowledgeCandidate candidate(java.sql.ResultSet rs) throws java.sql.SQLException {
        return new KnowledgeCandidate(rs.getLong("id"), rs.getLong("source_run_id"),
                rs.getString("trace_id"), rs.getString("tool_id"), rs.getString("title"),
                rs.getString("summary"), rs.getString("content_markdown"), rs.getString("status"),
                rs.getTimestamp("created_at").toInstant());
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

    public record KnowledgeCandidate(Long id, Long sourceRunId, String traceId, String toolId, String title,
                                     String summary, String contentMarkdown, String status, Instant createdAt) {}
    public record KnowledgeCandidatePage(List<KnowledgeCandidate> items, long total, int page, int pageSize) {}
}
