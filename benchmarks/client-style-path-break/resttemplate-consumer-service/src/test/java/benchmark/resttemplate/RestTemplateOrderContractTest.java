package benchmark.resttemplate;

import benchmark.provider.OrderResource;
import org.junit.jupiter.api.Test;

import java.net.URI;

import static org.junit.jupiter.api.Assertions.assertTrue;

class RestTemplateOrderContractTest {

    @Test
    void literalRestTemplateRouteIsStillServedByProvider() {
        String uri = new OrdersRestTemplateClient().getOrderUri(42);
        String path = URI.create(uri).getPath();

        assertTrue(
                OrderResource.serves("GET", path),
                () -> "provider no longer serves RestTemplate route " + path
        );
    }
}
