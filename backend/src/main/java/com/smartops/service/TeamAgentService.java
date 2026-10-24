package com.smartops.service;

import com.smartops.exception.BusinessException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartops.security.SessionUser;
import com.smartops.security.TeamResourceAuthorizer;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;
import java.util.HashSet;
import java.util.Set;

@Service
public class TeamAgentService {
    private final JdbcTemplate jdbc;
    private final TeamResourceAuthorizer authorizer;
    private final ObjectMapper mapper;
    private final OperationToolService tools;

    public TeamAgentService(JdbcTemplate jdbc, TeamResourceAuthorizer authorizer, ObjectMapper mapper, OperationToolService tools) {
        this.jdbc = jdbc;
        this.authorizer = authorizer;
        this.mapper = mapper;
        this.tools = tools;
    }

    public List<Agent> list(SessionUser actor, long teamId) {
        authorizer.requireTeamMember(actor, teamId);
        var agents = jdbc.query("SELECT a.id,a.team_id,a.name,a.description,a.status,a.current_version,a.created_by,v.version_no AS current_version_no FROM team_agent a LEFT JOIN team_agent_version v ON v.id=a.current_version WHERE a.team_id=? ORDER BY a.id DESC",
                (result, row) -> new Agent(result.getLong("id"), result.getLong("team_id"), result.getString("name"),
                        result.getString("description"), result.getString("status"),
                        result.getObject("current_version", Long.class), result.getObject("current_version_no", Integer.class), result.getLong("created_by")), teamId);
        return agents.stream().filter(agent -> canView(actor, teamId, agent.id())).toList();
    }

    public AgentDetail detail(SessionUser actor, long teamId, long agentId) {
        Agent agent = find(actor, teamId, agentId);
        boolean manager = Set.of("owner", "admin", "root").contains(authorizer.requireResource(actor, teamId, "agent", String.valueOf(agent.id()), "view").role());
        Version draft = manager ? version(agentId, "DRAFT") : null;
        Version published = agent.currentVersion() == null ? null : jdbc.query(
                "SELECT id,agent_id,version_no,prompt,tools_json,status FROM team_agent_version WHERE id=? AND agent_id=?",
                (row, index) -> mapVersion(row), agent.currentVersion(), agentId).stream().findFirst().orElse(null);
        Version visibleVersion = published == null || manager ? published :
                new Version(published.id(), published.agentId(), published.versionNo(), "", "[]", published.status());
        return new AgentDetail(agent, draft, visibleVersion);
    }

    public List<OperationToolService.ToolDescriptor> availableTools(SessionUser actor, long teamId, long agentId) {
        Agent agent = find(actor, teamId, agentId);
        authorizer.requireResource(actor, teamId, "agent", String.valueOf(agentId), "run");
        if (agent.currentVersion() == null || !"PUBLISHED".equals(agent.status())) {
            throw new BusinessException(409, "TEAM_AGENT_NOT_PUBLISHED");
        }
        Version published = version(agentId, "PUBLISHED");
        if (published == null || published.id() != agent.currentVersion()) {
            throw new BusinessException(409, "TEAM_AGENT_NOT_PUBLISHED");
        }
        Set<String> allowed = new HashSet<>();
        try {
            for (var item : mapper.readTree(published.toolsJson())) allowed.add(item.asText());
        } catch (Exception invalid) {
            throw new BusinessException(409, "TEAM_AGENT_TOOLS_INVALID");
        }
        return tools.listTools().stream().filter(tool -> allowed.contains(tool.toolId()) && !"alerts-suppress".equals(tool.toolId())).toList();
    }

    public List<OperationToolService.ToolDescriptor> catalog(SessionUser actor, long teamId) {
        authorizer.requireMember(actor, teamId, "manage");
        return tools.listTools().stream().filter(tool -> !"alerts-suppress".equals(tool.toolId())).toList();
    }

    @Transactional
    public Agent create(SessionUser actor, long teamId, String name, String description) {
        authorizer.requireMember(actor, teamId, "manage");
        if (name == null || name.isBlank() || name.trim().length() > 120) throw new BusinessException(400, "TEAM_AGENT_NAME_INVALID");
        var key = new GeneratedKeyHolder();
        jdbc.update(connection -> {
            var statement = connection.prepareStatement("INSERT INTO team_agent(team_id,name,description,status,created_by) VALUES(?,?,?,?,?)", new String[]{"id"});
            statement.setLong(1, teamId); statement.setString(2, name.trim()); statement.setString(3, description == null ? "" : description.trim());
            statement.setString(4, "DRAFT"); statement.setLong(5, actor.id());
            return statement;
        }, key);
        return find(actor, teamId, key.getKey().longValue());
    }

    @Transactional
    public void saveDraft(SessionUser actor, long agentId, String prompt, String toolsJson) {
        saveDraft(actor, agentId, prompt, toolsJson, null);
    }

    /**
     * 保存草稿，带**乐观锁**（协作优化 2）。
     *
     * <p>原实现是"后写覆盖先写"：两人同时编辑同一个 Agent 草稿时，
     * 后保存的人会把前一个人的修改静默抹掉，前一个人还以为保存成功了。</p>
     *
     * @param expectedRevision 客户端读取草稿时拿到的 revision。
     *                         {@code null} 表示不校验（兼容既有调用与首次创建）。
     *                         不匹配时抛 409 并给出当前 revision，让界面提示"有人先改了，请刷新"。
     */
    @Transactional
    public void saveDraft(SessionUser actor, long agentId, String prompt, String toolsJson, Integer expectedRevision) {
        Agent agent = findRaw(agentId);
        authorizer.requireResource(actor, agent.teamId(), "agent", String.valueOf(agentId), "edit");
        validateTools(toolsJson);
        Long versionId = jdbc.query("SELECT id FROM team_agent_version WHERE agent_id=? AND status='DRAFT' ORDER BY id DESC LIMIT 1",
                result -> result.next() ? result.getLong("id") : null, agentId);
        if (versionId == null) {
            // 首次创建草稿：如果客户端声称在编辑一个不存在的草稿，说明它读到的是过期状态
            if (expectedRevision != null && expectedRevision > 0) {
                throw new BusinessException(409, "草稿已被删除或尚未创建，请刷新后重试");
            }
            jdbc.update("""
                    INSERT INTO team_agent_version(agent_id,version_no,prompt,tools_json,status,created_by,created_at,revision,updated_at)
                    VALUES(?,?,?,?,?,?,?,0,?)
                    """, agentId, 0, prompt == null ? "" : prompt, toolsJson == null ? "[]" : toolsJson,
                    "DRAFT", actor.id(), Timestamp.from(Instant.now()), Timestamp.from(Instant.now()));
            return;
        }
        if (expectedRevision != null) {
            Integer current = currentRevision(versionId);
            if (current == null || !current.equals(expectedRevision)) {
                throw new BusinessException(409,
                        "草稿已被其他人修改（当前版本 " + (current == null ? "未知" : current) + "），请刷新后再保存，"
                                + "以免覆盖他人的修改");
            }
        }
        // 用 revision 作为条件更新，避免"检查通过后、更新之前被人插队"的竞态。
        int changed = jdbc.update("""
                UPDATE team_agent_version SET prompt=?,tools_json=?,revision=revision+1,updated_at=?
                 WHERE id=? AND (? IS NULL OR revision=?)
                """, prompt == null ? "" : prompt, toolsJson == null ? "[]" : toolsJson,
                Timestamp.from(Instant.now()), versionId, expectedRevision, expectedRevision);
        if (changed != 1) {
            throw new BusinessException(409, "草稿已被其他人修改，请刷新后再保存");
        }
    }

    /** 读取草稿当前 revision；列不存在时返回 null（旧库兼容）。 */
    private Integer currentRevision(long versionId) {
        try {
            return jdbc.queryForObject("SELECT revision FROM team_agent_version WHERE id=?", Integer.class, versionId);
        } catch (org.springframework.dao.DataAccessException missingColumn) {
            return null;
        }
    }

    private void validateTools(String toolsJson) {
        try {
            var value = mapper.readTree(toolsJson);
            if (!value.isArray() || value.size() > 30) throw new IllegalArgumentException();
            Set<String> known = new HashSet<>();
            tools.listTools().stream().filter(tool -> !"alerts-suppress".equals(tool.toolId())).forEach(tool -> known.add(tool.toolId()));
            Set<String> selected = new HashSet<>();
            for (var item : value) {
                if (!item.isTextual() || !known.contains(item.asText()) || !selected.add(item.asText())) {
                    throw new IllegalArgumentException();
                }
            }
        } catch (Exception invalid) {
            throw new BusinessException(400, "TEAM_AGENT_TOOLS_INVALID");
        }
    }

    private Version version(long agentId, String status) {
        return jdbc.query("SELECT id,agent_id,version_no,prompt,tools_json,status,revision FROM team_agent_version WHERE agent_id=? AND status=? ORDER BY id DESC LIMIT 1",
                (row, index) -> mapVersion(row), agentId, status).stream().findFirst().orElse(null);
    }

    private Version mapVersion(java.sql.ResultSet row) throws java.sql.SQLException {
        Integer revision;
        try {
            revision = row.getObject("revision", Integer.class);
        } catch (java.sql.SQLException missingColumn) {
            // 旧库没有 revision 列：返回 null，保存时不去校验，行为与改造前一致。
            revision = null;
        }
        return new Version(row.getLong("id"), row.getLong("agent_id"), row.getInt("version_no"),
                row.getString("prompt"), row.getString("tools_json"), row.getString("status"), revision);
    }

    @Transactional
    public void saveDraft(SessionUser actor, long teamId, long agentId, String prompt, String toolsJson) {
        saveDraft(actor, teamId, agentId, prompt, toolsJson, null);
    }

    @Transactional
    public void saveDraft(SessionUser actor, long teamId, long agentId, String prompt, String toolsJson,
                          Integer expectedRevision) {
        Agent agent = findRaw(agentId);
        if (agent.teamId() != teamId) throw new BusinessException(404, "TEAM_AGENT_NOT_FOUND");
        saveDraft(actor, agentId, prompt, toolsJson, expectedRevision);
    }

    @Transactional
    public Version publish(SessionUser actor, long agentId) {
        Agent agent = findRaw(agentId);
        authorizer.requireResource(actor, agent.teamId(), "agent", String.valueOf(agentId), "publish");
        var drafts = jdbc.query("SELECT id,prompt,tools_json FROM team_agent_version WHERE agent_id=? AND status='DRAFT' ORDER BY id DESC LIMIT 1",
                (result, row) -> new Draft(result.getLong("id"), result.getString("prompt"), result.getString("tools_json")), agentId);
        if (drafts.isEmpty()) throw new BusinessException(409, "TEAM_AGENT_DRAFT_REQUIRED");
        int next = jdbc.queryForObject("SELECT COALESCE(MAX(version_no),0)+1 FROM team_agent_version WHERE agent_id=?", Integer.class, agentId);
        Draft draft = drafts.get(0);
        jdbc.update("UPDATE team_agent_version SET status='ARCHIVED' WHERE agent_id=? AND status='PUBLISHED'", agentId);
        jdbc.update("UPDATE team_agent_version SET status='PUBLISHED',version_no=? WHERE id=?", next, draft.id());
        jdbc.update("UPDATE team_agent SET status='PUBLISHED',current_version=? WHERE id=?", draft.id(), agentId);
        return new Version(draft.id(), agentId, next, draft.prompt(), draft.toolsJson(), "PUBLISHED");
    }

    @Transactional
    public Version publish(SessionUser actor, long teamId, long agentId) {
        Agent agent = findRaw(agentId);
        if (agent.teamId() != teamId) throw new BusinessException(404, "TEAM_AGENT_NOT_FOUND");
        return publish(actor, agentId);
    }

    private Agent find(SessionUser actor, long teamId, long id) {
        Agent agent = findRaw(id);
        if (agent.teamId() != teamId) throw new BusinessException(404, "TEAM_AGENT_NOT_FOUND");
        authorizer.requireResource(actor, teamId, "agent", String.valueOf(id), "view");
        return agent;
    }

    private boolean canView(SessionUser actor, long teamId, long agentId) {
        try {
            authorizer.requireResource(actor, teamId, "agent", String.valueOf(agentId), "view");
            return true;
        } catch (BusinessException denied) {
            return false;
        }
    }

    private Agent findRaw(long id) {
        var agents = jdbc.query("SELECT a.id,a.team_id,a.name,a.description,a.status,a.current_version,a.created_by,v.version_no AS current_version_no FROM team_agent a LEFT JOIN team_agent_version v ON v.id=a.current_version WHERE a.id=?",
                (result, row) -> new Agent(result.getLong("id"), result.getLong("team_id"), result.getString("name"),
                        result.getString("description"), result.getString("status"), result.getObject("current_version", Long.class), result.getObject("current_version_no", Integer.class), result.getLong("created_by")), id);
        if (agents.isEmpty()) throw new BusinessException(404, "TEAM_AGENT_NOT_FOUND");
        return agents.get(0);
    }

    private record Draft(long id, String prompt, String toolsJson) {}
    public record Agent(long id, long teamId, String name, String description, String status, Long currentVersion, Integer currentVersionNo, long createdBy) {}
    /**
     * 草稿/已发布版本。
     *
     * <p>{@code revision} 是草稿的乐观锁版本号，前端保存时原样带回；
     * 未变化的旧库（没有该列）读到 null，此时不做校验，行为与改造前一致。</p>
     */
    public record Version(long id, long agentId, int versionNo, String prompt, String toolsJson, String status,
                          Integer revision) {
        public Version(long id, long agentId, int versionNo, String prompt, String toolsJson, String status) {
            this(id, agentId, versionNo, prompt, toolsJson, status, null);
        }
    }
    public record AgentDetail(Agent agent, Version draft, Version currentVersion) {}
}
