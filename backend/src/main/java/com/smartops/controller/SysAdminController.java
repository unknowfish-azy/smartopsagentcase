package com.smartops.controller;

import com.smartops.admin.SysDictService;
import com.smartops.admin.SysLoginLogService;
import com.smartops.admin.SysNoticeService;
import com.smartops.admin.SysOrgService;
import com.smartops.admin.SysRbacService;
import com.smartops.common.ApiResponse;
import com.smartops.security.SessionUser;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * 企业级系统管理：部门 / 岗位 / 角色 / 菜单 / 字典 / 公告 / 登录日志。
 *
 * <p>全部位于 {@code /api/admin/system/**}，由 SecurityConfig 的
 * {@code hasRole("ADMIN")} + AdminConfirmationFilter 统一守卫，
 * 不在每个方法里重复校验角色。</p>
 */
@RestController
@RequestMapping("/api/admin/system")
public class SysAdminController {

    private final SysOrgService org;
    private final SysDictService dict;
    private final SysRbacService rbac;
    private final SysNoticeService notice;
    private final SysLoginLogService loginLog;

    public SysAdminController(SysOrgService org, SysDictService dict, SysRbacService rbac, SysNoticeService notice,
                              SysLoginLogService loginLog) {
        this.org = org;
        this.dict = dict;
        this.rbac = rbac;
        this.notice = notice;
        this.loginLog = loginLog;
    }

    /* ── 部门 ─────────────────────────────────────────────────────────── */

    @GetMapping("/depts")
    public ApiResponse<List<Map<String, Object>>> depts() { return ApiResponse.success(org.deptTree()); }

    @PostMapping("/depts")
    public ApiResponse<Map<String, Object>> createDept(@AuthenticationPrincipal SessionUser actor, @RequestBody DeptRequest req) {
        return ApiResponse.success(org.createDept(actor, req.parentId(), req.name(), req.sort(), req.leader(), req.phone()));
    }

    @PutMapping("/depts/{id}")
    public ApiResponse<Map<String, Object>> updateDept(@AuthenticationPrincipal SessionUser actor, @PathVariable long id, @RequestBody DeptRequest req) {
        return ApiResponse.success(org.updateDept(actor, id, req.parentId(), req.name(), req.sort(), req.leader(), req.phone()));
    }

    @DeleteMapping("/depts/{id}")
    public ApiResponse<Void> deleteDept(@AuthenticationPrincipal SessionUser actor, @PathVariable long id) {
        org.deleteDept(actor, id); return ApiResponse.success();
    }

    @PutMapping("/depts/{id}/status")
    public ApiResponse<Void> deptStatus(@AuthenticationPrincipal SessionUser actor, @PathVariable long id, @RequestBody StatusRequest req) {
        org.setDeptStatus(actor, id, req.status()); return ApiResponse.success();
    }

    /* ── 岗位 ─────────────────────────────────────────────────────────── */

    @GetMapping("/posts")
    public ApiResponse<List<Map<String, Object>>> posts() { return ApiResponse.success(org.listPosts()); }

    @PostMapping("/posts")
    public ApiResponse<Map<String, Object>> createPost(@AuthenticationPrincipal SessionUser actor, @RequestBody PostRequest req) {
        return ApiResponse.success(org.createPost(actor, req.code(), req.name(), req.sort(), req.remark()));
    }

    @PutMapping("/posts/{id}")
    public ApiResponse<Map<String, Object>> updatePost(@AuthenticationPrincipal SessionUser actor, @PathVariable long id, @RequestBody PostRequest req) {
        return ApiResponse.success(org.updatePost(actor, id, req.code(), req.name(), req.sort(), req.remark()));
    }

    @DeleteMapping("/posts/{id}")
    public ApiResponse<Void> deletePost(@AuthenticationPrincipal SessionUser actor, @PathVariable long id) {
        org.deletePost(actor, id); return ApiResponse.success();
    }

    @PutMapping("/posts/{id}/status")
    public ApiResponse<Void> postStatus(@AuthenticationPrincipal SessionUser actor, @PathVariable long id, @RequestBody StatusRequest req) {
        org.setPostStatus(actor, id, req.status()); return ApiResponse.success();
    }

    /* ── 角色 ─────────────────────────────────────────────────────────── */

    @GetMapping("/roles")
    public ApiResponse<List<Map<String, Object>>> roles() { return ApiResponse.success(rbac.listRoles()); }

    @PostMapping("/roles")
    public ApiResponse<Map<String, Object>> createRole(@AuthenticationPrincipal SessionUser actor, @RequestBody RoleRequest req) {
        return ApiResponse.success(rbac.createRole(actor, req.name(), req.code(), req.sort(), req.dataScope(), req.remark()));
    }

    @PutMapping("/roles/{id}")
    public ApiResponse<Map<String, Object>> updateRole(@AuthenticationPrincipal SessionUser actor, @PathVariable long id, @RequestBody RoleRequest req) {
        return ApiResponse.success(rbac.updateRole(actor, id, req.name(), req.code(), req.sort(), req.dataScope(), req.remark()));
    }

    @DeleteMapping("/roles/{id}")
    public ApiResponse<Void> deleteRole(@AuthenticationPrincipal SessionUser actor, @PathVariable long id) {
        rbac.deleteRole(actor, id); return ApiResponse.success();
    }

    @PutMapping("/roles/{id}/status")
    public ApiResponse<Void> roleStatus(@AuthenticationPrincipal SessionUser actor, @PathVariable long id, @RequestBody StatusRequest req) {
        rbac.setRoleStatus(actor, id, req.status()); return ApiResponse.success();
    }

    @GetMapping("/roles/{id}/menus")
    public ApiResponse<Map<String, Object>> roleMenus(@PathVariable long id) {
        return ApiResponse.success(Map.of("menuIds", rbac.roleMenuIds(id)));
    }

    @PutMapping("/roles/{id}/menus")
    public ApiResponse<Void> grantMenus(@AuthenticationPrincipal SessionUser actor, @PathVariable long id, @RequestBody GrantMenusRequest req) {
        rbac.grantMenus(actor, id, req.menuIds()); return ApiResponse.success();
    }

    /* ── 菜单 ─────────────────────────────────────────────────────────── */

    @GetMapping("/menus")
    public ApiResponse<List<Map<String, Object>>> menus() { return ApiResponse.success(rbac.menuTree()); }

    @PostMapping("/menus")
    public ApiResponse<Map<String, Object>> createMenu(@AuthenticationPrincipal SessionUser actor, @RequestBody MenuRequest req) {
        return ApiResponse.success(rbac.createMenu(actor, req.parentId(), req.name(), req.type(), req.path(), req.component(), req.perms(), req.icon(), req.sort(), req.visible()));
    }

    @PutMapping("/menus/{id}")
    public ApiResponse<Map<String, Object>> updateMenu(@AuthenticationPrincipal SessionUser actor, @PathVariable long id, @RequestBody MenuRequest req) {
        return ApiResponse.success(rbac.updateMenu(actor, id, req.parentId(), req.name(), req.type(), req.path(), req.component(), req.perms(), req.icon(), req.sort(), req.visible()));
    }

    @DeleteMapping("/menus/{id}")
    public ApiResponse<Void> deleteMenu(@AuthenticationPrincipal SessionUser actor, @PathVariable long id) {
        rbac.deleteMenu(actor, id); return ApiResponse.success();
    }

    @PutMapping("/menus/{id}/status")
    public ApiResponse<Void> menuStatus(@AuthenticationPrincipal SessionUser actor, @PathVariable long id, @RequestBody StatusRequest req) {
        rbac.setMenuStatus(actor, id, req.status()); return ApiResponse.success();
    }

    /* ── 字典 ─────────────────────────────────────────────────────────── */

    @GetMapping("/dicts/types")
    public ApiResponse<List<Map<String, Object>>> dictTypes() { return ApiResponse.success(dict.listTypes()); }

    @PostMapping("/dicts/types")
    public ApiResponse<Map<String, Object>> createDictType(@AuthenticationPrincipal SessionUser actor, @RequestBody DictTypeRequest req) {
        return ApiResponse.success(dict.createType(actor, req.name(), req.type(), req.remark()));
    }

    @PutMapping("/dicts/types/{id}")
    public ApiResponse<Map<String, Object>> updateDictType(@AuthenticationPrincipal SessionUser actor, @PathVariable long id, @RequestBody DictTypeRequest req) {
        return ApiResponse.success(dict.updateType(actor, id, req.name(), req.type(), req.remark()));
    }

    @DeleteMapping("/dicts/types/{id}")
    public ApiResponse<Void> deleteDictType(@AuthenticationPrincipal SessionUser actor, @PathVariable long id) {
        dict.deleteType(actor, id); return ApiResponse.success();
    }

    @PutMapping("/dicts/types/{id}/status")
    public ApiResponse<Void> dictTypeStatus(@AuthenticationPrincipal SessionUser actor, @PathVariable long id, @RequestBody StatusRequest req) {
        dict.setTypeStatus(actor, id, req.status()); return ApiResponse.success();
    }

    @GetMapping("/dicts/{type}/data")
    public ApiResponse<List<Map<String, Object>>> dictData(@PathVariable String type) { return ApiResponse.success(dict.listData(type)); }

    @GetMapping("/dicts/{type}/enabled")
    public ApiResponse<List<Map<String, Object>>> dictDataEnabled(@PathVariable String type) { return ApiResponse.success(dict.enabledData(type)); }

    @PostMapping("/dicts/data")
    public ApiResponse<Map<String, Object>> createDictData(@AuthenticationPrincipal SessionUser actor, @RequestBody DictDataRequest req) {
        return ApiResponse.success(dict.createData(actor, req.type(), req.label(), req.value(), req.sort(), req.remark()));
    }

    @PutMapping("/dicts/data/{id}")
    public ApiResponse<Map<String, Object>> updateDictData(@AuthenticationPrincipal SessionUser actor, @PathVariable long id, @RequestBody DictDataRequest req) {
        return ApiResponse.success(dict.updateData(actor, id, req.type(), req.label(), req.value(), req.sort(), req.remark()));
    }

    @DeleteMapping("/dicts/data/{id}")
    public ApiResponse<Void> deleteDictData(@AuthenticationPrincipal SessionUser actor, @PathVariable long id) {
        dict.deleteData(actor, id); return ApiResponse.success();
    }

    @PutMapping("/dicts/data/{id}/status")
    public ApiResponse<Void> dictDataStatus(@AuthenticationPrincipal SessionUser actor, @PathVariable long id, @RequestBody StatusRequest req) {
        dict.setDataStatus(actor, id, req.status()); return ApiResponse.success();
    }

    /* ── 通知公告 ─────────────────────────────────────────────────────── */

    @GetMapping("/notices")
    public ApiResponse<List<Map<String, Object>>> notices(@RequestParam(defaultValue = "true") boolean includeDraft) {
        return ApiResponse.success(notice.list(includeDraft));
    }

    @PostMapping("/notices")
    public ApiResponse<Map<String, Object>> createNotice(@AuthenticationPrincipal SessionUser actor, @RequestBody NoticeRequest req) {
        return ApiResponse.success(notice.create(actor, req.title(), req.content(), req.type()));
    }

    @PutMapping("/notices/{id}")
    public ApiResponse<Map<String, Object>> updateNotice(@AuthenticationPrincipal SessionUser actor, @PathVariable long id, @RequestBody NoticeRequest req) {
        return ApiResponse.success(notice.update(actor, id, req.title(), req.content(), req.type()));
    }

    @PostMapping("/notices/{id}/publish")
    public ApiResponse<Void> publishNotice(@AuthenticationPrincipal SessionUser actor, @PathVariable long id) {
        notice.publish(actor, id); return ApiResponse.success();
    }

    @DeleteMapping("/notices/{id}")
    public ApiResponse<Void> deleteNotice(@AuthenticationPrincipal SessionUser actor, @PathVariable long id) {
        notice.delete(actor, id); return ApiResponse.success();
    }

    /* ── 登录日志 ─────────────────────────────────────────────────────── */

    @GetMapping("/login-logs")
    public ApiResponse<Map<String, Object>> loginLogs(@RequestParam(required = false) String q,
                                                      @RequestParam(defaultValue = "1") int page,
                                                      @RequestParam(defaultValue = "20") int pageSize) {
        return ApiResponse.success(loginLog.list(q, page, pageSize));
    }

    /* ── 请求体 ───────────────────────────────────────────────────────── */

    public record DeptRequest(long parentId, String name, int sort, String leader, String phone) {}
    public record PostRequest(String code, String name, int sort, String remark) {}
    public record RoleRequest(String name, String code, int sort, int dataScope, String remark) {}
    public record GrantMenusRequest(List<Long> menuIds) {}
    public record MenuRequest(long parentId, String name, int type, String path, String component, String perms, String icon, int sort, boolean visible) {}
    public record DictTypeRequest(String name, String type, String remark) {}
    public record DictDataRequest(String type, String label, String value, int sort, String remark) {}
    public record NoticeRequest(String title, String content, int type) {}
    public record StatusRequest(int status) {}
}
