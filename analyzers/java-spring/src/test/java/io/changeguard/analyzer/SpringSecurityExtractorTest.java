package io.changeguard.analyzer;

import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringSecurityExtractorTest {

    private final SpringSecurityExtractor extractor = new SpringSecurityExtractor();

    @Test
    void extractsWebFluxPermitAllAndDisabledFeaturesFromPetclinicShape() {
        String source = """
                import org.springframework.context.annotation.Bean;
                import org.springframework.security.config.web.server.ServerHttpSecurity;
                import org.springframework.security.web.server.SecurityWebFilterChain;

                class SecurityConfig {
                    @Bean
                    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
                        http
                            .authorizeExchange(exchanges -> exchanges
                                .anyExchange().permitAll())
                            .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
                            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                            .csrf(ServerHttpSecurity.CsrfSpec::disable)
                            .cors(ServerHttpSecurity.CorsSpec::disable);
                        return http.build();
                    }
                }
                """;

        List<SecurityPolicy> policies = extractor.extract(source);

        assertEquals(1, policies.size());
        SecurityPolicy policy = policies.get(0);
        assertEquals("SecurityWebFilterChain", policy.component());
        assertEquals("securityWebFilterChain", policy.methodName());
        assertEquals(
                List.of(new SecurityAuthorizationRule("anyExchange", List.of(), "permitAll")),
                policy.authorizationRules()
        );
        assertEquals(4, policy.disabledFeatures().size());
        assertTrue(policy.disabledFeatures().containsAll(
                List.of("httpBasic", "formLogin", "csrf", "cors")
        ));
    }

    @Test
    void extractsServletMatchersAndLambdaDisable() {
        String source = """
                import org.springframework.security.config.annotation.web.builders.HttpSecurity;
                import org.springframework.security.web.SecurityFilterChain;

                class SecurityConfig {
                    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
                        http
                            .authorizeHttpRequests(auth -> auth
                                .requestMatchers("/public", "/health").permitAll()
                                .anyRequest().authenticated())
                            .csrf(csrf -> csrf.disable());
                        return http.build();
                    }
                }
                """;

        SecurityPolicy policy = extractor.extract(source).get(0);

        assertEquals(2, policy.authorizationRules().size());
        assertTrue(policy.authorizationRules().contains(
                new SecurityAuthorizationRule(
                        "requestMatchers",
                        List.of("/public", "/health"),
                        "permitAll"
                )
        ));
        assertTrue(policy.authorizationRules().contains(
                new SecurityAuthorizationRule("anyRequest", List.of(), "authenticated")
        ));
        assertEquals(List.of("csrf"), policy.disabledFeatures());
    }
}
