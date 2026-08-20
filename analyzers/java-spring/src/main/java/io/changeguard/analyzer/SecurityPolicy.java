package io.changeguard.analyzer;

import java.util.List;

public record SecurityPolicy(
        String component,
        String methodName,
        List<SecurityAuthorizationRule> authorizationRules,
        List<String> disabledFeatures
) {
    public String methodIdentity() {
        return component + "#" + methodName;
    }
}
