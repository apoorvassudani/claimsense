"""Production entry point: API under /api, React app (with deep links) everywhere else."""
import importlib

from fastapi.testclient import TestClient


def test_one_server_for_api_and_frontend(tmp_path, monkeypatch):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<title>ClaimSense</title>")
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    monkeypatch.setenv("FRONTEND_DIST", str(tmp_path))
    import app.serve as serve
    importlib.reload(serve)
    with TestClient(serve.root) as c:
        assert "ClaimSense" in c.get("/").text
        assert "ClaimSense" in c.get("/claims/12").text            # React route survives a refresh
        assert c.get("/assets/app.js").status_code == 200
        assert c.get("/health").json() == {"status": "ok"}
        assert c.get("/api/health").json()["status"] == "ok"
        assert c.get("/api/claims").status_code == 401             # API still needs sign-in
        assert "root:" not in c.get("/..%2F..%2Fetc%2Fpasswd").text  # no files outside dist
