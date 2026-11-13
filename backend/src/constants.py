from datetime import datetime
from enum import Enum, IntEnum

class StaffRole(IntEnum):
    TEACHER = 0
    SYSTEM_ADMIN = 1        
    COMPETITION_ADMIN = 2

class Division(Enum):
    BLUE = "Blue"
    GOLD = "Gold"
    EAGLE = "Eagle"

#Issues from differnece in storage
def normalize_division(value): 
    """Teams stores 'Blue', Projects stores 'blue'. Compare through this."""
    v = str(value or "").strip().lower()
    return next((d for d in Division if d.value.lower() == v), None)

TEACHER_ROLE = StaffRole.TEACHER.value
ADMIN_ROLE = StaffRole.SYSTEM_ADMIN.value
EMPTY = -1

# Team Max
BLUE_TEAM_MAX = 80
GOLD_TEAM_MAX = 80
EAGLE_TEAM_MAX = 20

# Team Member Min and Max
BLUE_MEMBER_MIN = 3
BLUE_MEMBER_MAX = 4

GOLD_MEMBER_MIN = 2
GOLD_MEMBER_MAX = 3

EAGLE_MEMBER_MIN = 2
EAGLE_MEMBER_MAX = 4

# Problem Max
COMPETITION_PROBLEM_MAX = 10

# Competition Date Info
COMPETITION_DATE = (2026, 4, 15)

REGISTRATION_END = datetime(2026, 3, 27, 23, 59, 59)
PRACTICE_START = datetime(2026, 3, 30, 8, 0)
PRACTICE_END = datetime(*COMPETITION_DATE, 9, 0)

COMPETITION_START = datetime(*COMPETITION_DATE, 9, 0)
COMPETITION_END = datetime(*COMPETITION_DATE, 12, 0)
STUDENT_SUBMISSION_UNLOCK = datetime(2026, 4, 16, 12, 0)

SCOREBOARD_FREEZE = datetime(*COMPETITION_DATE, 11, 30)
SCOREBOARD_RELEASE = datetime(*COMPETITION_DATE, 14, 0)

DIVISION_TEAM_CAPS = {
    "Blue": BLUE_TEAM_MAX,
    "Gold": GOLD_TEAM_MAX,
    "Eagle": EAGLE_TEAM_MAX,
}

DIVISION_MEMBER_LIMITS = {
    "Blue": {"min": BLUE_MEMBER_MIN, "max": BLUE_MEMBER_MAX},
    "Gold": {"min": GOLD_MEMBER_MIN, "max": GOLD_MEMBER_MAX},
    "Eagle": {"min": EAGLE_MEMBER_MIN, "max": EAGLE_MEMBER_MAX},
}

def get_division_team_caps() -> dict[str, int]:
    return {division: int(cap) for division, cap in DIVISION_TEAM_CAPS.items()}


def get_division_member_limits() -> dict[str, dict[str, int]]:
    return {
        division: {"min": int(limits["min"]), "max": int(limits["max"])}
        for division, limits in DIVISION_MEMBER_LIMITS.items()
    }

def is_registration_open(now: datetime | None = None) -> bool:
    current = now or datetime.now()
    return current <= REGISTRATION_END

def is_teacher_submission_locked(now: datetime | None = None) -> bool:
    current = now or datetime.now()
    return COMPETITION_START <= current < STUDENT_SUBMISSION_UNLOCK

def is_student_submission_locked(now: datetime | None = None) -> bool:
    current = now or datetime.now()
    return COMPETITION_END <= current < STUDENT_SUBMISSION_UNLOCK

def can_student_access_competition_materials(now: datetime | None = None) -> bool:
    current = now or datetime.now()
    return current >= COMPETITION_START and not is_student_submission_locked(current)

def serialize_datetime(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%S")

def get_competition_schedule() -> dict[str, str]:
    return {
        "registrationEnd": serialize_datetime(REGISTRATION_END),
        "practiceStart": serialize_datetime(PRACTICE_START),
        "practiceEnd": serialize_datetime(PRACTICE_END),
        "competitionStart": serialize_datetime(COMPETITION_START),
        "competitionEnd": serialize_datetime(COMPETITION_END),
        "studentSubmissionUnlock": serialize_datetime(STUDENT_SUBMISSION_UNLOCK),
    }

def get_minute_index(start: datetime, now: datetime | None = None) -> int:
    current = now or datetime.now()
    if current < start:
        return -1
    return int((current - start).total_seconds() // 60)
