package io.changeguard.analyzer;

public record SecurityPolicyChange(
        SecurityPolicyChangeKind kind,
        SecurityPolicy before,
        SecurityPolicy after
) {
}
