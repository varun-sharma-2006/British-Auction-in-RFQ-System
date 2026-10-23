"""Single-container mode: the API also serves the built frontend."""
import pytest

from app import main


@pytest.fixture(scope="module")
def dist(tmp_path_factory):
    d = tmp_path_factory.mktemp("dist")
    (d / "assets").mkdir()
    (d / "index.html").write_text("<!doctype html><title>SPA</title>")
    (d / "favicon.svg").write_text("<svg/>")
    (d / "assets" / "app.js").write_text("console.log(1)")
    (d.parent / "secret.txt").write_text("outside dist")
    main.mount_frontend(d)
    return d


def test_serves_index_for_client_routes_and_real_files(client, dist):
    for path in ("/", "/rfqs/12", "/login"):
        res = client.get(path)
        assert res.status_code == 200 and "<title>SPA</title>" in res.text
    assert client.get("/favicon.svg").text == "<svg/>"
    assert client.get("/assets/app.js").text == "console.log(1)"


def test_api_routes_win_and_unknown_api_paths_404(client, dist):
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/api/nope").status_code == 404


def test_no_path_traversal(client, dist):
    res = client.get("/..%2Fsecret.txt")
    assert "outside dist" not in res.text
