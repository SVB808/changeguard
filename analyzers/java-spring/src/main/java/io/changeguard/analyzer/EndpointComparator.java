package io.changeguard.analyzer;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class EndpointComparator {

    public AnalysisResult compare(List<Endpoint> before, List<Endpoint> after) {
        Map<String, List<Endpoint>> beforeByMethod = groupByMethod(before);
        Map<String, List<Endpoint>> afterByMethod = groupByMethod(after);
        List<EndpointChange> changes = new ArrayList<>();

        List<String> identities = new ArrayList<>();
        identities.addAll(beforeByMethod.keySet());
        for (String identity : afterByMethod.keySet()) {
            if (!identities.contains(identity)) {
                identities.add(identity);
            }
        }

        for (String identity : identities) {
            List<Endpoint> oldEndpoints = beforeByMethod.getOrDefault(identity, List.of());
            List<Endpoint> newEndpoints = afterByMethod.getOrDefault(identity, List.of());

            if (oldEndpoints.isEmpty()) {
                for (Endpoint endpoint : newEndpoints) {
                    changes.add(new EndpointChange(EndpointChangeKind.ENDPOINT_ADDED, null, endpoint));
                }
                continue;
            }

            if (newEndpoints.isEmpty()) {
                for (Endpoint endpoint : oldEndpoints) {
                    changes.add(new EndpointChange(EndpointChangeKind.ENDPOINT_REMOVED, endpoint, null));
                }
                continue;
            }

            if (oldEndpoints.size() == 1 && newEndpoints.size() == 1) {
                compareSingle(oldEndpoints.get(0), newEndpoints.get(0), changes);
                continue;
            }

            compareMultiple(oldEndpoints, newEndpoints, changes);
        }

        return new AnalysisResult(
                List.copyOf(before),
                List.copyOf(after),
                List.copyOf(changes),
                List.of(),
                List.of(),
                List.of()
        );
    }

    private void compareSingle(Endpoint before, Endpoint after, List<EndpointChange> changes) {
        if (!before.path().equals(after.path())) {
            changes.add(new EndpointChange(EndpointChangeKind.ENDPOINT_PATH_CHANGED, before, after));
        }
        if (!before.httpMethod().equals(after.httpMethod())) {
            changes.add(new EndpointChange(EndpointChangeKind.ENDPOINT_METHOD_CHANGED, before, after));
        }
        if (!before.parameterTypes().equals(after.parameterTypes())) {
            changes.add(new EndpointChange(EndpointChangeKind.REQUEST_SIGNATURE_CHANGED, before, after));
        }
        if (!before.returnType().equals(after.returnType())) {
            changes.add(new EndpointChange(EndpointChangeKind.RESPONSE_TYPE_CHANGED, before, after));
        }
    }

    private void compareMultiple(
            List<Endpoint> before,
            List<Endpoint> after,
            List<EndpointChange> changes
    ) {
        List<Endpoint> unmatchedAfter = new ArrayList<>(after);

        for (Endpoint oldEndpoint : before) {
            int exactIndex = unmatchedAfter.indexOf(oldEndpoint);
            if (exactIndex >= 0) {
                unmatchedAfter.remove(exactIndex);
            } else {
                changes.add(new EndpointChange(EndpointChangeKind.ENDPOINT_REMOVED, oldEndpoint, null));
            }
        }

        for (Endpoint newEndpoint : unmatchedAfter) {
            changes.add(new EndpointChange(EndpointChangeKind.ENDPOINT_ADDED, null, newEndpoint));
        }
    }

    private Map<String, List<Endpoint>> groupByMethod(List<Endpoint> endpoints) {
        Map<String, List<Endpoint>> grouped = new LinkedHashMap<>();
        for (Endpoint endpoint : endpoints) {
            grouped.computeIfAbsent(endpoint.methodIdentity(), ignored -> new ArrayList<>()).add(endpoint);
        }
        return grouped;
    }
}
