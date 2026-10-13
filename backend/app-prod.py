"""
This is our main file for our application, from here everything else is called
"""

from container import Container
from datetime import timedelta
from flask import Flask
from flask_cors import CORS
from src.auth import auth_api
from src.repositories.database import db
from src.upload import upload_api
from src.submission import submission_api
from src.projects import projects_api
from src.schools import school_api
from src.teams import team_api
from src.gold_division import gold_division_api
from src.error import error_api
from src.jwt_manager import jwt
from src import teams, schools, auth, projects, submission, upload
from src.services import timeout_service
from src import teams, schools, auth, projects, submission, upload, timeout_service, gold_division, eagle_home
import os
from src.jobs.scoreboard_job import add_scoreboard_job
from src.extensions import cache, scheduler
from src.config import database_uri, require_env

def create_app():
    jwt_secret_key = require_env("JWT_SECRET_KEY")
    sqlalchemy_uri = database_uri()

    app = Flask(__name__)
    container = Container()
    app.container = container
    container.wire(modules=[teams, schools, auth, projects, submission, upload, timeout_service, gold_division, eagle_home])

    TEACHER_DIR = "/tabot-files/project-files/teacher-files"
    STUDENT_DIR = "/tabot-files/project-files/student-files"
    os.makedirs(TEACHER_DIR, exist_ok=True)
    os.makedirs(STUDENT_DIR, exist_ok=True)
    app.config.update({
        'TEACHER_FILES_DIR': TEACHER_DIR,
        'STUDENT_FILES_DIR': STUDENT_DIR,
    })

    CORS(app)
    app.config["JWT_SECRET_KEY"] = jwt_secret_key
    app.config["MAX_FAILED_LOGINS"] = 5
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1000 * 1000
    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=1)
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_DATABASE_URI"] = sqlalchemy_uri
    app.register_blueprint(auth_api, url_prefix='/api/auth')
    app.register_blueprint(upload_api, url_prefix='/api/upload')
    app.register_blueprint(submission_api, url_prefix='/api/submissions')
    app.register_blueprint(projects_api,url_prefix='/api/projects')  
    app.register_blueprint(school_api, url_prefix='/api/schools')
    app.register_blueprint(team_api, url_prefix='/api/teams')
    app.register_blueprint(gold_division_api, url_prefix='/api/gold-division')
    app.register_blueprint(eagle_home.eagle_api, url_prefix='/api/eagle')
    app.register_blueprint(error_api,url_prefix='/api/error')

    jwt.init_app(app)
    db.init_app(app)

    # Cache setup
    cache.init_app(app, config={
        'CACHE_TYPE': 'SimpleCache',
        'CACHE_DEFAULT_TIMEOUT': 60,
    })

    if scheduler.get_job("scoreboard_snapshot_job") is None:
        add_scoreboard_job(scheduler, app)

    if not scheduler.running:
        scheduler.start()

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, port=5000)
