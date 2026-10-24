package com.smartops.operations;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class OperationRiskPolicyTest {
    private final OperationRiskPolicy policy = new OperationRiskPolicy();

    @Test
    void marks_read_only_diagnostics_low_risk() {
        OperationRiskPolicy.Assessment assessment = policy.assess("uname -a", false, false);
        assertThat(assessment.risk()).isEqualTo(OperationRiskPolicy.Risk.LOW);
        assertThat(assessment.requiredApprovals()).isEqualTo(0);
    }

    @Test
    void marks_production_multi_target_delete_critical() {
        OperationRiskPolicy.Assessment assessment = policy.assess("kubectl delete pod api", true, true);
        assertThat(assessment.risk()).isEqualTo(OperationRiskPolicy.Risk.CRITICAL);
        assertThat(assessment.requiredApprovals()).isEqualTo(2);
    }
}
