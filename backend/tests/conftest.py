import os

import pytest

_TEST_ENV = {
    "PASSWORD_TOKEN_SALT": "ci-test-salt",
    "PASSWORD_TOKEN_MAX_AGE_SECONDS": "3600",
    "FRONTEND_BASE_URL": "http://localhost:3000",
    "DB_USER": "user",
    "DB_PASSWORD": "password",
    "DB_HOST": "127.0.0.1",
    "DB_NAME": "autota",
}
for _key, _value in _TEST_ENV.items():
    os.environ.setdefault(_key, _value)



@pytest.fixture(scope="session")
def app():
    from app import create_app
    from src.extensions import scheduler

    application = create_app()
    application.config["TESTING"] = True
    yield application

    if scheduler.running:
        scheduler.shutdown(wait=False)


@pytest.fixture()
def client(app):
    return app.test_client()
