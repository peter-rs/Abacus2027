"""
Permissions File determines who has access to what in the system. It is used to check if a user has the right permissions to access certain routes or perform certain actions.  
"""
from enum import Enum
from functools import wraps
from http import HTTPStatus

from flask import make_response 
from flask_jwt_extended import current_user #current user is the actual row in database 

from src.constants import StaffRole 
from src.repositories.database import db
from src.repositories.models import AdminUsers, StudentUsers, Teams


class Actor(Enum):
    STUDENT = "student"
    TEACHER = "teacher"
    SYSTEM_ADMIN = "system_admin"
    COMPETITION_ADMIN = "competition_admin"


_ACTOR_BY_ROLE = {
    StaffRole.TEACHER: Actor.TEACHER,
    StaffRole.SYSTEM_ADMIN: Actor.SYSTEM_ADMIN,
    StaffRole.COMPETITION_ADMIN: Actor.COMPETITION_ADMIN,
}

_CURRENT = object()   # will look at logged in user underscore allows running from anywhere

def _resolve_user(user):
    if user is _CURRENT: #current can be none so this checks that output
        return current_user
    return user

def actor_of(user=_CURRENT): #user =_CURRENT only runs when argument exlcuded
    """What kind of user this is, or None if unknown. Defaults to the logged-in user."""
    user = _resolve_user(user)
    if isinstance(user, StudentUsers):
        return Actor.STUDENT
    if isinstance(user, AdminUsers):
        try:
            return _ACTOR_BY_ROLE.get(StaffRole(int(user.Role)))
        except (TypeError, ValueError):
            return None
    return None


def is_student(user=_CURRENT) -> bool:
    return actor_of(user) == Actor.STUDENT


def is_teacher(user=_CURRENT) -> bool:
    return actor_of(user) == Actor.TEACHER


def is_system_admin(user=_CURRENT) -> bool:
    return actor_of(user) == Actor.SYSTEM_ADMIN


def is_competition_admin(user=_CURRENT) -> bool:
    return actor_of(user) == Actor.COMPETITION_ADMIN


def is_staff(user=_CURRENT) -> bool:
    """Teacher, system admin or competition admin (anyone in AdminUsers with a known role)."""
    return actor_of(user) in (Actor.TEACHER, Actor.SYSTEM_ADMIN, Actor.COMPETITION_ADMIN)


def school_id_of(user=_CURRENT) -> int:
    """The user's school id, or 0 if they have none (system and competition admins)."""
    user = _resolve_user(user)
    return int(getattr(user, "SchoolId", None) or 0)


def actors_required(*allowed):
    """Decorator only lets in allowed users return HTTP forbidden otherwise."""
    def decorator(view):
    """takes in the route for decoration"""
        @wraps(view) #needed so route keeps name not wapper
        def wrapper(*args, **kwargs):
            """accepts position and keyword input. Sees if actor is allowed if so then they run the route otherwise return forbidden"""
            if actor_of() not in allowed:
                return make_response({"message": "Unauthorized"}, HTTPStatus.FORBIDDEN) #makes json and sets status
            return view(*args, **kwargs)
        return wrapper
    return decorator


def can_view_eagle_chat(team, user=_CURRENT) -> bool:
    """Staff can see Eagle team's chat."""
    user = _resolve_user(user)
    actor = actor_of(user)
    if actor == Actor.SYSTEM_ADMIN:
        return True
    if actor == Actor.TEACHER:
        school = school_id_of(user)
        return school > 0 and int(getattr(team, "SchoolId", 0) or 0) == school
    return False   #division not setup yet

def can_view_submissions(submission, user = _CURRENT) -> bool:
    """You can view submissions if you are System admin. Teacher admin only should be allowed to see theri team, and Competition should be be able to see their dvision"""
    user = _resolve_user(user)
    if submission is None:
        return False
    actor = actor_of(user)
    team_id = int(getattr(submission, "Team", 0) or 0)
    if actor == Actor.SYSTEM_ADMIN:
        return True
    if actor == Actor.STUDENT:
        return team_id > 0 and int(getattr(user, "TeamId", 0) or 0) == team_id
    if actor == Actor.TEACHER:
        team = db.sessions.get(Teams, team_id) if team_id > 0 else None
        school = school_id_of(user)
        return team is not None and school > 0 and int(team.SchoolId or 0) == school
    if actor == Actor.COMPETITION_ADMIN:
        return True
    return False