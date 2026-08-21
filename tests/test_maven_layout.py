from changeguard.maven_layout import MavenBuildLayoutBuilder


class ReactorClient:
    paths = [
        "benchmarks/client-style-path-break/pom.xml",
        "benchmarks/client-style-path-break/provider-service/pom.xml",
        "benchmarks/client-style-path-break/feign-consumer-service/pom.xml",
        "benchmarks/client-style-path-break/resttemplate-consumer-service/pom.xml",
        "standalone-service/pom.xml",
    ]
    contents = {
        "benchmarks/client-style-path-break/pom.xml": """
            <project xmlns="http://maven.apache.org/POM/4.0.0">
              <modelVersion>4.0.0</modelVersion>
              <modules>
                <module>provider-service</module>
                <module>feign-consumer-service</module>
                <module>resttemplate-consumer-service</module>
              </modules>
            </project>
        """,
        "benchmarks/client-style-path-break/provider-service/pom.xml": "<project />",
        "benchmarks/client-style-path-break/feign-consumer-service/pom.xml": "<project />",
        "benchmarks/client-style-path-break/resttemplate-consumer-service/pom.xml": "<project />",
        "standalone-service/pom.xml": "<project />",
    }

    def list_repository_paths(self, repo_full_name: str, ref: str) -> list[str]:
        assert repo_full_name == "acme/changeguard"
        assert ref == "abc123"
        return self.paths

    def get_file_text(self, repo_full_name: str, path: str, ref: str) -> str | None:
        return self.contents.get(path)


class NestedReactorClient:
    paths = [
        "pom.xml",
        "platform/pom.xml",
        "platform/orders-service/pom.xml",
    ]
    contents = {
        "pom.xml": """
            <project>
              <modules><module>platform</module></modules>
            </project>
        """,
        "platform/pom.xml": """
            <project>
              <modules><module>orders-service</module></modules>
            </project>
        """,
        "platform/orders-service/pom.xml": "<project />",
    }

    def list_repository_paths(self, repo_full_name: str, ref: str) -> list[str]:
        return self.paths

    def get_file_text(self, repo_full_name: str, path: str, ref: str) -> str | None:
        return self.contents.get(path)


def test_discovers_nested_benchmark_reactor_and_relative_module_selector():
    layouts = MavenBuildLayoutBuilder(client=ReactorClient()).build(
        "acme/changeguard",
        "abc123",
    )

    layout = layouts["benchmarks/client-style-path-break/feign-consumer-service"]
    assert layout.build_root == "benchmarks/client-style-path-break"
    assert layout.build_pom == "benchmarks/client-style-path-break/pom.xml"
    assert layout.module_selector == "feign-consumer-service"
    assert layout.evidence_paths == ("benchmarks/client-style-path-break/pom.xml",)


def test_standalone_module_uses_its_own_pom_without_project_list_selector():
    layouts = MavenBuildLayoutBuilder(client=ReactorClient()).build(
        "acme/changeguard",
        "abc123",
    )

    layout = layouts["standalone-service"]
    assert layout.build_root == "standalone-service"
    assert layout.build_pom == "standalone-service/pom.xml"
    assert layout.module_selector is None
    assert layout.evidence_paths == ("standalone-service/pom.xml",)


def test_walks_transitive_module_declarations_to_topmost_reactor_root():
    layouts = MavenBuildLayoutBuilder(client=NestedReactorClient()).build(
        "acme/platform",
        "head",
    )

    layout = layouts["platform/orders-service"]
    assert layout.build_root == ""
    assert layout.build_pom == "pom.xml"
    assert layout.module_selector == "platform/orders-service"
    assert layout.evidence_paths == ("platform/pom.xml", "pom.xml")
