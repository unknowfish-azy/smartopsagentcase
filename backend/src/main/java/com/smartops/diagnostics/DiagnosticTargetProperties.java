package com.smartops.diagnostics;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;
import java.util.List;

@Component
@ConfigurationProperties(prefix = "smartops.diagnostics")
public class DiagnosticTargetProperties {
    private List<Target> targets = List.of();
    public List<Target> getTargets() { return targets; }
    public void setTargets(List<Target> targets) { this.targets = targets == null ? List.of() : List.copyOf(targets); }
    public record Target(String id, String displayName, String scheme, String hostname, Integer port, String path,
                         List<String> pinnedAddresses, List<Long> allowedUserIds, Integer expectedStatus) {}
}
