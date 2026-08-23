package io.changeguard.analyzer;

public record EndpointChange(
        EndpointChangeKind kind,
        Endpoint before,
        Endpoint after
) {
}
