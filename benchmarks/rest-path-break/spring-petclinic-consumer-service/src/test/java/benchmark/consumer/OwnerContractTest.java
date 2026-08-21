package benchmark.consumer;

import benchmark.provider.OwnerResource;
import org.junit.jupiter.api.Test;

import java.net.URI;

import static org.junit.jupiter.api.Assertions.assertTrue;

class OwnerContractTest {

    @Test
    void existingOwnerRouteIsStillServedByProvider() {
        String uri = new OwnersServiceClient().getOwnerUri(42);
        URI parsed = URI.create(uri);

        assertTrue(
                OwnerResource.serves("GET", parsed.getPath()),
                () -> "provider no longer serves consumer route " + parsed.getPath()
        );
    }
}
