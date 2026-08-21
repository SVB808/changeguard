package benchmark.feign;

@FeignClient(name = "provider-service")
@RequestMapping("/orders")
public interface OrdersFeign {

    @GetMapping("/{orderId}")
    String getOrder(int orderId);
}
