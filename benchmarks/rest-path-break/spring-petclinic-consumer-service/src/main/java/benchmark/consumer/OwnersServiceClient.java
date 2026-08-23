package benchmark.consumer;

public final class OwnersServiceClient {

    public String getOwnerUri(int ownerId) {
        return new RequestBuilder()
                .get()
                .uri("http://provider-service/owners/{ownerId}", ownerId);
    }

    private static final class RequestBuilder {
        private RequestBuilder get() {
            return this;
        }

        private String uri(String template, int ownerId) {
            return template.replace("{ownerId}", Integer.toString(ownerId));
        }
    }
}
