package com.smartops.integration;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.ResultActions;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicLong;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(properties = "spring.datasource.url=jdbc:h2:mem:chat_attachments;MODE=MySQL;DB_CLOSE_DELAY=-1;DATABASE_TO_LOWER=TRUE")
@AutoConfigureMockMvc
@ActiveProfiles("test")
@org.springframework.test.context.jdbc.Sql("classpath:db/migration/V007__chat_attachments.sql")
class ChatAttachmentIntegrationTest {
    @Autowired MockMvc mvc;
    @Autowired JdbcTemplate jdbc;
    @Autowired ObjectMapper json;
    @Autowired com.smartops.service.ChatAttachmentService attachmentService;
    @Autowired com.smartops.security.SecurityAuditService audit;
    @Autowired com.smartops.service.ChatAttachmentRetention retention;
    @MockBean com.smartops.service.ModelConnectionService models;
    private static final AtomicLong IDS = new AtomicLong(60000);
    private static final String PASSWORD = "AttachmentTestPassword42!";
    private static final String HASH = new BCryptPasswordEncoder().encode(PASSWORD);
    private Client owner;

    @BeforeEach void seed() throws Exception { owner = client(); }

    @Test void persistsFileOnlyMessageWithPrivateDownloadAndNoModelCall() throws Exception {
        String conversation = create(owner, null);
        upload(owner, conversation, "fault.log", "text/plain", "permission denied".getBytes(), UUID.randomUUID().toString()).andExpect(status().isOk());
        JsonNode file = lastUpload;
        String attachment = file.path("id").asText();
        send(owner, post(base(conversation) + "/messages"), Map.of("requestId", UUID.randomUUID().toString(), "text", "", "attachmentIds", List.of(attachment)))
                .andExpect(status().isOk()).andExpect(jsonPath("$.data.messages[0].attachments[0].name").value("fault.log"))
                .andExpect(jsonPath("$.data.messages[1].providerKey").value("attachment-receipt"));
        mvc.perform(get(base(conversation)).session(owner.session())).andExpect(status().isOk()).andExpect(jsonPath("$.data.messages.length()").value(2));
        mvc.perform(get(base(conversation) + "/attachments/" + attachment + "/content").session(owner.session()))
                .andExpect(status().isOk()).andExpect(header().string("Cache-Control", "no-store"))
                .andExpect(header().string("X-Content-Type-Options", "nosniff")).andExpect(content().bytes("permission denied".getBytes()));
        verifyNoInteractions(models);
    }

    @Test void outsiderCannotListReadBindDownloadOrDeletePrivateData() throws Exception {
        String conversation = create(owner, null);
        String attachment = uploadId(owner, conversation);
        Client other = client();
        mvc.perform(get("/api/assistant/conversations").session(other.session())).andExpect(jsonPath("$.data.length()").value(0));
        mvc.perform(get(base(conversation)).session(other.session())).andExpect(status().isNotFound());
        mvc.perform(get(base(conversation) + "/attachments/" + attachment + "/content").session(other.session())).andExpect(status().isNotFound());
        send(other, delete(base(conversation)), Map.of()).andExpect(status().isNotFound());
        String otherConversation = create(other, null);
        send(other, post(base(otherConversation) + "/messages"), Map.of("requestId", UUID.randomUUID().toString(), "text", "", "attachmentIds", List.of(attachment))).andExpect(status().isNotFound());
    }

    @Test void retriesDoNotDuplicateMessagesAndChangedPayloadConflicts() throws Exception {
        String conversation = create(owner, null);
        String requestId = UUID.randomUUID().toString();
        String attachment = uploadId(owner, conversation);
        var input = Map.of("requestId", requestId, "text", "证据", "attachmentIds", List.of(attachment));
        send(owner, post(base(conversation) + "/messages"), input).andExpect(status().isOk());
        send(owner, post(base(conversation) + "/messages"), input).andExpect(status().isOk()).andExpect(jsonPath("$.data.messages.length()").value(2));
        send(owner, post(base(conversation) + "/messages"), Map.of("requestId", requestId, "text", "changed", "attachmentIds", List.of(attachment))).andExpect(status().isConflict());
        send(owner, post(base(conversation) + "/messages"), Map.of("requestId", UUID.randomUUID().toString(), "text", "", "attachmentIds", List.of(attachment))).andExpect(status().isConflict());
    }

    @Test void uploadRetryUsesSameIdButDifferentBytesConflict() throws Exception {
        String conversation = create(owner, null);
        String uploadId = UUID.randomUUID().toString();
        upload(owner, conversation, "a.txt", "text/plain", "first".getBytes(), uploadId).andExpect(status().isOk());
        String first = lastUpload.path("id").asText();
        upload(owner, conversation, "a.txt", "text/plain", "first".getBytes(), uploadId).andExpect(status().isOk());
        assertEquals(first, lastUpload.path("id").asText());
        upload(owner, conversation, "a.txt", "text/plain", "second".getBytes(), uploadId).andExpect(status().isConflict());
    }

    @Test void rejectsSpoofedImagesActiveFormatsAndBinaryText() throws Exception {
        String conversation = create(owner, null);
        upload(owner, conversation, "fake.png", "image/png", "not an image".getBytes(), UUID.randomUUID().toString()).andExpect(status().isBadRequest());
        upload(owner, conversation, "bad.svg", "image/svg+xml", "<svg/>".getBytes(), UUID.randomUUID().toString()).andExpect(status().isBadRequest());
        upload(owner, conversation, "binary.txt", "text/plain", new byte[]{0, 1, 2}, UUID.randomUUID().toString()).andExpect(status().isBadRequest());
        upload(owner, conversation, "wrong.txt", "image/png", "text".getBytes(), UUID.randomUUID().toString()).andExpect(status().isBadRequest());
    }

    @Test void imageIsDecodedAndReencodedWithoutTrailingPayload() throws Exception {
        String conversation = create(owner, null);
        var image = new java.awt.image.BufferedImage(2, 2, java.awt.image.BufferedImage.TYPE_INT_RGB);
        var output = new java.io.ByteArrayOutputStream();
        javax.imageio.ImageIO.write(image, "png", output);
        output.write("PRIVATE_TRAILER".getBytes());
        upload(owner, conversation, "screen.png", "image/png", output.toByteArray(), UUID.randomUUID().toString()).andExpect(status().isOk());
        String attachment = lastUpload.path("id").asText();
        byte[] stored = mvc.perform(get(base(conversation) + "/attachments/" + attachment + "/content").session(owner.session())).andExpect(status().isOk()).andReturn().getResponse().getContentAsByteArray();
        assertFalse(new String(stored, java.nio.charset.StandardCharsets.ISO_8859_1).contains("PRIVATE_TRAILER"));
        assertNotNull(javax.imageio.ImageIO.read(new java.io.ByteArrayInputStream(stored)));
    }

    @Test void teamViewerCannotUploadAndRevocationAndFreezeBlockAccess() throws Exception {
        Client member = client();
        long team = json.readTree(send(owner, post("/api/teams"), Map.of("name", "附件团队", "description", ""))
                .andExpect(status().isOk()).andReturn().getResponse().getContentAsString()).path("data").path("id").asLong();
        jdbc.update("INSERT INTO team_member(team_id,user_id,role) VALUES(?,?,'viewer')", team, member.id());
        String conversation = create(owner, team);
        mvc.perform(get(base(conversation)).session(member.session())).andExpect(status().isOk());
        upload(member, conversation, "test.txt", "text/plain", "test".getBytes(), UUID.randomUUID().toString()).andExpect(status().isForbidden());
        jdbc.update("DELETE FROM team_member WHERE team_id=? AND user_id=?", team, member.id());
        mvc.perform(get(base(conversation)).session(member.session())).andExpect(status().isNotFound());
        jdbc.update("UPDATE team_workspace SET status='frozen' WHERE id=?", team);
        mvc.perform(get(base(conversation)).session(owner.session())).andExpect(status().isConflict());
    }

    @Test void deletingConversationDeletesBytesAndBlocksOldUrls() throws Exception {
        String conversation = create(owner, null);
        String attachment = uploadId(owner, conversation);
        send(owner, delete(base(conversation)), Map.of()).andExpect(status().isOk());
        mvc.perform(get(base(conversation) + "/attachments/" + attachment + "/content").session(owner.session())).andExpect(status().isNotFound());
        assertEquals(0L, jdbc.queryForObject("SELECT COUNT(*) FROM chat_attachment WHERE id=?", Long.class, attachment));
    }

    @Test void unauthenticatedAndCsrfLessWritesAreRejected() throws Exception {
        mvc.perform(get("/api/assistant/conversations")).andExpect(status().isUnauthorized());
        mvc.perform(post("/api/assistant/conversations").session(owner.session()).contentType("application/json").content("{}"))
                .andExpect(status().isForbidden());
    }

    @Test void sameOwnerCannotBindAnotherConversationAttachmentAndExpiredStagingIsRemoved() throws Exception {
        String first = create(owner, null), second = create(owner, null);
        String attachment = uploadId(owner, first);
        send(owner, post(base(second) + "/messages"), Map.of("requestId", UUID.randomUUID().toString(), "text", "", "attachmentIds", List.of(attachment))).andExpect(status().isNotFound());
        jdbc.update("UPDATE chat_attachment SET created_at=? WHERE id=?", System.currentTimeMillis() - 90_000_000L, attachment);
        mvc.perform(get(base(first) + "/attachments/" + attachment + "/content").session(owner.session())).andExpect(status().isNotFound());
        assertEquals(0L, jdbc.queryForObject("SELECT COUNT(*) FROM chat_attachment WHERE id=?", Long.class, attachment));
    }

    @Test void refusesOversizeInvalidUtf8AndScopeQuotaOverflow() throws Exception {
        String conversation = create(owner, null);
        upload(owner, conversation, "big.txt", "text/plain", new byte[20 * 1024 * 1024 + 1], UUID.randomUUID().toString()).andExpect(status().isBadRequest());
        upload(owner, conversation, "bad.txt", "text/plain", new byte[]{(byte) 0xc3, 0x28}, UUID.randomUUID().toString()).andExpect(status().isBadRequest());
        String attachment = uploadId(owner, conversation);
        jdbc.update("UPDATE chat_attachment SET byte_size=? WHERE id=?", 200 * 1024 * 1024L, attachment);
        upload(owner, conversation, "next.txt", "text/plain", "next".getBytes(), UUID.randomUUID().toString()).andExpect(status().isConflict());
    }

    @Test void concurrentMessageRetryIsSerialized() throws Exception {
        String conversation = create(owner, null);
        var input = Map.of("requestId", UUID.randomUUID().toString(), "text", "", "attachmentIds", List.of(uploadId(owner, conversation)));
        var executor = java.util.concurrent.Executors.newFixedThreadPool(2);
        try {
            var first = executor.submit(() -> send(owner, post(base(conversation) + "/messages"), input).andExpect(status().isOk()));
            var second = executor.submit(() -> send(owner, post(base(conversation) + "/messages"), input).andExpect(status().isOk()));
            first.get(10, java.util.concurrent.TimeUnit.SECONDS); second.get(10, java.util.concurrent.TimeUnit.SECONDS);
            assertEquals(2L, jdbc.queryForObject("SELECT COUNT(*) FROM chat_message WHERE conversation_id=?", Long.class, conversation));
        } finally { executor.shutdownNow(); }
    }

    @Test void stalePrincipalCannotAccessPersonalOrTeamAttachmentsAfterAccountRevocation() throws Exception {
        String conversation = create(owner, null);
        long team = json.readTree(send(owner, post("/api/teams"), Map.of("name", "撤权测试", "description", ""))
                .andExpect(status().isOk()).andReturn().getResponse().getContentAsString()).path("data").path("id").asLong();
        var stale = new com.smartops.security.SessionUser(owner.id(), "attachment-" + owner.id(), "operator");
        jdbc.update("UPDATE app_user SET enabled=FALSE WHERE id=?", owner.id());
        assertEquals(401, assertThrows(com.smartops.exception.BusinessException.class, () -> attachmentService.detail(stale, conversation)).getCode());
        assertEquals(401, assertThrows(com.smartops.exception.BusinessException.class, () -> attachmentService.list(stale, team)).getCode());
    }

    @Test void attachmentAuditActionsCanBeFilteredWithoutExposingFileNames() throws Exception {
        String conversation = create(owner, null);
        uploadId(owner, conversation);
        var entries = audit.list("CHAT_ATTACHMENT_UPLOAD", "SUCCESS", "attachment-" + owner.id(), 1, 20);
        assertEquals(1, entries.total());
        assertFalse(json.writeValueAsString(entries).contains("error.log"));
    }

    @Test void retentionReclaimsAbandonedUploadsForDisabledUsersButPreservesSentFiles() throws Exception {
        String conversation = create(owner, null);
        String sent = uploadId(owner, conversation);
        send(owner, post(base(conversation) + "/messages"), Map.of("requestId", UUID.randomUUID().toString(), "text", "", "attachmentIds", List.of(sent))).andExpect(status().isOk());
        String abandoned = uploadId(owner, conversation);
        jdbc.update("UPDATE chat_attachment SET created_at=? WHERE conversation_id=?", System.currentTimeMillis() - 90_000_000L, conversation);
        jdbc.update("UPDATE app_user SET enabled=FALSE WHERE id=?", owner.id());
        assertTrue(retention.sweep() >= 1);
        assertEquals(0L, jdbc.queryForObject("SELECT COUNT(*) FROM chat_attachment WHERE id=?", Long.class, abandoned));
        assertEquals(1L, jdbc.queryForObject("SELECT COUNT(*) FROM chat_attachment WHERE id=?", Long.class, sent));
    }

    private JsonNode lastUpload;
    private ResultActions upload(Client actor, String conversation, String name, String type, byte[] bytes, String requestId) throws Exception {
        var result = mvc.perform(multipart(base(conversation) + "/attachments").file(new MockMultipartFile("file", name, type, bytes))
                .param("requestId", requestId).session(actor.session()).header("X-CSRF-TOKEN", actor.csrf()));
        lastUpload = json.readTree(result.andReturn().getResponse().getContentAsString()).path("data");
        return result;
    }
    private String uploadId(Client actor, String conversation) throws Exception {
        upload(actor, conversation, "error.log", "text/plain", "error evidence".getBytes(), UUID.randomUUID().toString()).andExpect(status().isOk());
        return lastUpload.path("id").asText();
    }
    private String create(Client actor, Long teamId) throws Exception {
        var body = new java.util.HashMap<String, Object>();
        body.put("id", UUID.randomUUID().toString()); body.put("title", "附件会话");
        if (teamId != null) body.put("teamId", teamId);
        return json.readTree(send(actor, post("/api/assistant/conversations"), body).andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString()).path("data").path("id").asText();
    }
    private String base(String id) { return "/api/assistant/conversations/" + id; }
    private Client client() throws Exception {
        long id = IDS.incrementAndGet(); String name = "attachment-" + id;
        jdbc.update("INSERT INTO app_user(id,username,password_hash,role) VALUES(?,?,?,'operator')", id, name, HASH);
        var initial = mvc.perform(get("/api/auth/session")).andReturn();
        var session = (MockHttpSession) initial.getRequest().getSession(false);
        String csrf = json.readTree(initial.getResponse().getContentAsString()).path("data").path("csrfToken").asText();
        var login = mvc.perform(post("/api/auth/login").session(session).header("X-CSRF-TOKEN", csrf)
                .with(request -> { request.setRemoteAddr("192.0.2." + (id % 250 + 1)); return request; })
                .contentType("application/json").content(json.writeValueAsString(Map.of("username", name, "password", PASSWORD, "portal", "user"))))
                .andExpect(status().isOk()).andReturn();
        session = (MockHttpSession) login.getRequest().getSession(false);
        var refreshed = mvc.perform(get("/api/auth/session").session(session)).andReturn();
        return new Client(id, session, json.readTree(refreshed.getResponse().getContentAsString()).path("data").path("csrfToken").asText());
    }
    private ResultActions send(Client actor, MockHttpServletRequestBuilder request, Map<String, ?> body) throws Exception {
        return mvc.perform(request.session(actor.session()).header("X-CSRF-TOKEN", actor.csrf()).contentType("application/json").content(json.writeValueAsString(body)));
    }
    private record Client(long id, MockHttpSession session, String csrf) {}
}
