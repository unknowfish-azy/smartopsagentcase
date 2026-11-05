package com.smartops.diagnostics.kubernetes;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartops.exception.BusinessException;
import com.smartops.operations.OperationRuntime;
import com.smartops.operations.OperationRuntimeRegistry;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.time.Duration;
import java.time.Instant;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.regex.Pattern;

/**
 * Kubernetes 只读诊断包（OPS-05）。
 *
 * <p><b>结论口径</b>：无权限（{@code NO_PERMISSION}）、数据缺失（{@code DATA_MISSING}）与
 * 真实故障（{@code FAULT}）三者必须可区分。采集不到不是健康：RBAC 拒绝不能被翻译成
 * “没有异常”，对象不存在也不能被翻译成“检查通过”。因此整体结果额外暴露
 * {@code permissionDenied} 与 {@code dataMissing}，调用方必须在两者都为 false 时才可
 * 把本次诊断当作“已观测且无故障”。</p>
 *
 * <p>所有命令均为只读（get/logs），单条命令 25s 超时，整单最多 8 条命令；
 * 命令预算耗尽时置 {@code truncated=true}，不把“没采完”当成“采完了且没问题”。</p>
 */
@Service
public class KubernetesDiagnosisService {

    static final long COMMAND_TIMEOUT_MS = 25_000L;
    static final int MAX_COMMANDS = 8;

    private static final String CHECK_POD_STATUS = "POD_STATUS";
    private static final String CHECK_PREVIOUS_LOGS = "PREVIOUS_LOGS";
    private static final String CHECK_EVENTS = "EVENTS";
    private static final String CHECK_PVC = "PVC";
    private static final String CHECK_NODE_CONDITIONS = "NODE_CONDITIONS";
    private static final String CHECK_ENDPOINT_SLICE = "ENDPOINT_SLICE";

    private static final String STATUS_OK = "OK";
    private static final String STATUS_FAULT = "FAULT";
    private static final String STATUS_NO_PERMISSION = "NO_PERMISSION";
    private static final String STATUS_DATA_MISSING = "DATA_MISSING";
    private static final String STATUS_ERROR = "ERROR";

    private static final String SEVERITY_CRITICAL = "CRITICAL";
    private static final String SEVERITY_WARNING = "WARNING";
    private static final String SEVERITY_INFO = "INFO";

    private static final String CRASH_LOOP = "CRASH_LOOP";
    private static final String OOM = "OOM";
    private static final String PENDING = "PENDING";
    private static final String IMAGE_PULL = "IMAGE_PULL";
    private static final String PROBE_FAILURE = "PROBE_FAILURE";
    private static final String PVC_MOUNT = "PVC_MOUNT";
    private static final String NODE_PRESSURE = "NODE_PRESSURE";
    private static final String ENDPOINT_NOT_READY = "ENDPOINT_NOT_READY";
    private static final String RESTARTS = "RESTARTS";

    private static final Pattern PERMISSION_ERROR =
            Pattern.compile("forbidden|unauthorized|cannot", Pattern.CASE_INSENSITIVE);
    private static final Pattern MISSING_ERROR =
            Pattern.compile("notfound|not found|no resources found", Pattern.CASE_INSENSITIVE);

    private static final Pattern SAFE_CONTEXT = Pattern.compile("[A-Za-z0-9][A-Za-z0-9._:@/-]{0,127}");
    private static final Pattern SAFE_NAMESPACE =
            Pattern.compile("[a-z0-9](?:[a-z0-9.-]{0,61}[a-z0-9])?");
    private static final Pattern SAFE_NAME = Pattern.compile("[A-Za-z0-9][A-Za-z0-9._-]{0,127}");

    private static final Set<String> NODE_PRESSURE_TYPES =
            Set.of("MemoryPressure", "DiskPressure", "PIDPressure");

    private final OperationRuntimeRegistry registry;
    private final ObjectMapper objectMapper;

    public KubernetesDiagnosisService(OperationRuntimeRegistry registry, ObjectMapper objectMapper) {
        this.registry = registry;
        this.objectMapper = objectMapper;
    }

    public KubernetesDiagnosisResult diagnose(Long userId, String runtimeId, KubernetesDiagnosisRequest request) {
        OperationRuntime runtime = registry.requireOwned(runtimeId, userId);
        if (!runtime.isOpen()) throw new BusinessException(409, "RUNTIME_CLOSED");
        validate(request);

        Instant startedAt = Instant.now();
        Run run = new Run(runtime, request, startedAt);
        PodInventory pods = collectPods(run);
        collectEvents(run);
        collectPvc(run);
        collectNodeConditions(run);
        collectEndpointSlices(run);
        collectPreviousLogs(run, pods);
        Instant endedAt = Instant.now();

        boolean permissionDenied = run.checks.stream()
                .anyMatch(check -> STATUS_NO_PERMISSION.equals(check.status()));
        boolean dataMissing = run.expectedEmpty || run.checks.stream()
                .anyMatch(check -> STATUS_DATA_MISSING.equals(check.status()));
        KubernetesScope scope = new KubernetesScope(request.context(), request.namespace(),
                request.workload(), request.pod(), request.container(), request.sinceMinutes());
        return new KubernetesDiagnosisResult(scope, startedAt.toString(), endedAt.toString(),
                Duration.between(startedAt, endedAt).toMillis(), List.copyOf(run.checks),
                List.copyOf(run.findings), permissionDenied, dataMissing, run.truncated);
    }

    /* ── 采集项 ─────────────────────────────────────────────────────────── */

    private PodInventory collectPods(Run run) {
        KubernetesDiagnosisRequest request = run.request;
        String command = "kubectl get pods"
                + (request.workload() == null ? "" : " -l app=" + request.workload())
                + " --context " + request.context()
                + " -n " + request.namespace()
                + " --request-timeout=20s -o json";
        Execution execution = run.execute(command);
        if (execution == null) {
            run.truncated = true;
            run.addCheck(CHECK_POD_STATUS, STATUS_ERROR, command, Instant.now(),
                    "command budget exhausted before pod status collection", 0);
            return PodInventory.empty();
        }
        if (execution.exitCode() != 0) {
            run.addCheck(CHECK_POD_STATUS, failureStatus(execution), command, execution.collectedAt(),
                    "kubectl get pods failed: " + brief(execution.stderr()), 0);
            return PodInventory.empty();
        }
        JsonNode root = readJson(execution);
        if (root == null) {
            run.addCheck(CHECK_POD_STATUS, STATUS_ERROR, command, execution.collectedAt(),
                    "pod status output is not valid JSON", 0);
            return PodInventory.empty();
        }

        int itemCount = 0;
        int findingCount = 0;
        List<PodInfo> podsNeedingLogs = new ArrayList<>();
        for (JsonNode pod : root.path("items")) {
            String podName = textAt(pod, "metadata", "name");
            if (request.pod() != null && !request.pod().equals(podName)) continue;
            itemCount++;

            String phase = textAt(pod, "status", "phase");
            Set<String> loggableContainers = new LinkedHashSet<>();
            boolean podNeedsLogs = false;
            for (JsonNode container : pod.path("status").path("containerStatuses")) {
                String containerName = textAt(container, "name");
                int restartCount = container.path("restartCount").asInt(0);
                String waitingReason = textAt(container, "state", "waiting", "reason");
                String waitingMessage = textAt(container, "state", "waiting", "message");
                String terminatedReason = textAt(container, "state", "terminated", "reason");
                String lastTerminatedReason = textAt(container, "lastState", "terminated", "reason");

                boolean crashLoop = "CrashLoopBackOff".equals(waitingReason);
                boolean imagePull = "ImagePullBackOff".equals(waitingReason)
                        || "ErrImagePull".equals(waitingReason)
                        || "InvalidImageName".equals(waitingReason);
                boolean oomKilled = "OOMKilled".equals(terminatedReason)
                        || "OOMKilled".equals(lastTerminatedReason);

                if (crashLoop) {
                    findingCount++;
                    run.finding(CRASH_LOOP, SEVERITY_CRITICAL, "Pod", podName,
                            "container " + containerName + " is in CrashLoopBackOff",
                            command, execution.collectedAt(),
                            "state.waiting.reason=CrashLoopBackOff restartCount=" + restartCount
                                    + " message=" + waitingMessage);
                }
                if (imagePull) {
                    findingCount++;
                    run.finding(IMAGE_PULL, SEVERITY_CRITICAL, "Pod", podName,
                            "container " + containerName + " cannot pull image: " + waitingReason,
                            command, execution.collectedAt(),
                            "state.waiting.reason=" + waitingReason + " message=" + waitingMessage);
                }
                if (oomKilled) {
                    findingCount++;
                    run.finding(OOM, SEVERITY_CRITICAL, "Pod", podName,
                            "container " + containerName + " was terminated by OOMKilled",
                            command, execution.collectedAt(),
                            "state.terminated.reason=" + terminatedReason
                                    + " lastState.terminated.reason=" + lastTerminatedReason
                                    + " restartCount=" + restartCount);
                }
                if (!crashLoop && !imagePull && !oomKilled && restartCount > 0) {
                    findingCount++;
                    run.finding(RESTARTS, SEVERITY_INFO, "Pod", podName,
                            "container " + containerName + " restarted " + restartCount + " time(s)",
                            command, execution.collectedAt(), "restartCount=" + restartCount);
                }

                if (crashLoop || restartCount > 0) {
                    podNeedsLogs = true;
                    if (!containerName.isBlank()) loggableContainers.add(containerName);
                }
            }
            if ("Pending".equals(phase)) {
                findingCount++;
                run.finding(PENDING, SEVERITY_WARNING, "Pod", podName,
                        "pod is stuck in Pending phase", command, execution.collectedAt(),
                        "status.phase=Pending");
            }
            if (podNeedsLogs) {
                podsNeedingLogs.add(new PodInfo(podName, firstOf(loggableContainers)));
            }
        }
        if (request.pod() != null && itemCount == 0) run.expectedEmpty = true;
        if (request.workload() != null && itemCount == 0) run.expectedEmpty = true;

        run.addCheck(CHECK_POD_STATUS, findingCount > 0 ? STATUS_FAULT : STATUS_OK, command,
                execution.collectedAt(), "pods=" + itemCount + " findings=" + findingCount, itemCount);
        return new PodInventory(podsNeedingLogs);
    }

    private void collectEvents(Run run) {
        KubernetesDiagnosisRequest request = run.request;
        String command = "kubectl get events --context " + request.context()
                + " -n " + request.namespace()
                + " --request-timeout=20s"
                + (request.pod() == null ? "" : " --field-selector involvedObject.name=" + request.pod())
                + " -o json";
        Execution execution = run.execute(command);
        if (execution == null) {
            run.truncated = true;
            run.addCheck(CHECK_EVENTS, STATUS_ERROR, command, Instant.now(),
                    "command budget exhausted before event collection", 0);
            return;
        }
        if (execution.exitCode() != 0) {
            run.addCheck(CHECK_EVENTS, failureStatus(execution), command, execution.collectedAt(),
                    "kubectl get events failed: " + brief(execution.stderr()), 0);
            return;
        }
        JsonNode root = readJson(execution);
        if (root == null) {
            run.addCheck(CHECK_EVENTS, STATUS_ERROR, command, execution.collectedAt(),
                    "event output is not valid JSON", 0);
            return;
        }

        Instant cutoff = run.startedAt.minusSeconds(request.sinceMinutes());
        int itemCount = 0;
        int findingCount = 0;
        for (JsonNode event : root.path("items")) {
            Instant eventTime = eventTimestamp(event);
            if (eventTime != null && eventTime.isBefore(cutoff)) continue;
            itemCount++;

            String reason = textAt(event, "reason");
            String message = textAt(event, "message");
            String kind = textAt(event, "involvedObject", "kind");
            String name = textAt(event, "involvedObject", "name");
            String resourceKind = kind.isBlank() ? "Pod" : kind;
            Instant evidenceAt = eventTime == null ? execution.collectedAt() : eventTime;

            KubernetesFinding finding = eventFinding(run, reason, message, resourceKind, name, command, evidenceAt);
            if (finding != null) {
                findingCount++;
                run.findings.add(finding);
            }
        }
        run.addCheck(CHECK_EVENTS, findingCount > 0 ? STATUS_FAULT : STATUS_OK, command,
                execution.collectedAt(), "events=" + itemCount + " findings=" + findingCount, itemCount);
    }

    private KubernetesFinding eventFinding(Run run, String reason, String message, String resourceKind,
                                           String resourceName, String command, Instant evidenceAt) {
        String namespace = run.request.namespace();
        if ("FailedScheduling".equals(reason)) {
            if (containsIgnoreCase(message, "insufficient")) {
                return new KubernetesFinding(NODE_PRESSURE, SEVERITY_WARNING, resourceKind, resourceName,
                        namespace, "scheduling failed because nodes lack capacity: " + brief(message),
                        command, evidenceAt.toString(), "event.reason=FailedScheduling message=" + message);
            }
            return new KubernetesFinding(PENDING, SEVERITY_WARNING, resourceKind, resourceName,
                    namespace, "pod cannot be scheduled: " + brief(message),
                    command, evidenceAt.toString(), "event.reason=FailedScheduling message=" + message);
        }
        if ("FailedMount".equals(reason) || "FailedAttachVolume".equals(reason)) {
            return new KubernetesFinding(PVC_MOUNT, SEVERITY_CRITICAL, resourceKind, resourceName,
                    namespace, "volume mount failed: " + brief(message),
                    command, evidenceAt.toString(), "event.reason=" + reason + " message=" + message);
        }
        if ("Unhealthy".equals(reason)
                && (containsIgnoreCase(message, "probe failed")
                || containsIgnoreCase(message, "readiness")
                || containsIgnoreCase(message, "liveness"))) {
            return new KubernetesFinding(PROBE_FAILURE, SEVERITY_WARNING, resourceKind, resourceName,
                    namespace, "probe check failed: " + brief(message),
                    command, evidenceAt.toString(), "event.reason=Unhealthy message=" + message);
        }
        if (("FailedCreate".equals(reason) || "BackOff".equals(reason))
                && containsIgnoreCase(message, "pull")) {
            return new KubernetesFinding(IMAGE_PULL, SEVERITY_CRITICAL, resourceKind, resourceName,
                    namespace, "image pull failed: " + brief(message),
                    command, evidenceAt.toString(), "event.reason=" + reason + " message=" + message);
        }
        return null;
    }

    private void collectPvc(Run run) {
        KubernetesDiagnosisRequest request = run.request;
        String command = "kubectl get pvc --context " + request.context()
                + " -n " + request.namespace()
                + " --request-timeout=20s -o json";
        Execution execution = run.execute(command);
        if (execution == null) {
            run.truncated = true;
            run.addCheck(CHECK_PVC, STATUS_ERROR, command, Instant.now(),
                    "command budget exhausted before PVC collection", 0);
            return;
        }
        if (execution.exitCode() != 0) {
            run.addCheck(CHECK_PVC, failureStatus(execution), command, execution.collectedAt(),
                    "kubectl get pvc failed: " + brief(execution.stderr()), 0);
            return;
        }
        JsonNode root = readJson(execution);
        if (root == null) {
            run.addCheck(CHECK_PVC, STATUS_ERROR, command, execution.collectedAt(),
                    "PVC output is not valid JSON", 0);
            return;
        }

        int itemCount = 0;
        int findingCount = 0;
        for (JsonNode pvc : root.path("items")) {
            itemCount++;
            String name = textAt(pvc, "metadata", "name");
            String phase = textAt(pvc, "status", "phase");
            if (!"Bound".equals(phase)) {
                findingCount++;
                run.finding(PVC_MOUNT, "Lost".equals(phase) ? SEVERITY_CRITICAL : SEVERITY_WARNING,
                        "PersistentVolumeClaim", name,
                        "PVC is not bound (phase=" + (phase.isBlank() ? "Unknown" : phase) + ")",
                        command, execution.collectedAt(), "status.phase=" + phase);
            }
        }
        run.addCheck(CHECK_PVC, findingCount > 0 ? STATUS_FAULT : STATUS_OK, command,
                execution.collectedAt(), "pvcs=" + itemCount + " findings=" + findingCount, itemCount);
    }

    private void collectNodeConditions(Run run) {
        KubernetesDiagnosisRequest request = run.request;
        String command = "kubectl get nodes --context " + request.context()
                + " -n " + request.namespace()
                + " --request-timeout=20s -o json";
        Execution execution = run.execute(command);
        if (execution == null) {
            run.truncated = true;
            run.addCheck(CHECK_NODE_CONDITIONS, STATUS_ERROR, command, Instant.now(),
                    "command budget exhausted before node condition collection", 0);
            return;
        }
        if (execution.exitCode() != 0) {
            run.addCheck(CHECK_NODE_CONDITIONS, failureStatus(execution), command, execution.collectedAt(),
                    "kubectl get nodes failed: " + brief(execution.stderr()), 0);
            return;
        }
        JsonNode root = readJson(execution);
        if (root == null) {
            run.addCheck(CHECK_NODE_CONDITIONS, STATUS_ERROR, command, execution.collectedAt(),
                    "node output is not valid JSON", 0);
            return;
        }

        int itemCount = 0;
        int findingCount = 0;
        for (JsonNode node : root.path("items")) {
            itemCount++;
            String nodeName = textAt(node, "metadata", "name");
            for (JsonNode condition : node.path("status").path("conditions")) {
                String type = textAt(condition, "type");
                String conditionStatus = textAt(condition, "status");
                if (NODE_PRESSURE_TYPES.contains(type) && "True".equals(conditionStatus)) {
                    findingCount++;
                    run.finding(NODE_PRESSURE, SEVERITY_WARNING, "Node", nodeName,
                            "node reports " + type, command, execution.collectedAt(),
                            "condition.type=" + type + " status=" + conditionStatus);
                }
                if ("Ready".equals(type) && !"True".equals(conditionStatus)) {
                    findingCount++;
                    run.finding(NODE_PRESSURE, SEVERITY_CRITICAL, "Node", nodeName,
                            "node is not Ready", command, execution.collectedAt(),
                            "condition.type=Ready status=" + conditionStatus);
                }
            }
        }
        run.addCheck(CHECK_NODE_CONDITIONS, findingCount > 0 ? STATUS_FAULT : STATUS_OK, command,
                execution.collectedAt(), "nodes=" + itemCount + " findings=" + findingCount, itemCount);
    }

    private void collectEndpointSlices(Run run) {
        KubernetesDiagnosisRequest request = run.request;
        String command = "kubectl get endpointslices --context " + request.context()
                + " -n " + request.namespace()
                + " --request-timeout=20s"
                + (request.workload() == null ? "" : " -l kubernetes.io/service-name=" + request.workload())
                + " -o json";
        Execution execution = run.execute(command);
        if (execution == null) {
            run.truncated = true;
            run.addCheck(CHECK_ENDPOINT_SLICE, STATUS_ERROR, command, Instant.now(),
                    "command budget exhausted before endpoint slice collection", 0);
            return;
        }
        if (execution.exitCode() != 0) {
            run.addCheck(CHECK_ENDPOINT_SLICE, failureStatus(execution), command, execution.collectedAt(),
                    "kubectl get endpointslices failed: " + brief(execution.stderr()), 0);
            return;
        }
        JsonNode root = readJson(execution);
        if (root == null) {
            run.addCheck(CHECK_ENDPOINT_SLICE, STATUS_ERROR, command, execution.collectedAt(),
                    "endpoint slice output is not valid JSON", 0);
            return;
        }

        int itemCount = 0;
        int findingCount = 0;
        for (JsonNode slice : root.path("items")) {
            itemCount++;
            String name = textAt(slice, "metadata", "name");
            JsonNode endpoints = slice.path("endpoints");
            boolean empty = endpoints.isArray() && endpoints.isEmpty();
            boolean hasNotReady = false;
            if (endpoints.isArray()) {
                for (JsonNode endpoint : endpoints) {
                    JsonNode ready = endpoint.path("conditions").path("ready");
                    if (ready.isBoolean() && !ready.asBoolean()) {
                        hasNotReady = true;
                    }
                }
            }
            JsonNode legacyNotReady = slice.path("notReadyAddresses");
            if (legacyNotReady.isArray() && !legacyNotReady.isEmpty()) {
                hasNotReady = true;
            }
            if (empty) {
                findingCount++;
                run.finding(ENDPOINT_NOT_READY, SEVERITY_INFO, "EndpointSlice", name,
                        "EndpointSlice has no endpoints", command, execution.collectedAt(),
                        "endpoints=0");
            } else if (hasNotReady) {
                findingCount++;
                run.finding(ENDPOINT_NOT_READY, SEVERITY_WARNING, "EndpointSlice", name,
                        "EndpointSlice has endpoints that are not ready", command, execution.collectedAt(),
                        "endpoints.conditions.ready=false");
            }
        }
        if (request.workload() != null && itemCount == 0) run.expectedEmpty = true;

        run.addCheck(CHECK_ENDPOINT_SLICE, findingCount > 0 ? STATUS_FAULT : STATUS_OK, command,
                execution.collectedAt(), "endpointSlices=" + itemCount + " findings=" + findingCount, itemCount);
    }

    private void collectPreviousLogs(Run run, PodInventory pods) {
        List<LogTarget> targets = new ArrayList<>();
        for (PodInfo pod : pods.loggablePods) {
            String container = run.request.container() == null ? pod.preferredContainer : run.request.container();
            targets.add(new LogTarget(pod.name, container));
        }
        if (targets.isEmpty()) {
            run.addCheck(CHECK_PREVIOUS_LOGS, STATUS_OK, "kubectl logs --previous --tail=200", Instant.now(),
                    "no crash-loop or restarted pod requires previous logs", 0);
            return;
        }

        String firstCommand = null;
        Instant lastCollectedAt = null;
        int collected = 0;
        String aggregateStatus = STATUS_OK;
        for (LogTarget target : targets) {
            if (run.remainingCommands() <= 0) {
                run.truncated = true;
                break;
            }
            String command = logCommand(run.request, target);
            if (firstCommand == null) firstCommand = command;
            Execution execution = run.execute(command);
            if (execution == null) {
                run.truncated = true;
                break;
            }
            lastCollectedAt = execution.collectedAt();
            if (execution.exitCode() == 0) {
                collected++;
                continue;
            }
            String message = execution.stderr().isBlank() ? execution.stdout() : execution.stderr();
            String status;
            if (PERMISSION_ERROR.matcher(message).find()) {
                status = STATUS_NO_PERMISSION;
            } else if (containsIgnoreCase(message, "previous terminated container")
                    || MISSING_ERROR.matcher(message).find()) {
                status = STATUS_DATA_MISSING;
            } else {
                status = STATUS_ERROR;
            }
            aggregateStatus = worseStatus(aggregateStatus, status);
        }
        run.addCheck(CHECK_PREVIOUS_LOGS, aggregateStatus,
                firstCommand == null ? "kubectl logs --previous --tail=200" : firstCommand,
                lastCollectedAt == null ? Instant.now() : lastCollectedAt,
                "previous logs collected for " + collected + "/" + targets.size() + " pod(s)",
                collected);
    }

    /* ── 结果判定与解析辅助 ─────────────────────────────────────────────── */

    private static String failureStatus(Execution execution) {
        String message = execution.stderr().isBlank() ? execution.stdout() : execution.stderr();
        if (PERMISSION_ERROR.matcher(message).find()) return STATUS_NO_PERMISSION;
        if (MISSING_ERROR.matcher(message).find()) return STATUS_DATA_MISSING;
        return STATUS_ERROR;
    }

    private static String worseStatus(String current, String candidate) {
        int currentRank = statusRank(current);
        int candidateRank = statusRank(candidate);
        return candidateRank > currentRank ? candidate : current;
    }

    private static int statusRank(String status) {
        return switch (status) {
            case STATUS_NO_PERMISSION -> 3;
            case STATUS_ERROR -> 2;
            case STATUS_DATA_MISSING -> 1;
            default -> 0;
        };
    }

    private JsonNode readJson(Execution execution) {
        if (execution.stdout().isBlank()) return null;
        try {
            return objectMapper.readTree(execution.stdout());
        } catch (JsonProcessingException ex) {
            return null;
        }
    }

    private static Instant eventTimestamp(JsonNode event) {
        for (String field : List.of("lastTimestamp", "eventTime", "firstTimestamp")) {
            Instant parsed = parseInstant(textAt(event, field));
            if (parsed != null) return parsed;
        }
        return null;
    }

    private static Instant parseInstant(String value) {
        if (value == null || value.isBlank()) return null;
        try {
            return Instant.parse(value);
        } catch (DateTimeParseException ex) {
            return null;
        }
    }

    private static boolean containsIgnoreCase(String value, String needle) {
        return value != null && value.toLowerCase(Locale.ROOT).contains(needle.toLowerCase(Locale.ROOT));
    }

    private static String textAt(JsonNode node, String... path) {
        JsonNode current = node;
        for (String segment : path) {
            if (current == null) return "";
            current = current.path(segment);
        }
        if (current == null || current.isMissingNode() || current.isNull()) return "";
        return current.asText("");
    }

    private static String brief(String value) {
        if (value == null) return "";
        String singleLine = value.replace('\n', ' ').replace('\r', ' ').trim();
        return singleLine.length() <= 200 ? singleLine : singleLine.substring(0, 200) + "...";
    }

    private static String firstOf(Set<String> values) {
        return values.isEmpty() ? null : values.iterator().next();
    }

    private static String logCommand(KubernetesDiagnosisRequest request, LogTarget target) {
        return "kubectl logs " + target.podName
                + (target.container == null ? "" : " -c " + target.container)
                + " --previous --tail=200 --context " + request.context()
                + " -n " + request.namespace() + " --request-timeout=20s";
    }

    private static void validate(KubernetesDiagnosisRequest request) {
        if (!SAFE_CONTEXT.matcher(request.context() == null ? "" : request.context()).matches()) {
            invalid("context");
        }
        if (!SAFE_NAMESPACE.matcher(request.namespace() == null ? "" : request.namespace()).matches()) {
            invalid("namespace");
        }
        validateOptionalName(request.workload(), "workload");
        validateOptionalName(request.pod(), "pod");
        validateOptionalName(request.container(), "container");
    }

    private static void validateOptionalName(String value, String field) {
        if (value != null && !SAFE_NAME.matcher(value).matches()) invalid(field);
    }

    private static void invalid(String field) {
        throw new BusinessException(400, "INVALID_KUBERNETES_DIAGNOSIS_PARAMETER: " + field);
    }

    private static String text(String value) {
        return value == null ? "" : value;
    }

    /* ── 对外模型 ───────────────────────────────────────────────────────── */

    public record KubernetesScope(String context, String namespace, String workload, String pod,
                                  String container, int sinceMinutes) {}

    public record KubernetesCheck(String name, String status, String command, String collectedAt,
                                  String summary, int itemCount) {}

    public record KubernetesFinding(String type, String severity, String resourceKind, String resourceName,
                                    String namespace, String summary, String evidenceCommand,
                                    String evidenceAt, String detail) {}

    public record KubernetesDiagnosisResult(KubernetesScope scope, String startedAt, String endedAt,
                                            long durationMs, List<KubernetesCheck> checks,
                                            List<KubernetesFinding> findings, boolean permissionDenied,
                                            boolean dataMissing, boolean truncated) {}

    /* ── 内部运行态 ─────────────────────────────────────────────────────── */

    private record Execution(String command, int exitCode, String stdout, String stderr, Instant collectedAt) {}

    private record PodInfo(String name, String preferredContainer) {}

    private record PodInventory(List<PodInfo> loggablePods) {
        static PodInventory empty() { return new PodInventory(List.of()); }
    }

    private record LogTarget(String podName, String container) {}

    private static final class Run {
        private final OperationRuntime runtime;
        private final KubernetesDiagnosisRequest request;
        private final Instant startedAt;
        private final List<KubernetesCheck> checks = new ArrayList<>();
        private final List<KubernetesFinding> findings = new ArrayList<>();
        private int commandsUsed;
        private boolean truncated;
        private boolean expectedEmpty;

        private Run(OperationRuntime runtime, KubernetesDiagnosisRequest request, Instant startedAt) {
            this.runtime = runtime;
            this.request = request;
            this.startedAt = startedAt;
        }

        private Execution execute(String command) {
            if (commandsUsed >= MAX_COMMANDS) {
                truncated = true;
                return null;
            }
            commandsUsed++;
            try {
                OperationRuntime.CommandResult result = runtime.execute(command, COMMAND_TIMEOUT_MS);
                return new Execution(command, result.exitCode(), text(result.stdout()), text(result.stderr()),
                        Instant.now());
            } catch (IOException ex) {
                String message = ex.getMessage();
                return new Execution(command, -1, "",
                        message == null || message.isBlank() ? "COMMAND_EXECUTION_FAILED" : message,
                        Instant.now());
            }
        }

        private int remainingCommands() {
            return MAX_COMMANDS - commandsUsed;
        }

        private void addCheck(String name, String status, String command, Instant collectedAt,
                              String summary, int itemCount) {
            checks.add(new KubernetesCheck(name, status, command, collectedAt.toString(), summary, itemCount));
        }

        private void finding(String type, String severity, String resourceKind,
                             String resourceName, String summary, String evidenceCommand,
                             Instant evidenceAt, String detail) {
            findings.add(new KubernetesFinding(type, severity, resourceKind, resourceName, request.namespace(),
                    summary, evidenceCommand, evidenceAt.toString(), detail));
        }
    }
}
