package io.changeguard.analyzer;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class SecurityPolicyComparator {

    public List<SecurityPolicyChange> compare(List<SecurityPolicy> before, List<SecurityPolicy> after) {
        Map<String, SecurityPolicy> beforeByIdentity = index(before);
        Map<String, SecurityPolicy> afterByIdentity = index(after);
        List<SecurityPolicyChange> changes = new ArrayList<>();

        List<String> identities = new ArrayList<>(beforeByIdentity.keySet());
        for (String identity : afterByIdentity.keySet()) {
            if (!identities.contains(identity)) {
                identities.add(identity);
            }
        }

        for (String identity : identities) {
            SecurityPolicy oldPolicy = beforeByIdentity.get(identity);
            SecurityPolicy newPolicy = afterByIdentity.get(identity);

            if (oldPolicy == null) {
                changes.add(new SecurityPolicyChange(
                        SecurityPolicyChangeKind.SECURITY_POLICY_ADDED,
                        null,
                        newPolicy
                ));
            } else if (newPolicy == null) {
                changes.add(new SecurityPolicyChange(
                        SecurityPolicyChangeKind.SECURITY_POLICY_REMOVED,
                        oldPolicy,
                        null
                ));
            } else if (!oldPolicy.equals(newPolicy)) {
                changes.add(new SecurityPolicyChange(
                        SecurityPolicyChangeKind.SECURITY_POLICY_CHANGED,
                        oldPolicy,
                        newPolicy
                ));
            }
        }

        return List.copyOf(changes);
    }

    private Map<String, SecurityPolicy> index(List<SecurityPolicy> policies) {
        Map<String, SecurityPolicy> indexed = new LinkedHashMap<>();
        for (SecurityPolicy policy : policies) {
            indexed.put(policy.methodIdentity(), policy);
        }
        return indexed;
    }
}
