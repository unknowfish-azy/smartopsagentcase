package com.smartops.integration;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartops.security.AccountSessionRegistry;
import com.smartops.security.SessionUser;
import com.smartops.security.UserAccountService;
import com.smartops.service.ModelConnectionService;
import com.smartops.support.TestPlatformProfiles;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.ResultActions;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import java.util.List;
import java.util.Map;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

/**
 * 六门户接入矩阵 + 审计/管理职责分离（SoD）集成测试。
 *
 * <p>每个平级门户只接受注册中心规约的对应角色登录；未知入口 fail-closed（400）；
 * 把仍持有有效平台管理员档案的账号改任审计员必须被拦截（409），防止审计与管理两权合一。</p>
 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@TestPropertySource(properties = "spring.datasource.url=jdbc:h2:mem:portal_access;MODE=MySQL;DB_CLOSE_DELAY=-1;DATABASE_TO_LOWER=TRUE")
class PortalAccessIntegrationTest {
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper json;
    @Autowired JdbcTemplate jdbc;
    @Autowired AccountSessionRegistry sessions;
    @Autowired UserAccountService accounts;
    @MockBean ModelConnectionService models;

    private static final String PASSWORD = "PortalAccessPassword42!";

    private record PortalCase(String username, String portal, String role) {}

    private static final List<PortalCase> CASES = List.of(
            new PortalCase("portal-operator", "user", "operator"),
            new PortalCase("portal-admin", "admin", "admin"),
            new PortalCase("portal-enterprise", "enterprise", "enterprise"),
            new PortalCase("portal-auditor", "audit", "auditor"),
            new PortalCase("portal-commander", "command", "commander"),
            new PortalCase("portal-partner", "open", "partner")
    );

    @BeforeEach
    void seed() {
        jdbc.queryForList("SELECT id FROM app_user", Long.class).forEach(sessions::revokeUser);
        jdbc.update("DELETE FROM app_user");
        for (String table : List.of("account_security", "security_audit_event", "platform_admin_profile", "platform_admin_capability")) {
            if (jdbc.queryForObject("SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE LOWER(TABLE_NAME)=?", Integer.class, table) > 0) {
                jdbc.update("DELETE FROM " + table);
            }
        }
        String hash = new BCryptPasswordEncoder().encode(PASSWORD);
        jdbc.update("INSERT INTO app_user(id,username,password_hash,role) VALUES "
                        + "(11,'portal-admin',?,'admin'),"
                        + "(22,'portal-operator',?,'operator'),"
                        + "(33,'portal-enterprise',?,'enterprise'),"
                        + "(44,'portal-auditor',?,'auditor'),"
                        + "(55,'portal-commander',?,'commander'),"
                        + "(66,'portal-partner',?,'partner')",
                hash, hash, hash, hash, hash, hash);
        // 管理端 actor 需显式建档才有治理能力（SEC-07 回填语义）。
        TestPlatformProfiles.grantRoot(jdbc, 11L);
    }

    private Client anonymous() throws Exception {
        var result = mvc.perform(get("/api/auth/session")).andExpect(status().isOk()).andReturn();
        return new Client((MockHttpSession) result.getRequest().getSession(false),
                json.readTree(result.getResponse().getContentAsString()).path("data").path("csrfToken").asText());
    }

    private Client login(String name, String password, String portal) throws Exception {
        Client client = anonymous();
        send(client, post("/api/auth/login"), Map.of("username", name, "password", password, "portal", portal))
                .andExpect(status().isOk());
        var result = mvc.perform(get("/api/auth/session").session(client.session())).andExpect(status().isOk()).andReturn();
        return new Client((MockHttpSession) result.getRequest().getSession(false),
                json.readTree(result.getResponse().getContentAsString()).path("data").path("csrfToken").asText());
    }

    private Client admin() throws Exception {
        return login("portal-admin", PASSWORD, "admin");
    }

    private ResultActions send(Client client, MockHttpServletRequestBuilder request, Object body) throws Exception {
        return mvc.perform(request.session(client.session()).header("X-CSRF-TOKEN", client.csrf())
                .header("X-Admin-Password", PASSWORD).contentType("application/json").content(json.writeValueAsString(body)));
    }

    @Test
    void eachPortalAcceptsOnlyItsRegisteredRoleAndEstablishesTheRightSession() throws Exception {
        for (PortalCase c : CASES) {
            Client client = login(c.username(), PASSWORD, c.portal());
            mvc.perform(get("/api/auth/session").session(client.session()))
                    .andExpect(jsonPath("$.data.user.role").value(c.role()));
        }
    }

    @Test
    void foreignPortalLoginsAreForbidden() throws Exception {
        // 普通账号不得进入任何受限门户
        for (String portal : List.of("admin", "enterprise", "audit", "command", "open")) {
            send(anonymous(), post("/api/auth/login"),
                    Map.of("username", "portal-operator", "password", PASSWORD, "portal", portal))
                    .andExpect(status().isForbidden());
        }
        // 管理员不得退回公开用户层
        send(anonymous(), post("/api/auth/login"),
                Map.of("username", "portal-admin", "password", PASSWORD, "portal", "user"))
                .andExpect(status().isForbidden());
        // 受限门户之间也互不放行
        send(anonymous(), post("/api/auth/login"),
                Map.of("username", "portal-commander", "password", PASSWORD, "portal", "enterprise"))
                .andExpect(status().isForbidden());
        send(anonymous(), post("/api/auth/login"),
                Map.of("username", "portal-auditor", "password", PASSWORD, "portal", "command"))
                .andExpect(status().isForbidden());
        send(anonymous(), post("/api/auth/login"),
                Map.of("username", "portal-enterprise", "password", PASSWORD, "portal", "open"))
                .andExpect(status().isForbidden());
    }

    @Test
    void unknownPortalIsRejectedWithBadRequest() throws Exception {
        send(anonymous(), post("/api/auth/login"),
                Map.of("username", "portal-operator", "password", PASSWORD, "portal", "ghost"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void auditorRoleIsMutuallyExclusiveWithActiveAdminProfile() throws Exception {
        Client manager = admin();
        // 新建管理员会显式建档（ensureAdminProfile），因此持有有效平台管理员档案。
        var created = send(manager, post("/api/admin/users"),
                        Map.of("username", "sod-target", "password", PASSWORD, "role", "admin"))
                .andExpect(status().isOk()).andReturn();
        long targetId = json.readTree(created.getResponse().getContentAsString()).path("data").path("id").asLong();

        // 仍持有有效档案时改任审计员 → 409（SoD，先于「最后一个管理员」校验触发）
        send(manager, put("/api/admin/users/" + targetId), Map.of("role", "auditor", "enabled", true))
                .andExpect(status().isConflict());

        // 撤销档案后允许改任审计员
        var actor = new SessionUser(11L, "portal-admin", "admin", "admin", false, 0);
        accounts.revokePlatformAdmin(actor, targetId);
        send(manager, put("/api/admin/users/" + targetId), Map.of("role", "auditor", "enabled", true))
                .andExpect(status().isOk());

        // 对照：从未持有管理员档案的账号可直接改任审计员
        send(manager, put("/api/admin/users/22"), Map.of("role", "auditor", "enabled", true))
                .andExpect(status().isOk());
    }

    private record Client(MockHttpSession session, String csrf) {}
}
