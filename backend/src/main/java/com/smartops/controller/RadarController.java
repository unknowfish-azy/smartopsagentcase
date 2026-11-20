package com.smartops.controller;

import com.smartops.common.ApiResponse;
import com.smartops.radar.RadarCollectionService;
import com.smartops.radar.RadarDigestService;
import com.smartops.radar.RadarItem;
import com.smartops.radar.RadarItemService;
import com.smartops.radar.RadarSource;
import com.smartops.radar.RadarSourceService;
import com.smartops.security.CurrentUser;
import com.smartops.security.SessionUser;
import com.smartops.security.UserAccountService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

/**
 * 资源雷达 P1 接口。
 *
 * <p>读取对已登录用户开放；来源登记、采集触发属于平台配置动作，需要 admin.config 能力位。
 * 采集会产生服务端出站请求，因此不接受匿名或普通操作员触发。</p>
 */
@RestController
@RequestMapping("/api/radar")
public class RadarController {

    private final RadarSourceService sources;
    private final RadarItemService items;
    private final RadarCollectionService collection;
    private final RadarDigestService digests;
    private final UserAccountService accounts;

    public RadarController(RadarSourceService sources, RadarItemService items, RadarCollectionService collection,
                           RadarDigestService digests, UserAccountService accounts) {
        this.sources = sources;
        this.items = items;
        this.collection = collection;
        this.digests = digests;
        this.accounts = accounts;
    }

    @GetMapping("/sources")
    public ApiResponse<List<RadarSource>> sources() {
        return ApiResponse.success(sources.list());
    }

    @PostMapping("/sources")
    public ApiResponse<RadarSource> createSource(@CurrentUser SessionUser actor, @RequestBody SourceRequest input) {
        requireConfig(actor);
        return ApiResponse.success(sources.create(actor, input.name(), input.collectorType(), input.url(),
                input.channel(), input.trustLevel(), input.intervalMinutes()));
    }

    @PutMapping("/sources/{id}")
    public ApiResponse<RadarSource> updateSource(@CurrentUser SessionUser actor, @PathVariable long id,
                                                 @RequestBody SourceUpdate input) {
        requireConfig(actor);
        return ApiResponse.success(sources.update(id, input.enabled(), input.intervalMinutes()));
    }

    @PostMapping("/sources/{id}/collect")
    public ApiResponse<RadarCollectionService.CollectionResult> collect(@CurrentUser SessionUser actor,
                                                                        @PathVariable long id,
                                                                        @RequestParam(required = false) String trigger) {
        requireConfig(actor);
        return ApiResponse.success(collection.collect(id, trigger));
    }

    @GetMapping("/items")
    public ApiResponse<List<RadarItem>> items(@RequestParam(required = false) String channel,
                                              @RequestParam(required = false) String kind,
                                              @RequestParam(required = false) String status,
                                              @RequestParam(required = false) String q,
                                              @RequestParam(required = false) Integer limit) {
        return ApiResponse.success(items.list(channel, kind, status, q, limit));
    }

    @GetMapping("/items/{id}")
    public ApiResponse<Map<String, Object>> item(@PathVariable long id) {
        return ApiResponse.success(items.detail(id));
    }

    @GetMapping("/stats")
    public ApiResponse<Map<String, Object>> stats() {
        return ApiResponse.success(items.stats());
    }

    @GetMapping("/digest/preview")
    public ApiResponse<RadarDigestService.DigestDraft> previewDigest(@RequestParam(required = false) String channel,
                                                                     @RequestParam(required = false) Integer hours) {
        return ApiResponse.success(digests.preview(channel, hours));
    }

    @PostMapping("/digest")
    public ApiResponse<RadarDigestService.DigestView> generateDigest(@CurrentUser SessionUser actor,
                                                                     @RequestParam(required = false) String channel,
                                                                     @RequestParam(required = false) Integer hours) {
        return ApiResponse.success(digests.generate(actor, channel, hours));
    }

    @GetMapping("/digests")
    public ApiResponse<List<Map<String, Object>>> digests(@CurrentUser SessionUser actor,
                                                          @RequestParam(required = false) Integer limit) {
        return ApiResponse.success(digests.list(actor.id(), limit));
    }

    @GetMapping("/digests/{id}")
    public ApiResponse<RadarDigestService.DigestView> digest(@CurrentUser SessionUser actor, @PathVariable long id) {
        return ApiResponse.success(digests.require(actor.id(), id));
    }

    private void requireConfig(SessionUser actor) {
        accounts.requirePlatformCapability(actor, "admin.config");
    }

    public record SourceRequest(String name, String collectorType, String url, String channel,
                                String trustLevel, Integer intervalMinutes) {
    }

    public record SourceUpdate(Boolean enabled, Integer intervalMinutes) {
    }
}
