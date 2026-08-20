package io.changeguard.analyzer;

import com.github.javaparser.StaticJavaParser;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;
import com.github.javaparser.ast.body.MethodDeclaration;
import com.github.javaparser.ast.expr.AnnotationExpr;
import com.github.javaparser.ast.expr.ArrayInitializerExpr;
import com.github.javaparser.ast.expr.Expression;
import com.github.javaparser.ast.expr.NormalAnnotationExpr;
import com.github.javaparser.ast.expr.SingleMemberAnnotationExpr;
import com.github.javaparser.ast.expr.StringLiteralExpr;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Optional;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public final class SpringEndpointExtractor {

    private static final Pattern REQUEST_METHOD_PATTERN = Pattern.compile("RequestMethod\\.([A-Z]+)");

    public List<Endpoint> extract(String source) {
        if (source == null || source.isBlank()) {
            return List.of();
        }

        CompilationUnit unit = StaticJavaParser.parse(source);
        List<Endpoint> endpoints = new ArrayList<>();

        for (ClassOrInterfaceDeclaration type : unit.findAll(ClassOrInterfaceDeclaration.class)) {
            if (!isSpringController(type)) {
                continue;
            }

            String classPath = firstPath(type.getAnnotationsByName("RequestMapping"));

            for (MethodDeclaration method : type.getMethods()) {
                for (Mapping mapping : mappingsFor(method)) {
                    for (String methodPath : mapping.paths()) {
                        endpoints.add(new Endpoint(
                                type.getNameAsString(),
                                method.getNameAsString(),
                                mapping.httpMethod(),
                                joinPaths(classPath, methodPath),
                                method.getType().asString(),
                                method.getParameters().stream()
                                        .map(parameter -> parameter.getType().asString())
                                        .toList()
                        ));
                    }
                }
            }
        }

        return endpoints;
    }

    private boolean isSpringController(ClassOrInterfaceDeclaration type) {
        return !type.getAnnotationsByName("RestController").isEmpty()
                || !type.getAnnotationsByName("Controller").isEmpty();
    }

    private List<Mapping> mappingsFor(MethodDeclaration method) {
        List<Mapping> mappings = new ArrayList<>();

        for (AnnotationExpr annotation : method.getAnnotations()) {
            String name = annotation.getName().getIdentifier();
            switch (name) {
                case "GetMapping" -> mappings.addAll(directMapping(annotation, "GET"));
                case "PostMapping" -> mappings.addAll(directMapping(annotation, "POST"));
                case "PutMapping" -> mappings.addAll(directMapping(annotation, "PUT"));
                case "PatchMapping" -> mappings.addAll(directMapping(annotation, "PATCH"));
                case "DeleteMapping" -> mappings.addAll(directMapping(annotation, "DELETE"));
                case "RequestMapping" -> mappings.addAll(requestMappings(annotation));
                default -> {
                    // Not a Spring request mapping annotation.
                }
            }
        }

        return mappings;
    }

    private List<Mapping> directMapping(AnnotationExpr annotation, String httpMethod) {
        List<String> paths = pathsFrom(annotation);
        if (paths.isEmpty()) {
            paths = List.of("");
        }
        return List.of(new Mapping(httpMethod, paths));
    }

    private List<Mapping> requestMappings(AnnotationExpr annotation) {
        List<String> paths = pathsFrom(annotation);
        if (paths.isEmpty()) {
            paths = List.of("");
        }

        List<String> methods = requestMethodsFrom(annotation);
        if (methods.isEmpty()) {
            methods = List.of("ANY");
        }

        List<Mapping> mappings = new ArrayList<>();
        for (String method : methods) {
            mappings.add(new Mapping(method, paths));
        }
        return mappings;
    }

    private List<String> pathsFrom(AnnotationExpr annotation) {
        if (annotation instanceof SingleMemberAnnotationExpr single) {
            return stringValues(single.getMemberValue());
        }

        if (annotation instanceof NormalAnnotationExpr normal) {
            Optional<Expression> path = normal.getPairs().stream()
                    .filter(pair -> pair.getNameAsString().equals("path"))
                    .map(pair -> pair.getValue())
                    .findFirst();

            if (path.isPresent()) {
                return stringValues(path.get());
            }

            return normal.getPairs().stream()
                    .filter(pair -> pair.getNameAsString().equals("value"))
                    .map(pair -> stringValues(pair.getValue()))
                    .findFirst()
                    .orElse(List.of());
        }

        return List.of();
    }

    private List<String> requestMethodsFrom(AnnotationExpr annotation) {
        if (!(annotation instanceof NormalAnnotationExpr normal)) {
            return List.of();
        }

        Optional<Expression> value = normal.getPairs().stream()
                .filter(pair -> pair.getNameAsString().equals("method"))
                .map(pair -> pair.getValue())
                .findFirst();

        if (value.isEmpty()) {
            return List.of();
        }

        List<String> methods = new ArrayList<>();
        Expression methodExpression = value.get();

        if (methodExpression instanceof ArrayInitializerExpr array) {
            for (Expression expression : array.getValues()) {
                addRequestMethod(expression, methods);
            }
        } else {
            addRequestMethod(methodExpression, methods);
        }

        return methods;
    }

    private void addRequestMethod(Expression expression, List<String> methods) {
        Matcher matcher = REQUEST_METHOD_PATTERN.matcher(expression.toString());
        if (matcher.find()) {
            methods.add(matcher.group(1).toUpperCase(Locale.ROOT));
        }
    }

    private List<String> stringValues(Expression expression) {
        if (expression instanceof StringLiteralExpr literal) {
            return List.of(literal.asString());
        }

        if (expression instanceof ArrayInitializerExpr array) {
            return array.getValues().stream()
                    .filter(StringLiteralExpr.class::isInstance)
                    .map(StringLiteralExpr.class::cast)
                    .map(StringLiteralExpr::asString)
                    .toList();
        }

        return List.of();
    }

    private String firstPath(List<AnnotationExpr> annotations) {
        if (annotations.isEmpty()) {
            return "";
        }

        List<String> paths = pathsFrom(annotations.get(0));
        return paths.isEmpty() ? "" : paths.get(0);
    }

    static String joinPaths(String classPath, String methodPath) {
        String left = normalizePart(classPath);
        String right = normalizePart(methodPath);

        if (left.isEmpty() && right.isEmpty()) {
            return "/";
        }
        if (left.isEmpty()) {
            return "/" + right;
        }
        if (right.isEmpty()) {
            return "/" + left;
        }
        return "/" + left + "/" + right;
    }

    private static String normalizePart(String value) {
        if (value == null || value.isBlank() || value.equals("/")) {
            return "";
        }
        return value.replaceAll("^/+|/+$", "");
    }

    private record Mapping(String httpMethod, List<String> paths) {
    }
}
