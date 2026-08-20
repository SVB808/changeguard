package io.changeguard.analyzer;

import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.assertEquals;

class SpringEndpointExtractorTest {

    private final SpringEndpointExtractor extractor = new SpringEndpointExtractor();

    @Test
    void combinesClassAndMethodMappings() {
        String source = """
                package example;

                import org.springframework.web.bind.annotation.GetMapping;
                import org.springframework.web.bind.annotation.RequestMapping;
                import org.springframework.web.bind.annotation.RestController;

                @RequestMapping("/vets")
                @RestController
                class VetResource {
                    @GetMapping("/health")
                    public String health() {
                        return "UP";
                    }
                }
                """;

        List<Endpoint> endpoints = extractor.extract(source);

        assertEquals(1, endpoints.size());
        Endpoint endpoint = endpoints.get(0);
        assertEquals("VetResource", endpoint.controller());
        assertEquals("health", endpoint.methodName());
        assertEquals("GET", endpoint.httpMethod());
        assertEquals("/vets/health", endpoint.path());
        assertEquals("String", endpoint.returnType());
        assertEquals(List.of(), endpoint.parameterTypes());
    }

    @Test
    void supportsRequestMappingMethodAttribute() {
        String source = """
                package example;

                import org.springframework.web.bind.annotation.RequestMapping;
                import org.springframework.web.bind.annotation.RequestMethod;
                import org.springframework.web.bind.annotation.RestController;

                @RestController
                class OwnerResource {
                    @RequestMapping(path = "/owners/{id}", method = RequestMethod.GET)
                    public String owner(long id) {
                        return "owner";
                    }
                }
                """;

        Endpoint endpoint = extractor.extract(source).get(0);

        assertEquals("GET", endpoint.httpMethod());
        assertEquals("/owners/{id}", endpoint.path());
        assertEquals(List.of("long"), endpoint.parameterTypes());
    }

    @Test
    void expandsMultipleClassAndMethodPaths() {
        String source = """
                package example;

                import org.springframework.web.bind.annotation.GetMapping;
                import org.springframework.web.bind.annotation.RequestMapping;
                import org.springframework.web.bind.annotation.RestController;

                @RequestMapping({"/v1", "/v2"})
                @RestController
                class OwnerResource {
                    @GetMapping(path = {"/owners", "/customers"})
                    public String list() {
                        return "ok";
                    }
                }
                """;

        Set<String> paths = extractor.extract(source).stream()
                .map(Endpoint::path)
                .collect(Collectors.toSet());

        assertEquals(Set.of(
                "/v1/owners",
                "/v1/customers",
                "/v2/owners",
                "/v2/customers"
        ), paths);
    }

    @Test
    void normalizesSlashesWhenCombiningMappings() {
        String source = """
                package example;

                import org.springframework.web.bind.annotation.GetMapping;
                import org.springframework.web.bind.annotation.RequestMapping;
                import org.springframework.web.bind.annotation.RestController;

                @RequestMapping("/api/")
                @RestController
                class HealthResource {
                    @GetMapping("/health/")
                    public String health() {
                        return "UP";
                    }
                }
                """;

        Endpoint endpoint = extractor.extract(source).get(0);

        assertEquals("/api/health", endpoint.path());
    }
}
