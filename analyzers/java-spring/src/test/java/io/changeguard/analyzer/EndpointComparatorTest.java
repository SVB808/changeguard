package io.changeguard.analyzer;

import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class EndpointComparatorTest {

    private final SpringEndpointExtractor extractor = new SpringEndpointExtractor();
    private final EndpointComparator comparator = new EndpointComparator();

    @Test
    void detectsAddedEndpointFromPetclinicShape() {
        String before = """
                import java.util.List;
                import org.springframework.web.bind.annotation.GetMapping;
                import org.springframework.web.bind.annotation.RequestMapping;
                import org.springframework.web.bind.annotation.RestController;

                @RequestMapping("/vets")
                @RestController
                class VetResource {
                    @GetMapping
                    public List<String> showResourcesVetList() {
                        return List.of();
                    }
                }
                """;

        String after = """
                import java.util.List;
                import org.springframework.web.bind.annotation.GetMapping;
                import org.springframework.web.bind.annotation.RequestMapping;
                import org.springframework.web.bind.annotation.RestController;

                @RequestMapping("/vets")
                @RestController
                class VetResource {
                    @GetMapping
                    public List<String> showResourcesVetList() {
                        return List.of();
                    }

                    @GetMapping("/health")
                    public String health() {
                        return "UP";
                    }
                }
                """;

        AnalysisResult result = comparator.compare(extractor.extract(before), extractor.extract(after));

        assertEquals(1, result.changes().size());
        EndpointChange change = result.changes().get(0);
        assertEquals(EndpointChangeKind.ENDPOINT_ADDED, change.kind());
        assertEquals("GET", change.after().httpMethod());
        assertEquals("/vets/health", change.after().path());
    }

    @Test
    void detectsPathAndResponseTypeChangesWithoutCallingThemAddRemove() {
        Endpoint before = new Endpoint(
                "OwnerResource",
                "findOwner",
                "GET",
                "/owners/{id}",
                "Owner",
                List.of("long")
        );
        Endpoint after = new Endpoint(
                "OwnerResource",
                "findOwner",
                "GET",
                "/owners/{ownerId}",
                "OwnerResponse",
                List.of("long")
        );

        AnalysisResult result = comparator.compare(List.of(before), List.of(after));

        assertEquals(2, result.changes().size());
        assertTrue(result.changes().stream()
                .anyMatch(change -> change.kind() == EndpointChangeKind.ENDPOINT_PATH_CHANGED));
        assertTrue(result.changes().stream()
                .anyMatch(change -> change.kind() == EndpointChangeKind.RESPONSE_TYPE_CHANGED));
    }

    @Test
    void detectsHttpMethodAndRequestSignatureChanges() {
        Endpoint before = new Endpoint(
                "OwnerResource",
                "updateOwner",
                "PUT",
                "/owners/{id}",
                "OwnerResponse",
                List.of("long", "OwnerRequest")
        );
        Endpoint after = new Endpoint(
                "OwnerResource",
                "updateOwner",
                "PATCH",
                "/owners/{id}",
                "OwnerResponse",
                List.of("String", "OwnerPatchRequest")
        );

        AnalysisResult result = comparator.compare(List.of(before), List.of(after));

        assertEquals(2, result.changes().size());
        assertTrue(result.changes().stream()
                .anyMatch(change -> change.kind() == EndpointChangeKind.ENDPOINT_METHOD_CHANGED));
        assertTrue(result.changes().stream()
                .anyMatch(change -> change.kind() == EndpointChangeKind.REQUEST_SIGNATURE_CHANGED));
    }
}
