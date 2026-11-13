"""
Permissions File determines who has access to what in the system. It is used to check if a user has the right permissions to access certain routes or perform certain actions.  
"""
from enum import Enum
from functools import wraps
from http import HTTPStatus

from flask import make_response
from flask_jwt_extended import current_user

from src.constants import StaffRole 
from src.repositories.models import AdminUsers, StudentUsers


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

_CURRENT = object()   # will look at logged in user


def actor_of(user=_CURRENT):
    """What kind of user this is, or None if unknown. Defaults to the logged-in user."""
    if user is _CURRENT:
        user = current_user
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
    if user is _CURRENT:
        user = current_user
    return int(getattr(user, "SchoolId", None) or 0)


def actors_required(*allowed):
    """
    Decrorator only lets in allowed users return HTTP forbidden otherwise.
    """
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if actor_of() not in allowed:
                return make_response({"message": "Unauthorized"}, HTTPStatus.FORBIDDEN)
            return view(*args, **kwargs)
        return wrapper
    return decorator


def can_view_eagle_chat(team, user=_CURRENT) -> bool:
    """Staff can see Eagle team's chat."""
    actor = actor_of(user)
    if actor == Actor.SYSTEM_ADMIN:
        return True
    if actor == Actor.TEACHER:
        school = school_id_of(user)
        return school > 0 and int(getattr(team, "SchoolId", 0) or 0) == school
    return False   #division not setup yet
