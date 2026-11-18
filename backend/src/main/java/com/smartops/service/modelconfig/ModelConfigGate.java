package com.smartops.service.modelconfig;

import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/**
 * 配置发布闸门：快照发布前必须通过的结构性校验。
 *
 * <p>校验的是"发布后会不会立刻打不通模型"，而不是模型回答质量。
 * 任何一条 error 都会阻断发布；warnings 只做提示，不影响发布。</p>
 */
@Component
public class ModelConfigGate {

    public record Report(
            boolean passed,
            List<String> errors,
            List<String> warnings,
            Map<String, Object> stats
    ) {}

    public Report evaluate(ModelConfigSnapshot snapshot) {
        List<String> errors = new ArrayList<>();
        List<String> warnings = new ArrayList<>();

        List<ModelConfigSnapshot.Group> groups = snapshot.groups() == null ? List.of() : snapshot.groups();
        List<ModelConfigSnapshot.Connection> connections =
                snapshot.connections() == null ? List.of() : snapshot.connections();

        if (groups.isEmpty()) {
            errors.add("配置中没有任何模型组");
        }
        if (connections.isEmpty()) {
            errors.add("配置中没有任何模型连接");
        }

        Map<Long, ModelConfigSnapshot.Connection> connectionById = new HashMap<>();
        for (ModelConfigSnapshot.Connection connection : connections) {
            connectionById.put(connection.id(), connection);
        }

        Set<String> slugs = new HashSet<>();
        Set<Long> routeIds = new HashSet<>();
        boolean anyUsable = false;
        int enabledGroups = 0;

        for (ModelConfigSnapshot.Group group : groups) {
            if (!group.enabled()) {
                continue;
            }
            enabledGroups++;
            if (!slugs.add(group.slug())) {
                errors.add("模型组 slug 重复：" + group.slug());
            }
            List<ModelConfigSnapshot.Route> routes =
                    group.routes() == null ? List.of() : group.routes();
            boolean auto = "AUTO".equalsIgnoreCase(group.routeMode());

            if (auto) {
                boolean hasChat = connections.stream()
                        .anyMatch(c -> c.enabled()
                                && Objects.equals(c.userId(), group.ownerUserId())
                                && (c.capabilities() == null || c.capabilities().isEmpty()
                                || c.capabilities().contains("chat")));
                if (hasChat) {
                    anyUsable = true;
                } else {
                    errors.add("AUTO 模型组 " + group.slug() + " 没有可用的 chat 连接");
                }
            } else {
                if (routes.isEmpty()) {
                    errors.add("MANUAL 模型组 " + group.slug() + " 没有任何路由");
                }
                boolean groupUsable = false;
                for (ModelConfigSnapshot.Route route : routes) {
                    if (!routeIds.add(route.id())) {
                        errors.add("路由 id 重复：" + route.id());
                    }
                    if (route.priority() < 0 || route.priority() > 10000) {
                        errors.add("模型组 " + group.slug() + " 的路由优先级越界：" + route.priority());
                    }
                    if (route.weight() < 1 || route.weight() > 1000) {
                        errors.add("模型组 " + group.slug() + " 的路由权重越界：" + route.weight());
                    }
                    ModelConfigSnapshot.Connection connection = connectionById.get(route.connectionId());
                    if (connection == null) {
                        errors.add("模型组 " + group.slug() + " 的路由指向不存在的连接：" + route.connectionId());
                        continue;
                    }
                    if (!Objects.equals(connection.userId(), group.ownerUserId())) {
                        errors.add("模型组 " + group.slug() + " 的路由跨用户引用连接：" + route.connectionId());
                    }
                    if (route.enabled() && connection.enabled()) {
                        groupUsable = true;
                    }
                }
                if (!routes.isEmpty() && !groupUsable) {
                    errors.add("模型组 " + group.slug() + " 没有一条可用路由（路由或连接被禁用）");
                }
                anyUsable = anyUsable || groupUsable;
            }
        }

        if (enabledGroups == 0 && !groups.isEmpty()) {
            errors.add("没有任何启用的模型组");
        }
        if (enabledGroups > 0 && !anyUsable) {
            errors.add("发布后没有任何模型组可用，将导致全部请求失败");
        }
        if (!connections.isEmpty() && connections.stream().noneMatch(ModelConfigSnapshot.Connection::enabled)) {
            warnings.add("所有模型连接都处于禁用状态");
        }

        Map<String, Object> stats = Map.of(
                "groups", groups.size(),
                "enabledGroups", enabledGroups,
                "connections", connections.size(),
                "routes", routeIds.size()
        );
        return new Report(errors.isEmpty(), List.copyOf(errors), List.copyOf(warnings), stats);
    }
}
