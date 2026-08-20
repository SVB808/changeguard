package io.changeguard.analyzer;

import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;

class SecurityPolicyComparatorTest {

    private final SecurityPolicyComparator comparator = new SecurityPolicyComparator();

    @Test
    void detectsAddedSecurityPolicy() {
        SecurityPolicy after = new SecurityPolicy(
                "SecurityWebFilterChain",
                "securityWebFilterChain",
                List.of(new SecurityAuthorizationRule("anyExchange", List.of(), "permitAll")),
                List.of("csrf")
        );

        List<SecurityPolicyChange> changes = comparator.compare(List.of(), List.of(after));

        assertEquals(1, changes.size());
        assertEquals(SecurityPolicyChangeKind.SECURITY_POLICY_ADDED, changes.get(0).kind());
        assertEquals(after, changes.get(0).after());
    }

    @Test
    void detectsPolicyModification() {
        SecurityPolicy before = new SecurityPolicy(
                "SecurityFilterChain",
                "filterChain",
                List.of(new SecurityAuthorizationRule("anyRequest", List.of(), "authenticated")),
                List.of()
        );
        SecurityPolicy after = new SecurityPolicy(
                "SecurityFilterChain",
                "filterChain",
                List.of(new SecurityAuthorizationRule("anyRequest", List.of(), "permitAll")),
                List.of("csrf")
        );

        List<SecurityPolicyChange> changes = comparator.compare(List.of(before), List.of(after));

        assertEquals(1, changes.size());
        assertEquals(SecurityPolicyChangeKind.SECURITY_POLICY_CHANGED, changes.get(0).kind());
        assertEquals(before, changes.get(0).before());
        assertEquals(after, changes.get(0).after());
    }
}
