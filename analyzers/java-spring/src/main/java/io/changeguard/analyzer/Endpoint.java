package io.changeguard.analyzer;

import java.util.List;

public record Endpoint(
        String controller,
        String methodName,
        String httpMethod,
        String path,
        String returnType,
        List<String> parameterTypes
) {
    public String methodIdentity() {
        return controller + "#" + methodName;
    }
}
