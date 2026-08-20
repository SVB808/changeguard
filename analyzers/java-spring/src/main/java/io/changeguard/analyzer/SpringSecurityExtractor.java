package io.changeguard.analyzer;

import com.github.javaparser.StaticJavaParser;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.body.MethodDeclaration;
import com.github.javaparser.ast.expr.Expression;
import com.github.javaparser.ast.expr.MethodCallExpr;
import com.github.javaparser.ast.expr.StringLiteralExpr;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public final class SpringSecurityExtractor {

    private static final Set<String> SECURITY_CHAIN_TYPES = Set.of(
            "SecurityWebFilterChain",
            "SecurityFilterChain"
    );

    private static final Set<String> AUTHORIZATION_SELECTORS = Set.of(
            "anyExchange",
            "anyRequest",
            "pathMatchers",
            "requestMatchers"
    );

    private static final Set<String> AUTHORIZATION_ACTIONS = Set.of(
            "permitAll",
            "denyAll",
            "authenticated",
            "hasRole",
            "hasAuthority"
    );

    private static final Set<String> DISABLABLE_FEATURES = Set.of(
            "csrf",
            "cors",
            "httpBasic",
            "formLogin"
    );

    public List<SecurityPolicy> extract(String source) {
        if (source == null || source.isBlank()) {
            return List.of();
        }

        CompilationUnit unit = StaticJavaParser.parse(source);
        List<SecurityPolicy> policies = new ArrayList<>();

        for (MethodDeclaration method : unit.findAll(MethodDeclaration.class)) {
            String returnType = method.getType().asString();
            if (!SECURITY_CHAIN_TYPES.contains(returnType)) {
                continue;
            }

            LinkedHashSet<SecurityAuthorizationRule> authorizationRules = new LinkedHashSet<>();
            LinkedHashSet<String> disabledFeatures = new LinkedHashSet<>();

            for (MethodCallExpr call : method.findAll(MethodCallExpr.class)) {
                extractAuthorizationRule(call).ifPresent(authorizationRules::add);
                extractDisabledFeature(call).ifPresent(disabledFeatures::add);
            }

            policies.add(new SecurityPolicy(
                    returnType,
                    method.getNameAsString(),
                    List.copyOf(authorizationRules),
                    List.copyOf(disabledFeatures)
            ));
        }

        return List.copyOf(policies);
    }

    private java.util.Optional<SecurityAuthorizationRule> extractAuthorizationRule(MethodCallExpr call) {
        String actionName = call.getNameAsString();
        if (!AUTHORIZATION_ACTIONS.contains(actionName)) {
            return java.util.Optional.empty();
        }

        if (call.getScope().isEmpty() || !(call.getScope().get() instanceof MethodCallExpr selectorCall)) {
            return java.util.Optional.empty();
        }

        String selector = selectorCall.getNameAsString();
        if (!AUTHORIZATION_SELECTORS.contains(selector)) {
            return java.util.Optional.empty();
        }

        List<String> patterns = selectorCall.getArguments().stream()
                .filter(StringLiteralExpr.class::isInstance)
                .map(StringLiteralExpr.class::cast)
                .map(StringLiteralExpr::asString)
                .toList();

        return java.util.Optional.of(new SecurityAuthorizationRule(
                selector,
                patterns,
                actionLabel(call)
        ));
    }

    private String actionLabel(MethodCallExpr call) {
        String action = call.getNameAsString();
        if ((action.equals("hasRole") || action.equals("hasAuthority"))
                && !call.getArguments().isEmpty()) {
            Expression first = call.getArgument(0);
            if (first instanceof StringLiteralExpr literal) {
                return action + "(" + literal.asString() + ")";
            }
        }
        return action;
    }

    private java.util.Optional<String> extractDisabledFeature(MethodCallExpr call) {
        String callName = call.getNameAsString();

        if (DISABLABLE_FEATURES.contains(callName)
                && call.getArguments().stream().anyMatch(this::containsDisable)) {
            return java.util.Optional.of(callName);
        }

        if (callName.equals("disable")
                && call.getScope().isPresent()
                && call.getScope().get() instanceof MethodCallExpr featureCall
                && DISABLABLE_FEATURES.contains(featureCall.getNameAsString())) {
            return java.util.Optional.of(featureCall.getNameAsString());
        }

        return java.util.Optional.empty();
    }

    private boolean containsDisable(Expression expression) {
        return expression.toString().contains("disable");
    }
}
