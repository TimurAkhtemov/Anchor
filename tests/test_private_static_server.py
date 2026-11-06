import http.client
import threading

import pytest

from scripts.private_static_server import make_server


@pytest.fixture
def serve(tmp_path):
    servers = []

    def start(directory):
        server = make_server(0, str(directory))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        return server

    yield start
    for server in servers:
        server.shutdown()
        server.server_close()


def _get(server, host=None, path="/"):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    conn.putrequest("GET", path, skip_host=True)
    if host is not None:
        conn.putheader("Host", host)
    conn.endheaders()
    response = conn.getresponse()
    body = response.read()
    conn.close()
    return response.status, body


def _site(tmp_path):
    (tmp_path / "current").mkdir()
    (tmp_path / "current" / "index.html").write_text("private home")
    return tmp_path / "current"


def test_allowed_hosts_are_served_and_follow_the_port(serve, tmp_path):
    server = serve(_site(tmp_path))
    port = server.server_port
    assert server.server_address[0] == "127.0.0.1"
    assert _get(server, f"127.0.0.1:{port}") == (200, b"private home")
    assert _get(server, f"localhost:{port}") == (200, b"private home")


@pytest.mark.parametrize(
    "host", ["evil.example", "evil.example:{port}", "127.0.0.1", "localhost:1", None]
)
def test_other_hosts_get_403(serve, tmp_path, host):
    server = serve(_site(tmp_path))
    if host:
        host = host.format(port=server.server_port)
    status, body = _get(server, host)
    assert status == 403
    assert b"private home" not in body


def test_missing_directory_is_404_and_server_survives(serve, tmp_path):
    server = serve(tmp_path / "current")
    host = f"127.0.0.1:{server.server_port}"
    assert _get(server, host)[0] == 404
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "index.html").write_text("later")
    (tmp_path / "current").symlink_to("build")  # symlink swap, no restart
    assert _get(server, host) == (200, b"later")
