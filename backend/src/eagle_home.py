import os
from http import HTTPStatus

from dependency_injector.wiring import Provide, inject
from flask import Blueprint, jsonify, make_response, request, send_file
from flask_jwt_extended import current_user, jwt_required
from sqlalchemy import asc, desc

from container import Container
from src.constants import Division, can_student_access_competition_materials
from src.permissions import Actor, actor_of, can_view_eagle_chat, school_id_of
from src.repositories.database import db
from src.repositories.models import EagleTeamMessages, Teams
from src.repositories.project_repository import ProjectRepository

eagle_api = Blueprint("eagle_api", __name__)
NOT_EAGLE = "This page is only for Eagle Division teams."
MATERIALS_CLOSED = "Problem materials are only available during the competition and after submissions unlock."
INSTRUCTIONS_PDF = "/tabot-files/eagledivision/Eagle-Division-2026.pdf" #change when files updated


def _deny(message="Unauthorized", status=HTTPStatus.FORBIDDEN):
    return make_response({"message": message}, status)


def _eagle_team(team_id):
    return Teams.query.filter_by(Id=team_id, Division=Division.EAGLE.value).first()


def _role(message):
    return "student" if (message.SenderType or "").strip().lower() == "student" else "admin"


def _when(moment):
    return moment.isoformat(sep=" ", timespec="seconds") if moment else ""


def _materials_error():
    """None if the caller may see the Eagle problem and instructions, else the error response."""
    actor = actor_of()
    if actor == Actor.SYSTEM_ADMIN:
        return None
    if actor != Actor.STUDENT:
        return _deny()
    if not _eagle_team(current_user.TeamId):
        return _deny(NOT_EAGLE)
    return None if can_student_access_competition_materials() else _deny(MATERIALS_CLOSED)


def _visible_teams():
    """Eagle teams the caller may see (all for a system admin, own school for a teacher), else None."""
    actor = actor_of()
    if actor not in (Actor.SYSTEM_ADMIN, Actor.TEACHER):
        return None
    teams = Teams.query.filter(Teams.Division == Division.EAGLE.value)
    if actor == Actor.TEACHER:
        teams = teams.filter(Teams.SchoolId == school_id_of())
    return teams.order_by(asc(Teams.SchoolId), asc(Teams.TeamNumber)).all()


@eagle_api.route("/instructions", methods=["GET"])
@jwt_required()
def download_eagle_instructions():
    if err := _materials_error():
        return err
    if not os.path.isfile(INSTRUCTIONS_PDF):
        return _deny("Eagle instructions PDF is not available on the server.", HTTPStatus.NOT_FOUND)
    return send_file(INSTRUCTIONS_PDF, mimetype="application/pdf", as_attachment=True,
                     download_name="Eagle-Division-2026.pdf")


@eagle_api.route("/problem", methods=["GET"])
@jwt_required()
@inject
def eagle_problem(project_repo: ProjectRepository = Provide[Container.project_repo]):
    if err := _materials_error():
        return err
    result = {"projectId": None, "name": None, "preview": None, "previewKind": "none", "filename": None, "hint": None}
    if project := project_repo.get_eagle_competition_project():
        preview = project_repo.get_assignment_preview_for_ui(int(project.Id))
        result.update(projectId=int(project.Id), name=project.Name, preview=preview.get("text"),
                      previewKind=preview.get("kind"), filename=preview.get("filename"))
    return jsonify(result)


@eagle_api.route("/teams", methods=["GET"])
@jwt_required()
def list_eagle_teams():
    teams = _visible_teams()
    if teams is None:
        return _deny("Admin access required")
    return jsonify([{"id": t.Id, "name": t.Name, "teamNumber": t.TeamNumber, "schoolId": t.SchoolId} for t in teams])


@eagle_api.route("/conversations", methods=["GET"])
@jwt_required()
def list_eagle_conversations():
    teams = _visible_teams()
    if teams is None:
        return _deny()
    out = []
    for team in teams:
        thread = EagleTeamMessages.query.filter_by(TeamId=team.Id)
        last = thread.order_by(desc(EagleTeamMessages.CreatedAt), desc(EagleTeamMessages.Id)).first()
        count = thread.count()
        stage = "no_messages" if not count else "needs_admin_reply" if _role(last) == "student" else "waiting_for_requester"
        out.append({
            "teamId": int(team.Id), "teamName": str(team.Name or f"Team {team.Id}").strip(),
            "teamNumber": int(team.TeamNumber or 0), "schoolId": int(team.SchoolId or 0),
            "lastMessagePreview": str(last.Body or "").strip()[:140] if last else None,
            "lastMessageAt": _when(last.CreatedAt) or None if last else None,
            "lastSenderRole": _role(last) if last else None, "conversationStage": stage, "messageCount": count,
        })
    return jsonify(out)


@eagle_api.route("/messages", methods=["GET"])
@jwt_required()
def get_messages():
    actor = actor_of()
    if actor == Actor.STUDENT:
        team = _eagle_team(current_user.TeamId)
        if not team:
            return _deny(NOT_EAGLE)
    elif actor in (Actor.SYSTEM_ADMIN, Actor.TEACHER):
        if not (team_id := request.args.get("team_id", type=int)):
            return _deny("team_id is required", HTTPStatus.BAD_REQUEST)
        if not (team := _eagle_team(team_id)):
            return _deny("Eagle team not found", HTTPStatus.NOT_FOUND)
        if not can_view_eagle_chat(team):
            return _deny()
    else:
        return _deny()
    rows = EagleTeamMessages.query.filter_by(TeamId=team.Id).order_by(
        asc(EagleTeamMessages.CreatedAt), asc(EagleTeamMessages.Id)).all()
    return jsonify([{"id": m.Id, "sender": _role(m), "senderRole": _role(m), "body": m.Body,
                     "createdAt": _when(m.CreatedAt)} for m in rows])


@eagle_api.route("/messages", methods=["POST"])
@jwt_required()
def post_message():
    data = request.get_json() or {}
    if not (body := (data.get("body") or "").strip()):
        return _deny("Message body is required.", HTTPStatus.BAD_REQUEST)
    actor = actor_of()
    if actor == Actor.STUDENT:
        if not (team := _eagle_team(current_user.TeamId)):
            return _deny(NOT_EAGLE)
        message = EagleTeamMessages(TeamId=team.Id, SenderType="student", StudentId=current_user.Id, Body=body)
    elif actor == Actor.TEACHER:
        return _deny("Teachers can view Eagle chat threads but cannot send messages.")
    elif actor == Actor.SYSTEM_ADMIN:
        try:
            team = _eagle_team(int(data.get("team_id")))
        except (TypeError, ValueError):
            return _deny("team_id is required", HTTPStatus.BAD_REQUEST)
        if not team:
            return _deny("Eagle team not found", HTTPStatus.NOT_FOUND)
        message = EagleTeamMessages(TeamId=team.Id, SenderType="admin", AdminId=current_user.Id, Body=body)
    else:
        return _deny()
    db.session.add(message)
    db.session.commit()
    return jsonify({"id": message.Id, "ok": True}), HTTPStatus.CREATED