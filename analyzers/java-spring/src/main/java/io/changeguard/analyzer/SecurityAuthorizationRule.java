package io.changeguard.analyzer;

import java.util.List;

public record SecurityAuthorizationRule(
        String selector,
        List<String> patterns,
        String action
) {
}
