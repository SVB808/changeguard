package io.changeguard.analyzer;

import java.util.List;

public record AnalysisResult(
        List<Endpoint> beforeEndpoints,
        List<Endpoint> afterEndpoints,
        List<EndpointChange> changes,
        List<SecurityPolicy> beforeSecurityPolicies,
        List<SecurityPolicy> afterSecurityPolicies,
        List<SecurityPolicyChange> securityChanges
) {
}
