package com.smartops.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartops.assistant.MiniAssistantEngine;
import com.smartops.exception.BusinessException;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.sql.Statement;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * 聊天消息反馈 → Agent 独立复核 → 待审核知识候选。
 *
 * 红线：
 * 1. Agent 必须放下原答案独立作答，走真实检索；结论只有 CONFIRMED / UNCONFIRMED / ORIGINAL_OK 三态。
 * 2. 无检索证据时结论为 UNCONFIRMED，不编造修正答案。
 * 3. 复核结果永远先入 PENDING_REVIEW，人工 promote 后才全员可见。
 * 4. 反馈与候选仍按 user_id 隔离；只有 shared_knowledge_entry 全员只读。
 */
@Service
public class ChatFeedbackService {
    public static final String REVIEWING = "REVIEWING";
    public static final String CONFIRMED = "CONFIRMED";
    public static final String UNCONFIRMED = "UNCONFIRMED";
    public static final String ORIGINAL_OK = "ORIGINAL_OK";
    public static final String REVIEW_FAILED = "REVIEW_FAILED";

    private static final String FEEDBACK_COLUMNS = "id,user_id,conversation_id,message_id,prompt,original_answer,issue_type,description,expected,status,review_conclusion,revision,citations_json,provider_key,created_at,updated_at";

    private final JdbcTemplate jdbc;
    private final MiniAssistantEngine mini;
    private final KnowledgeCandidateService candidates;
    private final ObjectMapper mapper;

    public ChatFeedbackService(JdbcTemplate jdbc, MiniAssistantEngine mini,
                               KnowledgeCandidateService candidates, ObjectMapper mapper) {
        this.jdbc = jdbc;
        this.mini = mini;
        this.candidates = candidates;
        this.mapper = mapper;
    }

    @Transactional
    public Feedback create(Long userId, FeedbackRequest request) {
        if (request == null || request.messageId() == null || request.messageId().isBlank())
            throw new BusinessException(400, "CHAT_FEEDBACK_MESSAGE_REQUIRED");
        if (request.description() == null || request.description().trim().length() < 10)
            throw new BusinessException(400, "CHAT_FEEDBACK_DESCRIPTION_TOO_SHORT");
        var existing = findByMessage(userId, request.messageId());
        if (existing != null) throw new BusinessException(409, "CHAT_FEEDBACK_ALREADY_EXISTS");

        var keyHolder = new org.springframework.jdbc.support.GeneratedKeyHolder();
        try {
            jdbc.update(connection -> {
                var ps = connection.prepareStatement(
                        "INSERT INTO chat_feedback(user_id,conversation_id,message_id,prompt,original_answer,issue_type,description,expected,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                        Statement.RETURN_GENERATED_KEYS);
                ps.setLong(1, userId);
                ps.setString(2, safe(request.conversationId()));
                ps.setString(3, request.messageId().trim());
                ps.setString(4, safe(request.prompt()));
                ps.setString(5, safe(request.originalAnswer()));
                ps.setString(6, safe(request.issueType()));
                ps.setString(7, request.description().trim());
                ps.setString(8, safe(request.expected()));
                ps.setString(9, REVIEWING);
                var now = java.sql.Timestamp.from(Instant.now());
                ps.setTimestamp(10, now);
                ps.setTimestamp(11, now);
                return ps;
            }, keyHolder);
        } catch (DuplicateKeyException duplicate) {
            throw new BusinessException(409, "CHAT_FEEDBACK_ALREADY_EXISTS");
        }
        Number generated = keyHolder.getKey();
        if (generated == null) throw new BusinessException(500, "CHAT_FEEDBACK_CREATE_FAILED");
        return independentReview(userId, generated.longValue());
    }

    /** 真调用 Agent 独立复核：明确要求忽略原答案，只用问题 + 用户反馈重新检索作答。 */
    @Transactional
    public Feedback independentReview(Long userId, long feedbackId) {
        Feedback current = detail(userId, feedbackId);
        if (!REVIEWING.equals(current.status()) && !REVIEW_FAILED.equals(current.status()))
            throw new BusinessException(409, "CHAT_FEEDBACK_ALREADY_REVIEWED");

        String reviewPrompt = "请暂时忽略下面标注为「原答案」的内容，独立回答用户问题。" +
                "你只能依据当前可用的真实知识库与工具检索结果作答；如果没有足够证据，明确说「证据不足，无法确认」。\n\n" +
                "用户问题：" + current.prompt() + "\n\n" +
                "用户对原答案的反馈（" + current.issueType() + "）：" + current.description() + "\n" +
                (current.expected() == null || current.expected().isBlank() ? "" : "用户期望：" + current.expected() + "\n") +
                "\n原答案（仅供最后对比，不要作为依据）：" + abbreviate(current.originalAnswer(), 2000);

        String conclusion;
        String revision;
        String citationsJson;
        String providerKey;
        try {
            MiniAssistantEngine.Reply reply = mini.generate(reviewPrompt, List.of());
            revision = reply.content();
            citationsJson = mapper.writeValueAsString(reply.citations());
            providerKey = reply.model();
            conclusion = decideConclusion(reply);
        } catch (Exception failure) {
            jdbc.update("UPDATE chat_feedback SET status=?,review_conclusion=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=?",
                    REVIEW_FAILED, "AGENT_UNAVAILABLE", feedbackId, userId);
            return detail(userId, feedbackId);
        }

        jdbc.update("UPDATE chat_feedback SET status='REVIEWED',review_conclusion=?,revision=?,citations_json=?,provider_key=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=?",
                conclusion, revision, citationsJson, providerKey, feedbackId, userId);

        /* 无论结论三态，都生成待审核候选：审核员要能看到「用户说错了」的复核证据，避免错误扩散。 */
        candidates.createFromChatFeedback(userId, feedbackId, conclusion, revision, citationsJson);
        return detail(userId, feedbackId);
    }

    /**
     * 三态判定：无真实引用 → UNCONFIRMED；独立答案明确否定原答案 → CONFIRMED；
     * 独立答案与原答案一致（或明确支持）→ ORIGINAL_OK。不凭猜测下结论。
     */
    static String decideConclusion(MiniAssistantEngine.Reply reply) {
        if (reply.citations() == null || reply.citations().isEmpty()) return UNCONFIRMED;
        String text = reply.content() == null ? "" : reply.content().toLowerCase();
        if (text.contains("证据不足") || text.contains("无法确认")) return UNCONFIRMED;
        if (text.contains("原答案正确") || text.contains("原回答正确")) return ORIGINAL_OK;
        return CONFIRMED;
    }

    public Feedback detail(Long userId, long id) {
        var rows = jdbc.query("SELECT " + FEEDBACK_COLUMNS + " FROM chat_feedback WHERE id=? AND user_id=?",
                (rs, n) -> new Feedback(rs.getLong("id"), rs.getLong("user_id"), rs.getString("conversation_id"),
                        rs.getString("message_id"), rs.getString("prompt"), rs.getString("original_answer"),
                        rs.getString("issue_type"), rs.getString("description"), rs.getString("expected"),
                        rs.getString("status"), rs.getString("review_conclusion"), rs.getString("revision"),
                        rs.getString("citations_json"), rs.getString("provider_key"),
                        rs.getTimestamp("created_at") == null ? "" : rs.getTimestamp("created_at").toInstant().toString(),
                        rs.getTimestamp("updated_at") == null ? "" : rs.getTimestamp("updated_at").toInstant().toString()), id, userId);
        if (rows.isEmpty()) throw new BusinessException(404, "CHAT_FEEDBACK_NOT_FOUND");
        return rows.get(0);
    }

    public Feedback findByMessage(Long userId, String messageId) {
        var rows = jdbc.query("SELECT " + FEEDBACK_COLUMNS + " FROM chat_feedback WHERE user_id=? AND message_id=? ORDER BY id DESC LIMIT 1",
                (rs, n) -> new Feedback(rs.getLong("id"), rs.getLong("user_id"), rs.getString("conversation_id"),
                        rs.getString("message_id"), rs.getString("prompt"), rs.getString("original_answer"),
                        rs.getString("issue_type"), rs.getString("description"), rs.getString("expected"),
                        rs.getString("status"), rs.getString("review_conclusion"), rs.getString("revision"),
                        rs.getString("citations_json"), rs.getString("provider_key"),
                        rs.getTimestamp("created_at") == null ? "" : rs.getTimestamp("created_at").toInstant().toString(),
                        rs.getTimestamp("updated_at") == null ? "" : rs.getTimestamp("updated_at").toInstant().toString()), userId, messageId);
        return rows.isEmpty() ? null : rows.get(0);
    }

    public List<Feedback> listMine(Long userId, int limit) {
        return jdbc.query("SELECT " + FEEDBACK_COLUMNS + " FROM chat_feedback WHERE user_id=? ORDER BY id DESC LIMIT ?",
                (rs, n) -> new Feedback(rs.getLong("id"), rs.getLong("user_id"), rs.getString("conversation_id"),
                        rs.getString("message_id"), rs.getString("prompt"), rs.getString("original_answer"),
                        rs.getString("issue_type"), rs.getString("description"), rs.getString("expected"),
                        rs.getString("status"), rs.getString("review_conclusion"), rs.getString("revision"),
                        rs.getString("citations_json"), rs.getString("provider_key"),
                        rs.getTimestamp("created_at") == null ? "" : rs.getTimestamp("created_at").toInstant().toString(),
                        rs.getTimestamp("updated_at") == null ? "" : rs.getTimestamp("updated_at").toInstant().toString()), userId, Math.max(1, Math.min(100, limit)));
    }

    private static String safe(String value) { return value == null ? "" : value; }
    private static String abbreviate(String value, int max) {
        if (value == null) return "";
        return value.length() <= max ? value : value.substring(0, max) + "…";
    }

    public record FeedbackRequest(String conversationId, String messageId, String prompt,
                                  String originalAnswer, String issueType, String description, String expected) {}
    public record Feedback(Long id, Long userId, String conversationId, String messageId, String prompt,
                           String originalAnswer, String issueType, String description, String expected,
                           String status, String reviewConclusion, String revision, String citationsJson,
                           String providerKey, String createdAt, String updatedAt) {}
}
