package com.smartops.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartops.exception.BusinessException;
import lombok.RequiredArgsConstructor;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;

/**
 * AI 运维决策闭环：分析 → 记忆 → 决策 → 复盘 → 学习回写。
 *
 * <p>闭环主线落在 agent_decision_loop；记忆复用 operator_memory，
 * 复盘结论会真实回写记忆置信度，而不是只做展示。</p>
 */
@Service
@RequiredArgsConstructor
public class DecisionLoopService {

    public static final String ANALYZE = "ANALYZE";
    public static final String MEMORIZE = "MEMORIZE";
    public static final String DECIDE = "DECIDE";
    public static final String REVIEW = "REVIEW";
    public static final String LEARNED = "LEARNED";

    private static final List<String> STAGES = List.of(ANALYZE, MEMORIZE, DECIDE, REVIEW, LEARNED);

    private final JdbcTemplate jdbc;
    private final ObjectMapper objectMapper;
    private final OperatorMemoryService memories;
    private final IncidentRecommendationService recommendations;

    public List<Map<String, Object>> list(Long userId, int limit) {
        syncFromInspector(userId);
        int safeLimit = Math.max(1, Math.min(limit, 100));
        return jdbc.queryForList(
                        "SELECT id, incident_key, title, source_type, source_ref, stage, severity, symptom, analysis, "
                                + "recommendation, decision, decision_basis, requires_human, outcome, lesson, "
                                + "learned_count, confidence, reviewed_at, created_at, updated_at "
                                + "FROM agent_decision_loop WHERE user_id = ? ORDER BY updated_at DESC, created_at DESC LIMIT ?",
                        userId, safeLimit)
                .stream().map(this::camelize).toList();
    }

    public Map<String, Object> detail(Long userId, String id) {
        List<Map<String, Object>> rows = jdbc.queryForList(
                "SELECT id, incident_key, title, source_type, source_ref, stage, severity, symptom, analysis, "
                        + "evidence_json, memory_refs, recommendation, decision, decision_basis, requires_human, "
                        + "outcome, lesson, learned_memory_ids, learned_count, confidence, reviewed_at, created_at, updated_at "
                        + "FROM agent_decision_loop WHERE id = ? AND user_id = ?",
                id, userId);
        if (rows.isEmpty()) throw new BusinessException(404, "决策闭环不存在");

        Map<String, Object> loop = camelize(rows.get(0));
        loop.put("evidence", readList(loop.remove("evidenceJson")));
        List<Long> memoryIds = readIds(loop.remove("memoryRefs"));
        List<Long> learnedIds = readIds(loop.remove("learnedMemoryIds"));
        loop.put("memories", memories.byIds(userId, memoryIds));
        loop.put("learnedMemories", memories.byIds(userId, learnedIds));
        return loop;
    }

    @Transactional
    public Map<String, Object> create(Long userId, CreateRequest request) {
        if (isBlank(request.incidentKey()) || isBlank(request.title())) {
            throw new BusinessException("事件标识与标题不能为空");
        }
        String id = "LOOP-" + UUID.randomUUID().toString().replace("-", "").substring(0, 12).toUpperCase(Locale.ROOT);
        LocalDateTime now = LocalDateTime.now();
        jdbc.update("INSERT INTO agent_decision_loop "
                        + "(id,user_id,incident_key,title,source_type,stage,severity,symptom,analysis,evidence_json,"
                        + "confidence,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                id, userId, request.incidentKey().trim(), request.title().trim(), "MANUAL", ANALYZE,
                normalizeSeverity(request.severity()), request.symptom(), request.analysis(),
                json(request.evidence() == null ? List.of() : request.evidence()),
                0.5d, now, now);
        return detail(userId, id);
    }

    @Transactional
    public Map<String, Object> recall(Long userId, String id) {
        Map<String, Object> loop = row(userId, id);
        String incidentKey = str(loop.get("incidentKey"));
        String symptom = str(loop.get("symptom"));
        String title = str(loop.get("title"));

        List<OperatorMemoryService.Memory> matched = memories.match(userId, incidentKey);
        List<Long> ids = matched.stream().map(OperatorMemoryService.Memory::id).toList();

        String recommendation = str(loop.get("recommendation"));
        if (isBlank(recommendation) && !matched.isEmpty()) {
            OperatorMemoryService.Memory best = matched.get(0);
            recommendation = best.preferredAction() + "（历史同类处置，置信度 "
                    + Math.round(best.confidence() * 100) + "%）";
        } else if (isBlank(recommendation)) {
            List<String> evidence = readList(loop.get("evidenceJson")).stream()
                    .map(item -> str(item.get("content"))).filter(item -> !isBlank(item)).toList();
            IncidentRecommendationService.IncidentPattern pattern =
                    new IncidentRecommendationService.IncidentPattern(title, symptom, str(loop.get("severity")), evidence);
            List<IncidentRecommendationService.Recommendation> candidates =
                    recommendations.recommend(pattern, memories.list(userId));
            if (!candidates.isEmpty()) {
                recommendation = candidates.get(0).action() + "（跨事件经验匹配，置信度 "
                        + Math.round(candidates.get(0).confidence() * 100) + "%）";
            }
        }

        jdbc.update("UPDATE agent_decision_loop SET memory_refs=?, recommendation=?, stage=?, updated_at=? "
                        + "WHERE id=? AND user_id=?",
                json(ids), recommendation, laterStage(str(loop.get("stage")), MEMORIZE), LocalDateTime.now(), id, userId);
        return detail(userId, id);
    }

    @Transactional
    public Map<String, Object> decide(Long userId, String id, DecideRequest request) {
        Map<String, Object> loop = row(userId, id);
        if (isBlank(request.recommendation()) && isBlank(request.decision())) {
            throw new BusinessException("处置建议与决策结论至少填写一项");
        }
        String recommendation = isBlank(request.recommendation()) ? str(loop.get("recommendation")) : request.recommendation().trim();
        String decision = isBlank(request.decision()) ? recommendation : request.decision().trim();
        jdbc.update("UPDATE agent_decision_loop SET recommendation=?, decision=?, decision_basis=?, requires_human=?, "
                        + "stage=?, updated_at=? WHERE id=? AND user_id=?",
                recommendation, decision, request.decisionBasis(),
                Boolean.TRUE.equals(request.requiresHuman()),
                laterStage(str(loop.get("stage")), DECIDE), LocalDateTime.now(), id, userId);
        return detail(userId, id);
    }

    @Transactional
    public Map<String, Object> review(Long userId, String id, ReviewRequest request) {
        Map<String, Object> loop = row(userId, id);
        boolean resolved = "RESOLVED".equalsIgnoreCase(str(request.outcome()));
        if (!resolved && !"UNRESOLVED".equalsIgnoreCase(str(request.outcome()))) {
            throw new BusinessException("复盘结论必须为 RESOLVED 或 UNRESOLVED");
        }
        String outcome = resolved ? "RESOLVED" : "UNRESOLVED";
        // SEC-10：用条件 UPDATE 原子认领本次学习——同一闭环、同一结论的第二/并发 review 认领失败直接返回，
        // 不再重复回写记忆置信度、不重复沉淀记忆；结论翻转（RESOLVED ↔ UNRESOLVED）视为新信息仍可学习。
        int claimed = jdbc.update("UPDATE agent_decision_loop SET outcome=?, lesson=?, reviewed_at=?, stage=?, updated_at=? "
                        + "WHERE id=? AND user_id=? AND NOT (stage=? AND outcome=?)",
                outcome, request.lesson(), LocalDateTime.now(), laterStage(str(loop.get("stage")), LEARNED),
                LocalDateTime.now(), id, userId, LEARNED, outcome);
        if (claimed > 0) {
            learn(userId, row(userId, id));
        }
        return detail(userId, id);
    }

    public Map<String, Object> stats(Long userId) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("total", count(userId, "SELECT COUNT(*) FROM agent_decision_loop WHERE user_id=?"));
        result.put("reviewed", count(userId, "SELECT COUNT(*) FROM agent_decision_loop WHERE user_id=? AND outcome IS NOT NULL"));
        result.put("resolved", count(userId, "SELECT COUNT(*) FROM agent_decision_loop WHERE user_id=? AND outcome='RESOLVED'"));
        result.put("learnedCount", count(userId, "SELECT COALESCE(SUM(learned_count),0) FROM agent_decision_loop WHERE user_id=?"));
        result.put("byStage", jdbc.queryForList(
                "SELECT stage, COUNT(*) AS count FROM agent_decision_loop WHERE user_id=? GROUP BY stage",
                userId).stream().map(this::camelize).toList());
        long reviewed = ((Number) result.get("reviewed")).longValue();
        long resolved = ((Number) result.get("resolved")).longValue();
        result.put("resolveRate", reviewed == 0 ? 0d : (double) resolved / reviewed);
        return result;
    }

    /** 自动通道：把尚未进入闭环的 Inspector 事件派生为闭环卡片（每个事件只同步一次）。 */
    private void syncFromInspector(Long userId) {
        List<Map<String, Object>> rows = jdbc.queryForList(
                "SELECT e.id, e.task_id, e.status, e.severity, e.category, e.agent_claim, e.reason, e.recommendation, "
                        + "e.requires_human, "
                        + "(SELECT v.resolved FROM inspection_verification v WHERE v.event_id = e.id "
                        + " ORDER BY v.id DESC LIMIT 1) AS resolved "
                        + "FROM inspector_event e "
                        // SEC-08：只消费与当前用户关联的事件；无归属（服务间巡检）的事件不投影进任何人的闭环。
                        + "WHERE e.user_id = ? "
                        + "AND NOT EXISTS (SELECT 1 FROM agent_decision_loop d "
                        // SEC-10：去重按 (user_id, source_type, source_ref) 与唯一键一致。
                        + " WHERE d.user_id = ? AND d.source_type='INSPECTOR' AND d.source_ref=e.id) "
                        + "ORDER BY e.created_at DESC LIMIT 20", userId, userId);
        for (Map<String, Object> raw : rows) {
            Map<String, Object> event = camelize(raw);
            String category = str(event.get("category"));
            String taskId = str(event.get("taskId"));
            String incidentKey = isBlank(category) ? taskId : category;
            String title = (isBlank(category) ? "Inspector 事件" : category) + " · " + taskId;
            List<Map<String, Object>> evidence = jdbc.queryForList(
                    "SELECT content, source, score FROM inspection_evidence WHERE event_id = ? ORDER BY id",
                    event.get("id"));
            Boolean resolved = asResolved(event.get("resolved"));
            String stage = resolved != null ? REVIEW : (isBlank(str(event.get("recommendation"))) ? ANALYZE : DECIDE);
            String id = "LOOP-" + UUID.randomUUID().toString().replace("-", "").substring(0, 12).toUpperCase(Locale.ROOT);
            LocalDateTime now = LocalDateTime.now();
            try {
                jdbc.update("INSERT INTO agent_decision_loop "
                                + "(id,user_id,incident_key,title,source_type,source_ref,stage,severity,symptom,analysis,"
                                + "evidence_json,recommendation,decision,decision_basis,requires_human,created_at,updated_at) "
                                + "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        id, userId, incidentKey, title, "INSPECTOR", event.get("id"), stage,
                        normalizeSeverity(str(event.get("severity"))), event.get("agentClaim"), event.get("reason"),
                        json(evidence), event.get("recommendation"),
                        isBlank(str(event.get("recommendation"))) ? null : event.get("recommendation"),
                        "Inspector 纠察结论：" + str(event.get("status")),
                        Boolean.TRUE.equals(event.get("requiresHuman")), now, now);
            } catch (DuplicateKeyException concurrent) {
                // SEC-10：并发 GET 同时同步同一事件时，唯一键 (user_id, source_type, source_ref) 兜底；
                // 未抢到插入的请求直接跳过，既不再学也不会把 500 暴露给调用方。
                continue;
            }
            if (resolved != null) {
                learn(userId, Map.of(
                        "id", id,
                        "incidentKey", incidentKey,
                        "outcome", resolved ? "RESOLVED" : "UNRESOLVED",
                        "decision", isBlank(str(event.get("recommendation"))) ? "" : str(event.get("recommendation")),
                        "recommendation", str(event.get("recommendation"))));
            }
        }
    }

    /** 学习：复盘结果真实回写 operator_memory，并记录回写明细。 */
    private void learn(Long userId, Map<String, Object> loop) {
        String id = str(loop.get("id"));
        String incidentKey = str(loop.get("incidentKey"));
        boolean resolved = "RESOLVED".equalsIgnoreCase(str(loop.get("outcome")));

        List<Long> refIds = readIds(loop.get("memoryRefs"));
        List<OperatorMemoryService.Memory> targets = refIds.isEmpty()
                ? memories.match(userId, incidentKey)
                : memories.byIds(userId, refIds);

        List<Long> learnedIds = new ArrayList<>();
        double confidenceSum = 0d;
        for (OperatorMemoryService.Memory memory : targets) {
            OperatorMemoryService.Memory updated = memories.feedback(userId, memory.id(), resolved);
            learnedIds.add(updated.id());
            confidenceSum += updated.confidence();
        }

        if (resolved && targets.isEmpty()) {
            String action = isBlank(str(loop.get("decision"))) ? str(loop.get("recommendation")) : str(loop.get("decision"));
            OperatorMemoryService.Memory created = memories.recordLearned(userId, incidentKey, action, "DECISION_LOOP:" + id);
            if (created != null) {
                learnedIds.add(created.id());
                confidenceSum += created.confidence();
            }
        }

        double confidence = learnedIds.isEmpty()
                ? (resolved ? 0.6d : 0.35d)
                : confidenceSum / learnedIds.size();
        jdbc.update("UPDATE agent_decision_loop SET stage=?, learned_memory_ids=?, learned_count=?, confidence=?, updated_at=? "
                        + "WHERE id=? AND user_id=?",
                LEARNED, json(learnedIds), learnedIds.size(), confidence, LocalDateTime.now(), id, userId);
    }

    private Map<String, Object> row(Long userId, String id) {
        List<Map<String, Object>> rows = jdbc.queryForList(
                "SELECT id, incident_key, title, stage, severity, symptom, analysis, evidence_json, memory_refs, "
                        + "recommendation, decision, decision_basis, outcome, learned_memory_ids "
                        + "FROM agent_decision_loop WHERE id=? AND user_id=?",
                id, userId);
        if (rows.isEmpty()) throw new BusinessException(404, "决策闭环不存在");
        return camelize(rows.get(0));
    }

    /** 把数据库列名（下划线/大小写不定）统一转成前端使用的驼峰键。 */
    private Map<String, Object> camelize(Map<String, Object> row) {
        Map<String, Object> result = new LinkedHashMap<>();
        row.forEach((key, value) -> result.put(toCamel(key), value));
        return result;
    }

    private String toCamel(String key) {
        String lower = key.toLowerCase(Locale.ROOT);
        StringBuilder builder = new StringBuilder();
        boolean upperNext = false;
        for (char character : lower.toCharArray()) {
            if (character == '_') {
                upperNext = true;
                continue;
            }
            builder.append(upperNext ? Character.toUpperCase(character) : character);
            upperNext = false;
        }
        return builder.toString();
    }

    private long count(Long userId, String sql) {
        Long value = jdbc.queryForObject(sql, Long.class, userId);
        return value == null ? 0 : value;
    }

    private String laterStage(String current, String next) {
        return STAGES.indexOf(next) > STAGES.indexOf(current == null ? ANALYZE : current) ? next : current;
    }

    private String normalizeSeverity(String severity) {
        if (isBlank(severity)) return "MEDIUM";
        String value = severity.trim().toUpperCase(Locale.ROOT);
        return List.of("LOW", "MEDIUM", "HIGH", "CRITICAL").contains(value) ? value : "MEDIUM";
    }

    private Boolean asResolved(Object value) {
        if (value == null) return null;
        if (value instanceof Boolean bool) return bool;
        if (value instanceof Number number) return number.intValue() != 0;
        return Boolean.parseBoolean(value.toString());
    }

    private List<Map<String, Object>> readList(Object value) {
        if (!(value instanceof String text) || text.isBlank()) return List.of();
        try {
            return objectMapper.readValue(text, new TypeReference<List<Map<String, Object>>>() {});
        } catch (JsonProcessingException ex) {
            return List.of();
        }
    }

    private List<Long> readIds(Object value) {
        if (!(value instanceof String text) || text.isBlank()) return List.of();
        try {
            return objectMapper.readValue(text, new TypeReference<List<Long>>() {});
        } catch (JsonProcessingException ex) {
            return List.of();
        }
    }

    private String json(Object value) {
        try {
            return objectMapper.writeValueAsString(value == null ? List.of() : value);
        } catch (JsonProcessingException ex) {
            throw new BusinessException("决策闭环数据无法序列化");
        }
    }

    private static String str(Object value) {
        return value == null ? "" : String.valueOf(value);
    }

    private static boolean isBlank(String value) {
        return value == null || value.isBlank();
    }

    public record CreateRequest(String incidentKey, String title, String severity, String symptom,
                                String analysis, List<String> evidence) {}

    public record DecideRequest(String recommendation, String decision, String decisionBasis, Boolean requiresHuman) {}

    public record ReviewRequest(String outcome, String lesson) {}
}
