from __future__ import annotations

from changeguard.classifier import classify
from changeguard.dependency_graph import ServiceDependencyGraphBuilder
from changeguard.git_client import RawGitChange
from changeguard.github_client import GitHubAPIError, GitHubChangedFile, GitHubClient
from changeguard.impact_analysis import generate_impact_candidates, refine_impact_candidates
from changeguard.java_analyzer import JavaSpringAnalyzer
from changeguard.maven_layout import MavenBuildLayoutBuilder
from changeguard.models import ChangeManifest, FileChange, ServiceDependencyGraph
from changeguard.verification import build_verification_plans


GITHUB_STATUS_TO_GIT = {
    "added": "A",
    "modified": "M",
    "removed": "D",
    "renamed": "R100",
    "copied": "C100",
    "changed": "M",
    "unchanged": "M",
}


def scan_pull_request(
    repo_full_name: str,
    pr_number: int,
    client: GitHubClient | None = None,
    semantic_analyzer: JavaSpringAnalyzer | None = None,
    semantic_analysis: bool = False,
    dependency_graph_builder: ServiceDependencyGraphBuilder | None = None,
    dependency_analysis: bool = False,
    impact_analysis: bool = False,
    verification_planning: bool = False,
    maven_layout_builder: MavenBuildLayoutBuilder | None = None,
) -> ChangeManifest:
    client = client or GitHubClient()
    pull_request = client.get_pull_request(repo_full_name, pr_number)

    run_impact_analysis = impact_analysis or verification_planning
    run_semantic_analysis = semantic_analysis or run_impact_analysis
    run_dependency_analysis = dependency_analysis or run_impact_analysis

    analyzer = semantic_analyzer
    if run_semantic_analysis and analyzer is None:
        analyzer = JavaSpringAnalyzer()

    files: list[FileChange] = []
    for remote_file in pull_request.files:
        change = RawGitChange(
            status_token=GITHUB_STATUS_TO_GIT.get(remote_file.status, "M"),
            path=remote_file.filename,
            old_path=remote_file.previous_filename,
        )
        classified = classify(change, remote_file.patch or "")

        if run_semantic_analysis and classified.language == "java":
            assert analyzer is not None
            before_source, after_source = _load_java_versions(
                client=client,
                repo_full_name=pull_request.repo_full_name,
                remote_file=remote_file,
                base_sha=pull_request.base_sha,
                head_sha=pull_request.head_sha,
            )
            analysis = analyzer.analyze_sources(before_source, after_source)
            classified.semantic_changes.extend(analysis.endpoint_changes)
            classified.security_changes.extend(analysis.security_changes)

        files.append(classified)

    dependency_graph: ServiceDependencyGraph | None = None
    if run_dependency_analysis:
        builder = dependency_graph_builder or ServiceDependencyGraphBuilder(client=client)
        dependency_graph = builder.build(
            pull_request.repo_full_name,
            pull_request.head_sha,
        )
        _attach_dependency_context(files, dependency_graph)

    impact_candidates = []
    suppressed_impact_candidates = []
    if run_impact_analysis and dependency_graph is not None:
        service_candidates = generate_impact_candidates(files, dependency_graph)
        impact_candidates, suppressed_impact_candidates = refine_impact_candidates(
            service_candidates,
            dependency_graph,
        )

    verification_plans = []
    if verification_planning and dependency_graph is not None:
        module_layout = {}
        if maven_layout_builder is not None:
            module_layout = maven_layout_builder.build(
                pull_request.repo_full_name,
                pull_request.head_sha,
            )
        elif hasattr(client, "list_repository_paths"):
            module_layout = MavenBuildLayoutBuilder(client=client).build(
                pull_request.repo_full_name,
                pull_request.head_sha,
            )

        verification_plans = build_verification_plans(
            impact_candidates,
            dependency_graph,
            module_layout=module_layout,
        )

    return ChangeManifest(
        repo=pull_request.repo_full_name,
        base=pull_request.base_sha,
        head=pull_request.head_sha,
        files=files,
        dependency_graph=dependency_graph,
        impact_analysis_enabled=run_impact_analysis,
        impact_candidates=impact_candidates,
        suppressed_impact_candidates=suppressed_impact_candidates,
        verification_planning_enabled=verification_planning,
        verification_plans=verification_plans,
    )


def _attach_dependency_context(
    files: list[FileChange],
    graph: ServiceDependencyGraph,
) -> None:
    for file in files:
        node = graph.node_for_path(file.path)
        if node is None:
            continue
        file.service = node.name
        file.service_module = node.module_path
        file.direct_dependents = [
            dependent.name for dependent in graph.direct_dependent_nodes(node)
        ]


def _load_java_versions(
    client: GitHubClient,
    repo_full_name: str,
    remote_file: GitHubChangedFile,
    base_sha: str,
    head_sha: str,
) -> tuple[str, str]:
    before_path = remote_file.previous_filename or remote_file.filename

    if remote_file.status == "added":
        before_source = ""
    else:
        before_source = client.get_file_text(repo_full_name, before_path, base_sha)
        if before_source is None:
            raise GitHubAPIError(
                f"Could not load base source for {before_path} at {base_sha[:12]}"
            )

    if remote_file.status == "removed":
        after_source = ""
    else:
        after_source = client.get_file_text(
            repo_full_name,
            remote_file.filename,
            head_sha,
        )
        if after_source is None:
            raise GitHubAPIError(
                f"Could not load head source for {remote_file.filename} "
                f"at {head_sha[:12]}"
            )

    return before_source, after_source
