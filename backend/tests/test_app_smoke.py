import os

EXPECTED_PREFIXES = [
    "/api/auth",
    "/api/upload",
    "/api/submissions",
    "/api/projects",
    "/api/schools",
    "/api/teams",
    "/api/gold-division",
    "/api/eagle",
    "/api/error",
]


def test_app_factory_builds(app):
    assert app.name == "app"
    assert app.config["SQLALCHEMY_DATABASE_URI"].startswith("mysql+pymysql://")


def test_blueprints_registered(app):
    rules = [rule.rule for rule in app.url_map.iter_rules()]
    for prefix in EXPECTED_PREFIXES:
        assert any(rule.startswith(prefix + "/") for rule in rules), f"no routes under {prefix}"


def test_file_dirs_created(app):
    assert os.path.isdir(app.config["TEACHER_FILES_DIR"])
    assert os.path.isdir(app.config["STUDENT_FILES_DIR"])


def test_unknown_route_is_404(client):
    assert client.get("/api/does-not-exist").status_code == 404


def test_protected_endpoint_requires_jwt(client):
    response = client.get("/api/schools/config/divisions")
    assert response.status_code == 401
    assert response.is_json


def test_scoreboard_job_scheduled(app):
    from src.extensions import scheduler

    assert scheduler.get_job("scoreboard_snapshot_job") is not None
