package benchmark.provider;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface RestController {
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface RequestMapping {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface GetMapping {
    String value();
}

@RestController
@RequestMapping("/customers")
public final class OwnerResource {

    @GetMapping("/{ownerId}")
    public String findOwner(int ownerId) {
        return "owner-" + ownerId;
    }

    public static boolean serves(String httpMethod, String path) {
        return "GET".equals(httpMethod) && path.matches("/customers/\\d+");
    }
}
