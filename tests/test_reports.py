"""Reports: choose parts from a list, get a PDF, find it again; ownership and admin-only parts."""
import pytest
from fastapi.testclient import TestClient
import main
from tests.test_region import user, admin


def test_catalog_hides_admin_parts_from_users_and_shows_them_to_admins():
    with TestClient(main.app) as c:
        user(c, "rep1@example.com")
        ids = [i["id"] for g in c.get("/api/reports/catalog").json()["groups"] for i in g["items"]]
        assert "cube" in ids and "star" in ids and "a_users" not in ids
        assert c.post("/api/reports/generate", json={"sections": ["a_users"]}, headers={"X-Requested-With": "fetch"}).status_code == 400
    with TestClient(main.app) as a:
        admin(a)
        ids = [i["id"] for g in a.get("/api/reports/catalog").json()["groups"] for i in g["items"]]
        assert "a_users" in ids


def test_generate_download_history_and_delete_pdf():
    H = {"X-Requested-With": "fetch"}
    with TestClient(main.app) as c:
        user(c, "rep2@example.com")
        r = c.post("/api/reports/generate", json={"sections": ["kpis", "star", "cube", "hours", "etl"], "title": "My demo"}, headers=H)
        assert r.status_code == 200, r.text
        rep = r.json(); assert rep["pages"] >= 1 and rep["bytes"] > 2000
        pdf = c.get(f"/api/reports/{rep['id']}/download"); assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
        h = c.get("/api/reports/history").json(); assert h and h[0]["title"] == "My demo" and "Star schema" in h[0]["sections"]
        assert c.post("/api/reports/generate", json={"sections": []}, headers=H).status_code == 422
        assert c.post("/api/reports/generate", json={"sections": ["nope"]}, headers=H).status_code == 400
        # another user can not open it
        with TestClient(main.app) as c2:
            user(c2, "rep3@example.com")
            assert c2.get(f"/api/reports/{rep['id']}/download").status_code == 404 and c2.delete(f"/api/reports/{rep['id']}", headers=H).status_code == 404
        assert c.delete(f"/api/reports/{rep['id']}", headers=H).status_code == 200
        assert c.get(f"/api/reports/{rep['id']}/download").status_code == 404


def test_every_part_in_the_list_draws_without_error():
    from app.routers import reports as R
    u = {"id": 1, "email": "a@b.c", "name": "Admin", "role": "admin"}
    data, pages = R.build_pdf(u, [c[0] for c in R.CATALOG], "all")
    assert data[:4] == b"%PDF" and pages >= 5 and b"could not be drawn" not in data
