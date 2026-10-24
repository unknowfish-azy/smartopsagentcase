package com.smartops.controller;

import com.smartops.common.ApiResponse;
import com.smartops.service.PersonalKnowledgeService;
import lombok.RequiredArgsConstructor;
import com.smartops.security.SessionUser;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/knowledge/personal")
@RequiredArgsConstructor
public class PersonalKnowledgeController {
    private final PersonalKnowledgeService service;

    @PostMapping("/libraries")
    public ApiResponse<PersonalKnowledgeService.Library> createLibrary(@AuthenticationPrincipal SessionUser user, @RequestBody LibraryRequest request) {
        return ApiResponse.success(service.createLibrary(user.id(), request.name(), request.description()));
    }

    @GetMapping("/libraries")
    public ApiResponse<java.util.List<PersonalKnowledgeService.Library>> libraries(@AuthenticationPrincipal SessionUser user) {
        return ApiResponse.success(service.listLibraries(user.id()));
    }

    @GetMapping("/libraries/{libraryId}")
    public ApiResponse<PersonalKnowledgeService.Library> library(@AuthenticationPrincipal SessionUser user, @PathVariable Long libraryId) {
        return ApiResponse.success(service.detailLibrary(user.id(), libraryId));
    }

    @PatchMapping("/libraries/{libraryId}")
    public ApiResponse<PersonalKnowledgeService.Library> updateLibrary(@AuthenticationPrincipal SessionUser user, @PathVariable Long libraryId, @RequestBody LibraryRequest request) {
        return ApiResponse.success(service.renameLibrary(user.id(), libraryId, request.name(), request.description()));
    }

    @PostMapping("/libraries/{libraryId}/archive")
    public ApiResponse<PersonalKnowledgeService.Library> archiveLibrary(@AuthenticationPrincipal SessionUser user, @PathVariable Long libraryId) {
        return ApiResponse.success(service.setLibraryStatus(user.id(), libraryId, "ARCHIVED"));
    }

    @PostMapping("/libraries/{libraryId}/restore")
    public ApiResponse<PersonalKnowledgeService.Library> restoreLibrary(@AuthenticationPrincipal SessionUser user, @PathVariable Long libraryId) {
        return ApiResponse.success(service.setLibraryStatus(user.id(), libraryId, "ACTIVE"));
    }

    @PostMapping("/libraries/{libraryId}/entries")
    public ApiResponse<PersonalKnowledgeService.Entry> createEntry(@AuthenticationPrincipal SessionUser user, @PathVariable Long libraryId, @RequestBody EntryRequest request) {
        return ApiResponse.success(service.createEntry(user.id(), libraryId, request.title(), request.summary(), request.contentMarkdown(), request.sourceType(), request.sourceRef()));
    }

    @GetMapping("/libraries/{libraryId}/entries")
    public ApiResponse<PersonalKnowledgeService.EntryPage> entries(@AuthenticationPrincipal SessionUser user, @PathVariable Long libraryId, @RequestParam(required = false) String query, @RequestParam(defaultValue = "1") int page, @RequestParam(defaultValue = "20") int pageSize) {
        return ApiResponse.success(service.listEntries(user.id(), libraryId, query, page, pageSize));
    }

    @GetMapping("/entries/{entryId}")
    public ApiResponse<PersonalKnowledgeService.Entry> entry(@AuthenticationPrincipal SessionUser user, @PathVariable Long entryId) {
        return ApiResponse.success(service.detailEntry(user.id(), entryId));
    }

    @PatchMapping("/entries/{entryId}")
    public ApiResponse<PersonalKnowledgeService.Entry> update(@AuthenticationPrincipal SessionUser user, @PathVariable Long entryId, @RequestBody EntryUpdate request) {
        return ApiResponse.success(service.updateEntry(user.id(), entryId, request.title(), request.summary(), request.contentMarkdown()));
    }

    @PostMapping("/entries/{entryId}/archive")
    public ApiResponse<Void> archive(@AuthenticationPrincipal SessionUser user, @PathVariable Long entryId) {
        service.archiveEntry(user.id(), entryId);
        return ApiResponse.success();
    }

    @DeleteMapping("/entries/{entryId}")
    public ApiResponse<Void> delete(@AuthenticationPrincipal SessionUser user, @PathVariable Long entryId) {
        service.deleteEntry(user.id(), entryId);
        return ApiResponse.success();
    }

    public record LibraryRequest(String name, String description) {}
    public record EntryRequest(String title, String summary, String contentMarkdown, String sourceType, String sourceRef) {}
    public record EntryUpdate(String title, String summary, String contentMarkdown) {}
}
