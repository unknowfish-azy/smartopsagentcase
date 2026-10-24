package com.smartops.controller;

import com.smartops.common.ApiResponse;
import com.smartops.knowledge.PersonalKnowledgeIndexService;
import com.smartops.service.PersonalKnowledgeService;
import org.springframework.web.bind.annotation.*;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.multipart.MultipartFile;
import com.smartops.security.SessionUser;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import java.nio.charset.StandardCharsets;
import java.util.Map;

@RestController
@RequestMapping("/api/knowledge/personal/libraries")
public class PersonalKnowledgeFileController {
    private final PersonalKnowledgeIndexService index;
    private final PersonalKnowledgeService knowledge;
    public PersonalKnowledgeFileController(PersonalKnowledgeIndexService index, PersonalKnowledgeService knowledge) { this.index = index; this.knowledge = knowledge; }

    @PostMapping("/{libraryId}/reindex")
    public ApiResponse<PersonalKnowledgeIndexService.HealthReport> reindex(@AuthenticationPrincipal SessionUser user, @PathVariable Long libraryId) {
        return ApiResponse.success(index.rebuild(user.id(), libraryId));
    }

    @PostMapping(value = "/{libraryId}/import", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ApiResponse<Map<String, Object>> importMarkdown(@AuthenticationPrincipal SessionUser user, @PathVariable Long libraryId, @RequestPart MultipartFile file) {
        if (file.isEmpty() || file.getOriginalFilename() == null || !file.getOriginalFilename().toLowerCase().matches(".*\\.(md|markdown|txt)$"))
            throw new com.smartops.exception.BusinessException(400, "KNOWLEDGE_IMPORT_FORMAT_UNSUPPORTED");
        try {
            String name = file.getOriginalFilename();
            String title = name.replaceFirst("\\.[^.]+$", "");
            var entry = knowledge.createEntry(user.id(), libraryId, title, "导入的个人知识文件", new String(file.getBytes(), StandardCharsets.UTF_8), "IMPORT", name);
            return ApiResponse.success(Map.of("accepted", true, "name", name, "bytes", file.getSize(), "entryId", entry.id()));
        } catch (java.io.IOException failure) { throw new com.smartops.exception.BusinessException(400, "KNOWLEDGE_IMPORT_READ_FAILED"); }
    }

    @GetMapping("/{libraryId}/export")
    public ResponseEntity<byte[]> export(@AuthenticationPrincipal SessionUser user, @PathVariable Long libraryId) {
        var page = knowledge.listEntries(user.id(), libraryId, null, 1, 100);
        StringBuilder markdown = new StringBuilder("# Personal Knowledge Export\n\nLibrary: ").append(libraryId).append("\nUser: ").append(user.id()).append("\n");
        for (var entry : page.items()) markdown.append("\n---\n\n").append(entry.contentMarkdown()).append("\n");
        return ResponseEntity.ok().contentType(MediaType.TEXT_MARKDOWN).header("Content-Disposition", "attachment; filename=personal-knowledge.md").body(markdown.toString().getBytes(StandardCharsets.UTF_8));
    }
}
