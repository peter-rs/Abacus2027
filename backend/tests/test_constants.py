from datetime import datetime, timedelta

import pytest

from src import constants as c


@pytest.mark.parametrize(
    "now, expected",
    [
        (c.REGISTRATION_END - timedelta(days=1), True),
        (c.REGISTRATION_END, True),
        (c.REGISTRATION_END + timedelta(seconds=1), False),
    ],
)
def test_is_registration_open(now, expected):
    assert c.is_registration_open(now) is expected


@pytest.mark.parametrize(
    "now, expected",
    [
        (c.COMPETITION_START - timedelta(minutes=1), False),
        (c.COMPETITION_START, True),
        (c.COMPETITION_END + timedelta(hours=1), True),
        (c.STUDENT_SUBMISSION_UNLOCK - timedelta(seconds=1), True),
        (c.STUDENT_SUBMISSION_UNLOCK, False),
    ],
)
def test_is_teacher_submission_locked(now, expected):
    assert c.is_teacher_submission_locked(now) is expected


@pytest.mark.parametrize(
    "now, expected",
    [
        (c.COMPETITION_START, False),  
        (c.COMPETITION_END - timedelta(minutes=1), False),
        (c.COMPETITION_END, True),
        (c.STUDENT_SUBMISSION_UNLOCK - timedelta(seconds=1), True),
        (c.STUDENT_SUBMISSION_UNLOCK, False),
    ],
)
def test_is_student_submission_locked(now, expected):
    assert c.is_student_submission_locked(now) is expected


@pytest.mark.parametrize(
    "now, expected",
    [
        (c.COMPETITION_START - timedelta(minutes=1), False),
        (c.COMPETITION_START, True),
        (c.COMPETITION_END, False), 
        (c.STUDENT_SUBMISSION_UNLOCK, True),
    ],
)
def test_can_student_access_competition_materials(now, expected):
    assert c.can_student_access_competition_materials(now) is expected


def test_get_minute_index():
    start = datetime(2026, 4, 15, 9, 0)
    assert c.get_minute_index(start, start - timedelta(seconds=1)) == -1
    assert c.get_minute_index(start, start) == 0
    assert c.get_minute_index(start, start + timedelta(minutes=5, seconds=59)) == 5
    assert c.get_minute_index(start, start + timedelta(hours=3)) == 180


def test_get_competition_schedule_shape():
    schedule = c.get_competition_schedule()
    assert set(schedule) == {
        "registrationEnd",
        "practiceStart",
        "practiceEnd",
        "competitionStart",
        "competitionEnd",
        "studentSubmissionUnlock",
    }
    for value in schedule.values():
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%S")
    assert schedule["competitionStart"] == c.serialize_datetime(c.COMPETITION_START)


def test_division_caps_and_limits():
    caps = c.get_division_team_caps()
    assert set(caps) == {"Blue", "Gold", "Eagle"}
    assert caps["Blue"] == c.BLUE_TEAM_MAX
    assert caps["Eagle"] == c.EAGLE_TEAM_MAX

    limits = c.get_division_member_limits()
    assert set(limits) == {"Blue", "Gold", "Eagle"}
    for division, lim in limits.items():
        assert 1 <= lim["min"] <= lim["max"], division
    assert limits["Blue"] == {"min": c.BLUE_MEMBER_MIN, "max": c.BLUE_MEMBER_MAX}
