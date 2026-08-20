package io.changeguard.analyzer;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public final class Main {

    private Main() {
    }

    public static void main(String[] args) throws Exception {
        Map<String, String> options = parseArgs(args);

        if (!options.containsKey("before") && !options.containsKey("after")) {
            System.err.println("Usage: java -jar changeguard-java-analyzer.jar --before <file> --after <file> [--pretty]");
            System.exit(2);
        }

        String beforeSource = readOptional(options.get("before"));
        String afterSource = readOptional(options.get("after"));

        SpringEndpointExtractor extractor = new SpringEndpointExtractor();
        List<Endpoint> before = extractor.extract(beforeSource);
        List<Endpoint> after = extractor.extract(afterSource);

        AnalysisResult result = new EndpointComparator().compare(before, after);

        ObjectMapper mapper = new ObjectMapper();
        if (options.containsKey("pretty")) {
            mapper.enable(SerializationFeature.INDENT_OUTPUT);
        }
        System.out.println(mapper.writeValueAsString(result));
    }

    private static String readOptional(String path) throws Exception {
        if (path == null) {
            return "";
        }
        return Files.readString(Path.of(path), StandardCharsets.UTF_8);
    }

    private static Map<String, String> parseArgs(String[] args) {
        Map<String, String> options = new HashMap<>();

        for (int index = 0; index < args.length; index++) {
            String arg = args[index];
            switch (arg) {
                case "--before", "--after" -> {
                    if (index + 1 >= args.length) {
                        throw new IllegalArgumentException(arg + " requires a path");
                    }
                    options.put(arg.substring(2), args[++index]);
                }
                case "--pretty" -> options.put("pretty", "true");
                default -> throw new IllegalArgumentException("Unknown argument: " + arg);
            }
        }

        return options;
    }
}
