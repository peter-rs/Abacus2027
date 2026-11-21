""" tests for src/permissions.py. Not using database: instead users and teams are plain model objects."""
import pytest

from src import permissions
from src.permissions import (
    Actor, actor_of, actors_required, can_view_eagle_chat, is_staff, school_id_of,
)
from src.repositories.models import AdminUsers, StudentUsers, Teams


def staff(role, school=1):
    return AdminUsers(Id=10, Email="staff@test", Role=role, SchoolId=school)


def student(school=1):
    return StudentUsers(Id=20, TeamId=1, SchoolId=school)


@pytest.mark.parametrize("user,expected", [
    (student(), Actor.STUDENT),
    (staff(0), Actor.TEACHER),
    (staff(1, school=None), Actor.SYSTEM_ADMIN),
    (staff(2, school=None), Actor.COMPETITION_ADMIN),
])
def test_actor_of_each_kind_of_user(user, expected):
    assert actor_of(user) is expected


@pytest.mark.parametrize("user", [staff(7), staff(-1), staff(None), object(), None])
def test_unknown_users_are_nobody(user):
    assert actor_of(user) is None
    assert not is_staff(user)


def test_defaults_to_the_logged_in_user(monkeypatch):
    monkeypatch.setattr(permissions, "current_user", staff(1))
    assert actor_of() is Actor.SYSTEM_ADMIN


def test_explicit_none_does_not_fall_back_to_the_logged_in_user(monkeypatch):
    """A deleted account passed as None must not be mistaken for whoever is logged in."""
    monkeypatch.setattr(permissions, "current_user", staff(1))
    assert actor_of(None) is None


def test_every_kind_of_staff_counts_as_staff_but_students_do_not():
    assert all(is_staff(staff(role)) for role in (0, 1, 2))
    assert not is_staff(student())


def test_school_id_of():
    assert school_id_of(staff(0, school=3)) == 3
    assert school_id_of(staff(2, school=None)) == 0      # used to crash: int(None)
    assert school_id_of(student(school=5)) == 5


@actors_required(Actor.TEACHER, Actor.SYSTEM_ADMIN)
def _protected_view():
    return "ok"


@pytest.mark.parametrize("user,allowed", [
    (staff(0), True),
    (staff(1), True),
    (staff(2), False),       # competition admin: denied until granted on purpose
    (student(), False),
    (staff(7), False),       # unknown role: denied
])
def test_actors_required(app, monkeypatch, user, allowed):
    monkeypatch.setattr(permissions, "current_user", user)
    with app.test_request_context():
        result = _protected_view()
    if allowed:
        assert result == "ok"
    else:
        assert result.status_code == 403
        assert result.get_json() == {"message": "Unauthorized"}


@pytest.mark.parametrize("user,team_school,expected", [
    (staff(1, school=None), 1, True),     # system admin sees every school
    (staff(1, school=None), 2, True),
    (staff(0, school=1), 1, True),        # teacher sees their own school only
    (staff(0, school=1), 2, False),
    (staff(0, school=None), 1, False),    # a teacher with no school sees nothing
    (staff(2, school=None), 1, False),    # competition admin: nothing yet
    (staff(2, school=2), 2, False),     
    (student(), 1, False),
])
def test_can_view_eagle_chat(user, team_school, expected):
    assert can_view_eagle_chat(Teams(Id=1, SchoolId=team_school), user) is expected
