from http import HTTPStatus
from flask import Blueprint, request, jsonify, make_response, send_file
from flask_jwt_extended import jwt_required, current_user
from dependency_injector.wiring import inject, Provide
from container import Container
from typing import Any, Dict, List
import ast
import json
import os
import re
from datetime import datetime

from src.repositories.models import AdminUsers, StudentUsers, Teams
from src.repositories.team_repository import TeamRepository
from src.repositories.user_repository import UserRepository
from src.repositories.school_repository import SchoolRepository
from src.repositories.submission_repository import SubmissionRepository
from src.repositories.project_repository import ProjectRepository
from src.constants import (
    ADMIN_ROLE,
    DIVISION_TEAM_CAPS,
    COMPETITION_START,
    COMPETITION_END,
    SCOREBOARD_FREEZE,
    SCOREBOARD_RELEASE,
    is_registration_open,
    is_student_submission_locked,
    is_teacher_submission_locked,
    get_minute_index,
)
from src.permissions import Actor, actors_required 
from src.services.scoreboard_service import build_scoreboard_payload
from src.extensions import cache
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.utils import get_column_letter
from io import BytesIO

team_api = Blueprint("team_api", __name__)

def total_teams_in_division(division: str) -> int:
    return Teams.query.filter_by(Division=division).count()

def parse_result_payload(raw):
    if raw is None:
        return None

    if isinstance(raw, (dict, list)):
        return raw

    text = str(raw).strip()
    if text == "":
        return None

    try:
        return json.loads(text)
    except Exception:
        pass

    try:
        return ast.literal_eval(text)
    except Exception:
        return None


def extract_result_rows(payload):
    if isinstance(payload, list):
        return payload

    if isinstance(payload, dict):
        if isinstance(payload.get("results"), list):
            return payload["results"]
        if isinstance(payload.get("testResults"), list):
            return payload["testResults"]

    return []


def load_submission_result_rows(submission_repo: SubmissionRepository, submission) -> List[dict]:
    if submission is None:
        return []

    # First try the DB field saved on the submission row
    parsed = parse_result_payload(getattr(submission, "TestCaseResults", None))
    rows = extract_result_rows(parsed)
    if rows:
        return rows

    # Fallback to the output file contents if present
    output_path = getattr(submission, "OutputFilepath", "") or ""
    if output_path and os.path.exists(output_path):
        try:
            raw_output = submission_repo.read_output_file(output_path)
            parsed = parse_result_payload(raw_output)
            rows = extract_result_rows(parsed)
            if rows:
                return rows
        except Exception:
            pass

    return []

def count_passed_testcases(rows: List[dict]) -> int:
    passed = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        if bool(row.get("passed", row.get("State", False))):
            passed += 1
    return passed

def clean_scoreboard_args(division: str, is_online_raw: str, project_type: str = None) -> tuple:
    if not all([division, is_online_raw]):
        raise Exception('Missing required parameters')

    is_online_str = is_online_raw.lower()
    if is_online_str not in {"true", "false"}:
        raise Exception('Invalid is_online value')
    is_online = is_online_str == "true"

    division = division.capitalize()
    if division not in {"Blue", "Gold", "Eagle"}:
        raise Exception('Invalid division')
    
    if project_type is not None:
        project_type = project_type.lower()
        if project_type not in {"competition", "practice"}:
            raise Exception('Invalid project_type')
        return division, is_online, project_type

    return division, is_online

def build_scoreboard_now(project_repo, team_repo, division, is_online, project_type, now, status, transition_at=None):
    payload = build_scoreboard_payload(
        project_repo=project_repo,
        team_repo=team_repo,
        division=division,
        is_online=is_online,
        project_type=project_type,
    )
    payload["timestamp"] = now.isoformat()
    payload["status"] = status
    if transition_at:
        payload["transitionAt"] = transition_at.isoformat()
    return payload

def build_snapshot_response(scoreboard, status, transition_at=None):
    payload = json.loads(scoreboard.Payload) if scoreboard.Payload else {}
    payload["timestamp"] = scoreboard.TimeStamp.isoformat() if scoreboard.TimeStamp else None
    payload["status"] = status
    if transition_at:
        payload["transitionAt"] = transition_at.isoformat()
    return payload


@team_api.route('/create', methods=['POST'])
@jwt_required()
@actors_required(Actor.TEACHER, Actor.SYSTEM_ADMIN)
@inject
def create_team(
    team_repo: TeamRepository = Provide[Container.team_repo],
    user_repo: UserRepository = Provide[Container.user_repo],
    school_repo: SchoolRepository = Provide[Container.school_repo],
):
    data = request.get_json()

    school_id = int(getattr(current_user, "SchoolId", None) or 0)
    role = int(getattr(current_user, "Role", 0) or 0)
    requested_school_id = data.get("school_id")

    if requested_school_id:
        if user_repo.is_admin():
            school_id = requested_school_id
        elif requested_school_id != school_id:
            return make_response({'message': 'Unauthorized'}, HTTPStatus.FORBIDDEN)

    if school_id <= 0:
        return make_response({'message': 'Invalid school ID'}, HTTPStatus.BAD_REQUEST)
    
    if role != ADMIN_ROLE and not is_registration_open():
        return make_response({'message': 'Registration is closed.'}, HTTPStatus.FORBIDDEN)

    if team_repo.school_has_empty_team(school_id):
        return make_response({'message': 'An empty team already exists'}, HTTPStatus.BAD_REQUEST)

    team_number = team_repo.get_next_team_number(school_id)
    if team_number is None:
        return make_response({'message': 'Failed to determine next team number'}, HTTPStatus.INTERNAL_SERVER_ERROR)

    # Default name (Team + Team Number)
    name = f"Team {team_number}"

    default_division = next(
        (
            division
            for division in ["Blue", "Gold", "Eagle"]
            if total_teams_in_division(division) < DIVISION_TEAM_CAPS[division]
        ),
        None,
    )

    if not default_division:
        return make_response(
            {
                'message': 'All division team caps have been reached. Contact support if you believe this is a mistake.'
            },
            HTTPStatus.CONFLICT
        )

    team = team_repo.create_team(school_id, team_number, name, default_division, False)

    return make_response({
            'id': team.Id,
            'teamNumber': team.TeamNumber,
            'name': team.Name,
            'division': team.Division,
            'isOnline': team.IsOnline,
            'members': []
    }, HTTPStatus.OK)

@team_api.route('/update', methods=['PUT'])
@jwt_required()
@inject
def update_team(
    team_repo: TeamRepository = Provide[Container.team_repo],
    user_repo: UserRepository = Provide[Container.user_repo],
):
    if not isinstance(current_user, AdminUsers):
        return make_response({'message': 'Unauthorized'}, HTTPStatus.FORBIDDEN)

    data = request.get_json()
    team_id = int(data.get("team_id") or 0)
    school_id = int(getattr(current_user, "SchoolId", None) or 0)
    requested_school_id = data.get("school_id")

    if team_id <= 0:
        return make_response({'message': 'team_id is required.'}, HTTPStatus.NOT_ACCEPTABLE)

    if requested_school_id:
        if user_repo.is_admin():
            school_id = requested_school_id
        elif requested_school_id != school_id:
            return make_response({'message': 'Unauthorized'}, HTTPStatus.FORBIDDEN)

    if school_id <= 0:
        return make_response({'message': 'Invalid school ID'}, HTTPStatus.BAD_REQUEST)

    team = team_repo.get_team_by_id(team_id)
    if not team:
        return make_response({'message': 'Team not found'}, HTTPStatus.NOT_FOUND)
    if team.SchoolId != school_id:
        return make_response({'message': 'Unauthorized'}, HTTPStatus.FORBIDDEN)

    division = data.get("division")
    if division and division not in ["Blue", "Gold", "Eagle"]:
        return make_response({'message': 'Invalid division'}, HTTPStatus.BAD_REQUEST)

    name = data.get("name")
    if name is not None:
        name = name.strip()
        if len(name) < 3:
            return make_response(
                {'message': 'Team name must be at least three characters long.'},
                HTTPStatus.BAD_REQUEST
            )
        if len(name) > 30:
            return make_response(
                {'message': 'Team name can be no longer than 30 characters.'},
                HTTPStatus.BAD_REQUEST
            )
        if not re.match(r"^[A-Za-z0-9\s'\-_]+$", name):
            return make_response(
                {'message': 'Team name can only contain letters, numbers, spaces, underscores, hyphens, and apostrophes.'},
                HTTPStatus.BAD_REQUEST
            )
        if not re.search(r"[A-Za-z0-9]", name):
            return make_response(
                {'message': 'Team name must contain at least one letter or number.'},
                HTTPStatus.BAD_REQUEST
            )

        existing_team = team_repo.get_team_by_name(school_id, name)
        if existing_team and existing_team.Id != team_id:
            return make_response(
                {'message': 'Team name is already in use.'},
                HTTPStatus.BAD_REQUEST
            )
            
    is_online = data.get("is_online")

    if division and division != team.Division:
        division_cap = DIVISION_TEAM_CAPS.get(division)
        if division_cap is not None and total_teams_in_division(division) >= division_cap:
            return make_response(
                {
                    'message': f'The maximum amount of teams among all schools has been reached for the {division} division ({division_cap}). Contact support if you believe this is a mistake.'
                },
                HTTPStatus.CONFLICT
            )

    team_repo.update_team(team.Id, name=name, division=division, is_online=is_online)
    
    return make_response({'message': 'Success'}, HTTPStatus.OK)

@team_api.route('/delete', methods=['DELETE'])
@jwt_required()
@inject
def delete_team(
    team_repo: TeamRepository = Provide[Container.team_repo],
    user_repo: UserRepository = Provide[Container.user_repo],
):
    if not isinstance(current_user, AdminUsers):
            return make_response({'message': 'Unauthorized'}, HTTPStatus.FORBIDDEN)
    
    data = request.get_json()
    team_id = int(data.get("team_id") or 0)
    school_id = int(getattr(current_user, "SchoolId", None) or 0)
    requested_school_id = data.get("school_id")

    if team_id <= 0:
        return make_response({'message': 'team_id is required.'}, HTTPStatus.NOT_ACCEPTABLE)

    if requested_school_id:
        if user_repo.is_admin():
            school_id = requested_school_id
        elif requested_school_id != school_id:
            return make_response({'message': 'Unauthorized'}, HTTPStatus.FORBIDDEN)

    if school_id <= 0:
        return make_response({'message': 'Invalid school ID'}, HTTPStatus.BAD_REQUEST)

    team = team_repo.get_team_by_id(team_id)
    if not team:
        return make_response({'message': 'Team not found'}, HTTPStatus.NOT_FOUND)
    if team.SchoolId != school_id:
        return make_response({'message': 'Unauthorized'}, HTTPStatus.FORBIDDEN)
    
    student_count = user_repo.count_team_members(team.Id)
    if student_count > 0:
        return make_response(
            {'message': 'Cannot delete a team with members.'},
            HTTPStatus.BAD_REQUEST
        )

    team_repo.delete_team(team_id)

    return make_response({'message': 'Success'}, HTTPStatus.OK)

@team_api.route("/byschool", methods=["GET"])
@jwt_required()
@inject
def get_teams_by_school(
    team_repo: TeamRepository = Provide[Container.team_repo],
    user_repo: UserRepository = Provide[Container.user_repo],
):
    '''
    Lists teams for the current admin (teacher).
    Returns only hashed identifiers (no plaintext emails).
    '''

    if not isinstance(current_user, AdminUsers):
        return make_response({'message': 'Unauthorized'}, HTTPStatus.FORBIDDEN)

    school_id = int(getattr(current_user, "SchoolId", None) or 0)
    requested_school_id = request.args.get("school_id", type=int)

    if requested_school_id:
        if user_repo.is_admin():
            school_id = requested_school_id
        elif requested_school_id != school_id:
            return make_response({'message': 'Unauthorized'}, HTTPStatus.FORBIDDEN)

    if school_id <= 0:
        return make_response({'message': 'Invalid school ID'}, HTTPStatus.BAD_REQUEST)

    teams = team_repo.get_teams_by_school(school_id)
    teams_sorted = sorted(teams, key=lambda x: x.TeamNumber)
    
    payload = []
    for t in teams_sorted:
        payload.append({
            "Id": t.Id,
            "Name": t.Name,
        })

    return make_response(payload, HTTPStatus.OK)
    

@team_api.route("/byschool/details", methods=["GET"])
@jwt_required()
@inject
def get_teams_by_school_detailed(
    team_repo: TeamRepository = Provide[Container.team_repo],
    user_repo: UserRepository = Provide[Container.user_repo],
):
    '''
    Lists teams for the current admin (teacher).
    Returns only hashed identifiers (no plaintext emails).
    '''

    if not isinstance(current_user, AdminUsers):
        return make_response({'message': 'Unauthorized'}, HTTPStatus.FORBIDDEN)

    school_id = int(getattr(current_user, "SchoolId", None) or 0)
    requested_school_id = request.args.get("school_id", type=int)

    if requested_school_id:
        if user_repo.is_admin():
            school_id = requested_school_id
        elif requested_school_id != school_id:
            return make_response({'message': 'Unauthorized'}, HTTPStatus.FORBIDDEN)

    if school_id <= 0:
        return make_response({'message': 'Invalid school ID'}, HTTPStatus.BAD_REQUEST)

    students = user_repo.get_students_for_school(school_id)

    team_members: Dict[int, List[StudentUsers]] = {}
    for s in students:
        team_id = int(s.TeamId)
        if team_id <= 0:
            continue
        team_members.setdefault(team_id, []).append(s)

    teams = team_repo.get_teams_by_school(school_id)
    teams_sorted = sorted(teams, key=lambda x: x.TeamNumber)
    
    payload = []
    for t in teams_sorted:
        members_sorted = sorted(team_members.get(t.Id, []), key=lambda x: int(x.MemberId or 0))
        payload.append({
            "id": t.Id,
            "teamNumber": t.TeamNumber,
            "name": t.Name,
            "division": t.Division,
            "isOnline": t.IsOnline,
            "members": [
                {
                    "studentId": m.Id,
                    "memberId": int(m.MemberId or 0),
                    "emailHash": m.EmailHash,
                    "hasAccount": True if (m.PasswordHash is not None and m.PasswordHash != "") else False,
                    "isLocked": True if m.IsLocked else False,
                }
                for m in members_sorted
            ]
        })

    return make_response(payload, HTTPStatus.OK)

@team_api.route("/members", methods=["GET"])
@jwt_required()
@inject
def get_members_by_team(
    user_repo: UserRepository = Provide[Container.user_repo],
):
    '''
    Lists members for a given team.
    '''

    if not isinstance(current_user, AdminUsers):
        return make_response({'message': 'Unauthorized'}, HTTPStatus.FORBIDDEN)

    team_id = request.args.get("team_id", type=int)
    if team_id is None:
        return make_response({'message': 'team_id is required'}, HTTPStatus.BAD_REQUEST)

    members = user_repo.get_students_for_team(team_id)    

    return jsonify([
        {
            "Id": m.Id,
            "MemberId": m.MemberId,
        }
        for m in members
    ])

@team_api.route("/me", methods=["GET"])
@jwt_required()
@inject
def get_my_team(
    team_repo: TeamRepository = Provide[Container.team_repo],
):
    team_id = getattr(current_user, "TeamId", None)
    if team_id is None:
        return jsonify({}), 404

    team = team_repo.get_team_by_id(int(team_id))
    if not team:
        return jsonify({}), 404

    return jsonify({
        "id": team.Id,
        "name": team.Name,
        "division": team.Division,
        "teamNumber": team.TeamNumber,
        "isOnline": team.IsOnline,
    })

@team_api.route("/submissions/summary", methods=["GET"])
@jwt_required()
@inject
def get_team_submission_summary(
    team_repo: TeamRepository = Provide[Container.team_repo],
    user_repo: UserRepository = Provide[Container.user_repo],
    submission_repo: SubmissionRepository = Provide[Container.submission_repo],
    project_repo: ProjectRepository = Provide[Container.project_repo],
):
    """
    Returns one summary row per project for the requested team.
    Shape matches what AdminTeamSubmissions.tsx expects:
    [
        {
            "projectId": 1,
            "totalTestcases": 8,
            "passedTestcases": 6,
            "submissionCount": 3,
            "latestSubmissionId": 42,
            "latestSubmittedAt": "2026-03-19T14:23:11"
        }
    ]
    """

    is_admin = isinstance(current_user, AdminUsers)
    is_student = isinstance(current_user, StudentUsers)
    is_global_admin = bool(
        is_admin and int(getattr(current_user, "Role", 0) or 0) == ADMIN_ROLE
    )

    if not (is_admin or is_student):
        return make_response({'message': 'Unauthorized'}, HTTPStatus.FORBIDDEN)

    requested_team_id = request.args.get("team_id", type=int)

    if is_student:
        if is_student_submission_locked():
            return make_response(
                {
                    'message': 'Student submissions are locked until 24 hours after the competition ends.'
                },
                HTTPStatus.FORBIDDEN,
            )
        own_team_id = int(getattr(current_user, "TeamId", 0) or 0)
        if own_team_id <= 0:
            return make_response({'message': 'No team is associated with this account'}, HTTPStatus.BAD_REQUEST)

        if requested_team_id and requested_team_id != own_team_id:
            return make_response({'message': 'Unauthorized'}, HTTPStatus.FORBIDDEN)

        team_id = own_team_id
        team = team_repo.get_team_by_id(team_id)
        if not team:
            return make_response({'message': 'Team not found'}, HTTPStatus.NOT_FOUND)
    else:
        team_id = requested_team_id
        if not team_id or team_id <= 0:
            return make_response({'message': 'team_id is required'}, HTTPStatus.BAD_REQUEST)

        school_id = int(getattr(current_user, "SchoolId", None) or 0)
        requested_school_id = request.args.get("school_id", type=int)

        if requested_school_id:
            if user_repo.is_admin():
                school_id = requested_school_id
            elif requested_school_id != school_id:
                return make_response({'message': 'Unauthorized'}, HTTPStatus.FORBIDDEN)

        if school_id <= 0:
            return make_response({'message': 'Invalid school ID'}, HTTPStatus.BAD_REQUEST)

        team = team_repo.get_team_by_id(team_id)
        if not team:
            return make_response({'message': 'Team not found'}, HTTPStatus.NOT_FOUND)

        if int(team.SchoolId) != int(school_id):
            return make_response({'message': 'Unauthorized'}, HTTPStatus.FORBIDDEN)

        if not is_global_admin and is_teacher_submission_locked():
            return make_response(
                {
                    'message': 'Teacher access to submissions is locked during the competition and until student submissions unlock.'
                },
                HTTPStatus.FORBIDDEN,
            )

    latest_by_project = submission_repo.get_latest_submission_by_team(team_id)
    counts_by_project = submission_repo.get_submission_counts_by_team(team_id)
    all_projects = project_repo.get_all_projects()

    payload = []
    for project in all_projects:
        latest_submission = latest_by_project.get(project.Id)

        testcase_rows = project_repo.get_testcases(project.Id) or []
        total_testcases = len(testcase_rows)

        result_rows = load_submission_result_rows(submission_repo, latest_submission)
        passed_testcases = count_passed_testcases(result_rows)

        if total_testcases > 0:
            passed_testcases = min(passed_testcases, total_testcases)

        payload.append({
            "projectId": int(project.Id),
            "totalTestcases": int(total_testcases),
            "passedTestcases": int(passed_testcases),
            "submissionCount": int(counts_by_project.get(project.Id, 0)),
            "latestSubmissionId": int(latest_submission.Id) if latest_submission else None,
            "latestSubmittedAt": latest_submission.Time.isoformat() if latest_submission and latest_submission.Time else None,
        })

    return jsonify(payload)

@team_api.route("/scoreboard", methods=["GET"])
@jwt_required(optional=True)
@inject
def get_scoreboard(
    team_repo: TeamRepository = Provide[Container.team_repo],
    project_repo: ProjectRepository = Provide[Container.project_repo],
    user_repo: UserRepository = Provide[Container.user_repo],
):
    """
    Get team rankings (solved count, penalty) for a division/project_type/attendance.
    Returns list of dicts with team info and stats for the scoreboard.
    """
    division = request.args.get("division", type=str)
    project_type = request.args.get("project_type", type=str)
    is_online_raw = request.args.get("is_online", type=str)

    try:
        division, is_online, project_type = clean_scoreboard_args(division, is_online_raw, project_type)
    except Exception as e:
        return make_response({'message': str(e)}, HTTPStatus.BAD_REQUEST)

    user_is_admin = current_user is not None and user_repo.is_admin()
    now = datetime.now()

    if project_type == "practice":
        if not user_is_admin:
            return make_response({'message': 'Forbidden'}, HTTPStatus.FORBIDDEN)
        return jsonify(build_scoreboard_now(project_repo, team_repo, division, is_online, project_type, now, "practice"))

    if now < COMPETITION_START:
        if not user_is_admin:
            return jsonify({
                "projects": [],
                "teams": [],
                "status": "upcoming",
                "transitionAt": COMPETITION_START.isoformat()
            })
        return jsonify(build_scoreboard_now(
            project_repo, team_repo, division, is_online, project_type, now, "upcoming",
            transition_at=COMPETITION_START
        ))

    transition_at = None
    if now > COMPETITION_END:
        if user_is_admin or now > SCOREBOARD_RELEASE:
            minute = get_minute_index(start=COMPETITION_START, now=COMPETITION_END)
            status = "final"
        else:
            return jsonify({
                "projects": [],
                "teams": [],
                "status": "awaiting-results",
                "transitionAt": SCOREBOARD_RELEASE.isoformat()
            })
    elif now > SCOREBOARD_FREEZE and not user_is_admin:
        minute = get_minute_index(start=COMPETITION_START, now=SCOREBOARD_FREEZE)
        status = "frozen"
        transition_at = COMPETITION_END
    elif now > SCOREBOARD_FREEZE and user_is_admin:
        minute = get_minute_index(start=COMPETITION_START, now=now)
        status = "frozen-admin"
    else:
        minute = get_minute_index(start=COMPETITION_START, now=now)
        status = "live"

    cache_key = f"scoreboard:{division}:{is_online}:{minute}:{status}"

    cached = cache.get(cache_key)
    if cached:
        return jsonify(cached)

    scoreboard = team_repo.get_latest_scoreboard_snapshot(division=division, is_online=is_online, max_minute=minute)
    if not scoreboard:
        return make_response({"message": "Scoreboard failed to load."}, HTTPStatus.NOT_FOUND)

    payload = build_snapshot_response(scoreboard, status, transition_at=transition_at)

    cache.set(cache_key, payload, timeout=60)

    return jsonify(payload)

@team_api.route("/scoreboard/download", methods=["GET"])
@jwt_required()
@inject
def download_scoreboard(
    team_repo: TeamRepository = Provide[Container.team_repo],
    project_repo: ProjectRepository = Provide[Container.project_repo],
    user_repo: UserRepository = Provide[Container.user_repo],
):
    if not user_repo.is_admin():
        return make_response({'message': 'Forbidden'}, HTTPStatus.FORBIDDEN)
    
    division = request.args.get("division", type=str)
    is_online_raw = request.args.get("is_online", type=str)

    try:
        division, is_online = clean_scoreboard_args(division, is_online_raw)
    except Exception as e:
        return make_response({'message': str(e)}, HTTPStatus.BAD_REQUEST)
    
    now = datetime.now()

    if now > COMPETITION_END:
        minute = get_minute_index(start=COMPETITION_START, now=COMPETITION_END)
    else:
        minute = get_minute_index(start=COMPETITION_START, now=now)

    scoreboard = team_repo.get_latest_scoreboard_snapshot(division=division, is_online=is_online, max_minute=minute)

    if scoreboard:
        timestamp = scoreboard.TimeStamp.strftime("%B %d, %Y at %I:%M %p") if scoreboard.TimeStamp else "Unknown"
        payload = json.loads(scoreboard.Payload) if scoreboard.Payload else {}
    else:
        try:
            payload = build_scoreboard_now(project_repo, team_repo, division, is_online, "competition", now, "")
            timestamp = now.strftime("%B %d, %Y at %I:%M %p")
        except Exception:
            return make_response({"message": "Scoreboard failed to load."}, HTTPStatus.SERVICE_UNAVAILABLE)

    teams = payload.get("teams", [])
    projects = payload.get("projects", [])
    is_online_str = "Virtual" if is_online else "In-Person"

    wb = Workbook()
    ws = wb.active
    ws.title = 'Scoreboard'

    headers = ['Rank', 'Team Name', 'School Name', 'Score', 'Total Penalty']
    headers += [f"P{p['orderIndex']}" for p in projects]

    total_cols = len(headers)
    ws.cell(row=1, column=1, value=f"{division} {is_online_str} Scoreboard - {timestamp}")
    ws.cell(row=1, column=1).font = Font(bold=True, size=13, name="Arial")
    ws.cell(row=1, column=1).alignment = Alignment(horizontal="left", vertical="center")
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=total_cols)

    cell_alignment = Alignment(horizontal="center", vertical="center")

    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=3, column=col, value=header)
        cell.font = Font(bold=True, size=11, name="Arial")
        cell.fill = PatternFill("solid", fgColor="D9E1F2")
        cell.alignment = cell_alignment

    for t_idx, team in enumerate(teams):
        row = t_idx + 4
        ws.cell(row=row, column=1, value=t_idx + 1).alignment = cell_alignment
        ws.cell(row=row, column=2, value=team.get('teamName'))
        ws.cell(row=row, column=3, value=team.get('schoolName'))
        ws.cell(row=row, column=4, value=team.get('solvedCount')).alignment = cell_alignment
        ws.cell(row=row, column=5, value=team.get('totalPenalty')).alignment = cell_alignment
        for p_idx, project in enumerate(team.get('projects', [])):
            icon = "\u2713" if project.get('solved') else "\u2717"
            col = p_idx + 6
            if project.get("attempts", 0) > 0:
                val = f"{icon} {project.get('attempts', '')}"
            else:
                val = ""
            ws.cell(row=row, column=col, value=val).alignment = cell_alignment

    for col_idx in range(1, total_cols + 1):
        max_len = max(
            (len(str(ws.cell(row=row, column=col_idx).value or ""))
            for row in range(3, len(teams) + 4)),
            default=0,
        )
        ws.column_dimensions[get_column_letter(col_idx)].width = max(max_len + 3, 10)
    
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{now_str}_{division}_{is_online_str}_Scoreboard.xlsx"

    return send_file(buffer, download_name=filename, as_attachment=True, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.xml")