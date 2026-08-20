from changeguard.models import ChangeManifest


def test_changed_file_count():
    manifest = ChangeManifest(
        repo="/tmp/example",
        base="main",
        head="feature",
        files=[],
    )

    assert manifest.changed_file_count == 0
