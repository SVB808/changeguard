package benchmark.feign;

import benchmark.provider.OrderResource;
import org.junit.jupiter.api.Test;

import java.lang.reflect.Method;

import static org.junit.jupiter.api.Assertions.assertTrue;

class FeignOrderContractTest {

    @Test
    void declaredFeignRouteIsStillServedByProvider() throws Exception {
        RequestMapping base = OrdersFeign.class.getAnnotation(RequestMapping.class);
        Method getOrder = OrdersFeign.class.getDeclaredMethod("getOrder", int.class);
        GetMapping method = getOrder.getAnnotation(GetMapping.class);
        String path = (base.value() + method.value()).replace("{orderId}", "42");

        assertTrue(
                OrderResource.serves("GET", path),
                () -> "provider no longer serves Feign route " + path
        );
    }
}
