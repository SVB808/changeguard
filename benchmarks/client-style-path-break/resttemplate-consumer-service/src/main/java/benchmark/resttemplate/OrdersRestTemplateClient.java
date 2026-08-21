package benchmark.resttemplate;

public final class OrdersRestTemplateClient {

    private final FakeRestTemplate restTemplate = new FakeRestTemplate();

    public String getOrderUri(int orderId) {
        return restTemplate.getForEntity(
                "http://provider-service/orders/{orderId}",
                String.class,
                orderId
        );
    }

    private static final class FakeRestTemplate {
        private String getForEntity(String template, Class<?> responseType, int orderId) {
            return template.replace("{orderId}", Integer.toString(orderId));
        }
    }
}
