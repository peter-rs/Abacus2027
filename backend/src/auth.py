import hashlib
import re
from datetime import datetime
from http import HTTPStatus
from typing import Optional

from dependency_injector.wiring import Provide, inject
from flask import Blueprint, current_app, make_response, request
from flask_jwt_extended import create_access_token, current_user, jwt_required
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

from container import Container
from src.api_utils import get_value_or_empty
from src.config import env_bool, require_env, require_int_env
from src.email import send_password_link_email
from src.jwt_manager import jwt
from src.repositories.models import AdminUsers, StudentUsers
from src.repositories.team_repository import TeamRepository
from src.repositories.user_repository import UserRepository

auth_api = Blueprint("auth_api", __name__)

PASSWORD_TOKEN_SALT = require_env("PASSWORD_TOKEN_SALT")
PASSWORD_TOKEN_MAX_AGE_SECONDS = require_int_env("PASSWORD_TOKEN_MAX_AGE_SECONDS")

# Schools where students may not be able to receive email directly, so password
# emails should CC the teacher if the teacher email matches one of these suffixes.
TEACHER_EMAIL_ENDSWITH = [
    "@milwaukee.k12.wi.us",
    "@depere.k12.wi.us",
]

def frontend_base_url() -> str:
    # The React app URL must come from the real process environment.
    # No localhost fallback. No Flask-config fallback.
    return require_env("FRONTEND_BASE_URL").rstrip("/")

def is_valid_password(password: str) -> bool:
    if len(password) < 8:
        return False
    if not re.search(r"[A-Z]", password):
        return False
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        return False
    return True

# Local server must be restarted if DEBUGGER_MODE is changed.
DEBUGGER_MODE = env_bool("DEBUGGER_MODE", False)

# Password assigned to accounts created while DEBUGGER_MODE is on.
DEBUG_DEFAULT_PASSWORD = require_env("DEBUG_DEFAULT_PASSWORD") if DEBUGGER_MODE else None

def password_sig(password_hash: str) -> str:
    return hashlib.sha256((password_hash or "").encode("utf-8")).hexdigest()

def password_token_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(str(current_app.config["JWT_SECRET_KEY"]))

def create_password_token(user_type: str, user_id: int, current_password_hash: str) -> str:
    payload = {
        "type": user_type,
        "id": int(user_id),
        "sig": password_sig(current_password_hash or ""),
    }
    return password_token_serializer().dumps(payload, salt=PASSWORD_TOKEN_SALT)

def decode_password_token(token: str) -> dict:
    return password_token_serializer().loads(
        token,
        salt=PASSWORD_TOKEN_SALT,
        max_age=PASSWORD_TOKEN_MAX_AGE_SECONDS,
    )

def build_password_link(token: str) -> str:
    return f"{frontend_base_url()}/set-password?token={token}"

def teacher_cc_email_for_restricted_student_email_schools(
    student: Optional[StudentUsers],
    user_repo: UserRepository,
) -> Optional[str]:
    """
    Returns the teacher email to CC for schools where students cannot receive
    email directly and password/setup emails should also go to the teacher.
    """
    if not student:
        return None

    teacher_id = int(getattr(student, "TeacherId", 0) or 0)
    if teacher_id <= 0:
        return None

    teacher = user_repo.get_admin_by_id(teacher_id)
    teacher_email = (getattr(teacher, "Email", "") or "").strip().lower() if teacher else ""

    if any(teacher_email.endswith(suffix) for suffix in TEACHER_EMAIL_ENDSWITH):
        return teacher_email

    return None

@jwt.user_identity_loader
def user_identity_lookup(user):
    if isinstance(user, AdminUsers):
        return {"type": "admin", "id": user.Id}
    if isinstance(user, StudentUsers):
        return {"type": "student", "id": user.Id}
    return {"type": "unknown", "id": getattr(user, "Id", None)}

@auth_api.route("/get-role", methods=["GET"])
@jwt_required()
@inject
def get_user_role(user_repo: UserRepository = Provide[Container.user_repo]):
    status = user_repo.get_user_status()  # "admin" | "student" | "unknown"
    if status == "admin":
        # AdminUsers: Role 0 = teacher, Role 1 = admin
        role = int(getattr(current_user, "Role", 0) or 0)
        return make_response({"role": role, "status": status}, HTTPStatus.OK)
    if status == "student":
        return make_response({"role": 0, "status": status}, HTTPStatus.OK)
    return make_response({"role": -1, "status": status}, HTTPStatus.OK)

@jwt.user_lookup_loader
def user_lookup_callback(jwt_header, jwt_data):
    identity = jwt_data["sub"] or {}
    user_type = identity.get("type")
    user_id = identity.get("id")
    if user_type == "admin":
        return AdminUsers.query.filter_by(Id=user_id).one_or_none()
    if user_type == "student":
        return StudentUsers.query.filter_by(Id=user_id).one_or_none()
    return None

@auth_api.route("/admin/login", methods=["POST"])
@inject
def admin_login(user_repo: UserRepository = Provide[Container.user_repo]):
    input_json = request.get_json() or {}
    email = get_value_or_empty(input_json, "email").strip().lower()
    password = get_value_or_empty(input_json, "password")

    if user_repo.can_admin_login(email) >= current_app.config["MAX_FAILED_LOGINS"]:
        user_repo.lock_admin_account(email)
        return make_response(
            {"message": "Your account has been locked! Please contact an administrator!"},
            HTTPStatus.FORBIDDEN,
        )

    admin = user_repo.get_admin_by_email(email)
    if not admin:
        return make_response({"message": "No teacher account found for that email."}, HTTPStatus.NOT_FOUND)

    if getattr(admin, "IsLocked", False):
        return make_response(
            {"message": "Your account has been locked! Please contact an administrator!"},
            HTTPStatus.FORBIDDEN,
        )

    if (not DEBUGGER_MODE) and not (admin.PasswordHash or "").strip():
        return make_response(
            {"message": "Account setup pending. Please check your email for a password link."},
            HTTPStatus.FORBIDDEN,
        )

    if not check_password_hash(admin.PasswordHash or "", password):
        user_repo.send_admin_attempt_data(email, request.remote_addr, datetime.now())
        return make_response(
            {"message": "Invalid email and/or password! Please try again!"},
            HTTPStatus.FORBIDDEN,
        )

    user_repo.clear_admin_failed_attempts(email)
    access_token = create_access_token(identity=admin)
    return make_response(
        {
            "message": "Success",
            "access_token": access_token,
            "role": int(getattr(admin, "Role", 0) or 0),
        },
        HTTPStatus.OK,
    )

@auth_api.route("/student/login", methods=["POST"])
@inject
def student_login(user_repo: UserRepository = Provide[Container.user_repo]):
    input_json = request.get_json() or {}
    email = get_value_or_empty(input_json, "email").strip().lower()
    password = get_value_or_empty(input_json, "password")

    email_hash = hashlib.sha256(email.encode("utf-8")).hexdigest()

    if user_repo.can_student_login(email_hash) >= current_app.config["MAX_FAILED_LOGINS"]:
        user_repo.lock_student_account(email_hash)
        return make_response(
            {"message": "Your account has been locked! Please contact an administrator!"},
            HTTPStatus.FORBIDDEN,
        )

    student = user_repo.get_student_by_emailhash(email_hash)
    if not student:
        return make_response({"message": "No student account found for that email."}, HTTPStatus.NOT_FOUND)

    if getattr(student, "IsLocked", False):
        return make_response(
            {"message": "Your account has been locked! Please contact an administrator!"},
            HTTPStatus.FORBIDDEN,
        )

    if (not DEBUGGER_MODE) and not (student.PasswordHash or "").strip():
        return make_response(
            {
                "message": "Account setup pending. Please check your email for a password link, or request a new one."
            },
            HTTPStatus.FORBIDDEN,
        )

    if not check_password_hash(student.PasswordHash or "", password):
        user_repo.send_student_attempt_data(email_hash, request.remote_addr, datetime.now())
        return make_response(
            {"message": "Invalid email and/or password! Please try again!"},
            HTTPStatus.FORBIDDEN,
        )

    user_repo.clear_student_failed_attempts(email_hash)
    access_token = create_access_token(identity=student)
    return make_response({"message": "Success", "access_token": access_token, "role": 0}, HTTPStatus.OK)

@auth_api.route("/register", methods=["POST"])
@inject
def register_user(user_repo: UserRepository = Provide[Container.user_repo]):
    input_json = request.get_json() or {}

    first_name = get_value_or_empty(input_json, "fname")
    last_name = get_value_or_empty(input_json, "lname")
    school = get_value_or_empty(input_json, "school")
    school_id_raw = get_value_or_empty(input_json, "school_id")
    email = get_value_or_empty(input_json, "email").strip().lower()
    questionOne = get_value_or_empty(input_json, "questionOne")
    questionTwo = get_value_or_empty(input_json, "questionTwo")

    if not (first_name and last_name and email):
        return make_response(
            {"message": "Missing required data. All fields are required."},
            HTTPStatus.NOT_ACCEPTABLE,
        )

    if user_repo.does_admin_email_exist(email):
        return make_response({"message": "Email already exists"}, HTTPStatus.NOT_ACCEPTABLE)

    school_obj = None
    if str(school_id_raw or "").strip():
        try:
            sid = int(school_id_raw)
        except Exception:
            sid = 0

        if sid <= 0:
            return make_response({"message": "Invalid school_id."}, HTTPStatus.NOT_ACCEPTABLE)

        school_obj = user_repo.get_school_by_id(sid)
        if not school_obj:
            return make_response({"message": "Selected school not found."}, HTTPStatus.NOT_ACCEPTABLE)
    else:
        if not school:
            return make_response(
                {"message": "Missing required data. school (or school_id) is required."},
                HTTPStatus.NOT_ACCEPTABLE,
            )

        existing = user_repo.get_school_by_name(school)
        school_obj = existing if existing else user_repo.create_school(school)

    if DEBUGGER_MODE:
        password_hash = generate_password_hash(DEBUG_DEFAULT_PASSWORD)
    else:
        password_hash = None

    admin = user_repo.create_admin_user(
        email=email,
        first_name=first_name,
        last_name=last_name,
        school_id=school_obj.Id,
        password_hash=password_hash,
        questionOne=questionOne,
        questionTwo=questionTwo,
        role=0,
    )

    if not DEBUGGER_MODE:
        try:
            token = create_password_token("admin", admin.Id, admin.PasswordHash or "")
            link = build_password_link(token)
            send_password_link_email(
                to_email=email,
                link=link,
                account_type="admin",
            )
        except Exception as e:
            return make_response(
                {"message": f"Account created but failed to send email: {str(e)}"},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

        return make_response(
            {"message": "Account created. Please check your email to set your password."},
            HTTPStatus.OK,
        )

    return make_response(
        {"message": "Account successfully created in debugging mode."},
        HTTPStatus.OK,
    )

@auth_api.route("/student/create", methods=["POST"])
@jwt_required()
@inject
def create_student_user(
    user_repo: UserRepository = Provide[Container.user_repo],
    team_repo: TeamRepository = Provide[Container.team_repo],
):
    if not isinstance(current_user, AdminUsers):
        return make_response({"message": "Unauthorized"}, HTTPStatus.FORBIDDEN)

    input_json = request.get_json() or {}

    # Per policy: store only hashed emails. Front end sends email_hash.
    # For compatibility, allow email as input, but do NOT store it.
    email_hash = get_value_or_empty(input_json, "email_hash").strip().lower()
    email = get_value_or_empty(input_json, "email").strip().lower()
    password = get_value_or_empty(input_json, "password")
    team_id = int(get_value_or_empty(input_json, "team_id") or 0)
    member_id = int(get_value_or_empty(input_json, "member_id") or 0)
    requested_school_id = int(get_value_or_empty(input_json, "school_id") or 0)

    if team_id <= 0:
        return make_response(
            {"message": "Missing required data. team_id is required."},
            HTTPStatus.NOT_ACCEPTABLE,
        )

    team = team_repo.get_team_by_id(team_id)
    if not team:
        return make_response({"message": "Invalid team_id"}, HTTPStatus.NOT_ACCEPTABLE)

    if member_id < 1 or member_id > 4:
        return make_response(
            {"message": "member_id must be between 1 and 4."},
            HTTPStatus.NOT_ACCEPTABLE,
        )

    if not email_hash:
        if not email:
            return make_response(
                {"message": "Missing required data. email_hash (or email) is required."},
                HTTPStatus.NOT_ACCEPTABLE,
            )
        email_hash = hashlib.sha256(email.encode("utf-8")).hexdigest()

    if user_repo.does_student_emailhash_exist(email_hash):
        return make_response({"message": "Student already exists"}, HTTPStatus.NOT_ACCEPTABLE)

    role = int(getattr(current_user, "Role", 0) or 0)  # 0 = teacher, 1 = admin
    school_id = int(getattr(current_user, "SchoolId", 0) or 0)

    if requested_school_id > 0:
        if role == 1:
            school_id = requested_school_id
        elif requested_school_id != school_id:
            return make_response({"message": "Unauthorized"}, HTTPStatus.FORBIDDEN)

    if school_id <= 0:
        return make_response(
            {"message": "Missing required data. SchoolId is required."},
            HTTPStatus.NOT_ACCEPTABLE,
        )

    existing_slot = user_repo.get_student_by_school_team_member(school_id, team.Id, member_id)
    if existing_slot is not None:
        return make_response(
            {"message": "That team/member slot is already in use."},
            HTTPStatus.CONFLICT,
        )

    if user_repo.count_team_members_for_school(school_id, team.Id) >= 4:
        return make_response(
            {"message": "This team already has 4 members."},
            HTTPStatus.CONFLICT,
        )

    if DEBUGGER_MODE:
        password_hash = generate_password_hash(DEBUG_DEFAULT_PASSWORD)
    else:
        password_hash = generate_password_hash(password) if password else None

    teacher_id = current_user.Id
    if role == 1:
        teacher = (
            AdminUsers.query.filter_by(SchoolId=school_id, Role=0)
            .order_by(AdminUsers.Id.asc())
            .first()
        )
        if teacher:
            teacher_id = teacher.Id

    student = user_repo.create_student_user(
        email_hash=email_hash,
        teacher_id=teacher_id,
        school_id=school_id,
        team_id=team.Id,
        member_id=member_id,
        password_hash=password_hash,
    )

    return make_response(
        {
            "message": "Success",
            "student_id": student.Id,
            "team_id": team.Id,
            "member_id": member_id,
            "email_hash": email_hash,
        },
        HTTPStatus.OK,
    )

@auth_api.route("/student/delete", methods=["DELETE"])
@jwt_required()
@inject
def delete_student_user(
    user_repo: UserRepository = Provide[Container.user_repo],
    team_repo: TeamRepository = Provide[Container.team_repo],
):
    if not isinstance(current_user, AdminUsers):
        return make_response({"message": "Unauthorized"}, HTTPStatus.FORBIDDEN)

    input_json = request.get_json() or {}
    team_id = int(get_value_or_empty(input_json, "team_id") or 0)
    member_id = int(get_value_or_empty(input_json, "member_id") or 0)
    requested_school_id = int(get_value_or_empty(input_json, "school_id") or 0)

    if team_id <= 0 or member_id <= 0:
        return make_response(
            {"message": "team_id and member_id are required."},
            HTTPStatus.NOT_ACCEPTABLE,
        )

    role = int(getattr(current_user, "Role", 0) or 0)
    school_id = int(getattr(current_user, "SchoolId", 0) or 0)

    if requested_school_id > 0:
        if role == 1:
            school_id = requested_school_id
        elif requested_school_id != school_id:
            return make_response({"message": "Unauthorized"}, HTTPStatus.FORBIDDEN)

    if school_id <= 0:
        return make_response(
            {"message": "Missing required data. SchoolId is required."},
            HTTPStatus.NOT_ACCEPTABLE,
        )

    team = team_repo.get_team_by_id(team_id)
    if not team:
        return make_response({"message": "Invalid team_id"}, HTTPStatus.NOT_ACCEPTABLE)

    student = user_repo.get_student_by_school_team_member(school_id, team.Id, member_id)
    if not student:
        return make_response({"message": "Student not found."}, HTTPStatus.NOT_FOUND)

    user_repo.delete_student(student.Id)
    return make_response({"message": "Success"}, HTTPStatus.OK)

@auth_api.route("/student/invite", methods=["POST"])
@jwt_required()
@inject
def send_student_password_link(
    user_repo: UserRepository = Provide[Container.user_repo],
    team_repo: TeamRepository = Provide[Container.team_repo],
):
    """
    Sends or re-sends a password link email to a student.
    Verifies the provided email matches the stored hash for the team/member.
    """
    if not isinstance(current_user, AdminUsers):
        return make_response({"message": "Unauthorized"}, HTTPStatus.FORBIDDEN)

    input_json = request.get_json() or {}
    team_id = int(get_value_or_empty(input_json, "team_id") or 0)
    member_id = int(get_value_or_empty(input_json, "member_id") or 0)
    email = get_value_or_empty(input_json, "email").strip().lower()
    requested_school_id = int(get_value_or_empty(input_json, "school_id") or 0)

    if team_id <= 0 or member_id <= 0 or not email:
        return make_response(
            {"message": "team_id, member_id, and email are required."},
            HTTPStatus.NOT_ACCEPTABLE,
        )

    role = int(getattr(current_user, "Role", 0) or 0)
    school_id = int(getattr(current_user, "SchoolId", 0) or 0)

    if requested_school_id > 0:
        if role == 1:
            school_id = requested_school_id
        elif requested_school_id != school_id:
            return make_response({"message": "Unauthorized"}, HTTPStatus.FORBIDDEN)

    if school_id <= 0:
        return make_response(
            {"message": "Missing required data. SchoolId is required."},
            HTTPStatus.NOT_ACCEPTABLE,
        )

    team = team_repo.get_team_by_id(team_id)
    if not team:
        return make_response({"message": "Invalid team_id"}, HTTPStatus.NOT_ACCEPTABLE)

    student = user_repo.get_student_by_school_team_member(school_id, team.Id, member_id)
    if not student:
        return make_response({"message": "Student not found."}, HTTPStatus.NOT_FOUND)

    provided_hash = hashlib.sha256(email.encode("utf-8")).hexdigest()
    if provided_hash != (student.EmailHash or ""):
        return make_response(
            {"message": "Email does not match saved hash for this member."},
            HTTPStatus.FORBIDDEN,
        )

    if DEBUGGER_MODE:
        return make_response(
            {"message": "Email invite skipped in debugging mode."},
            HTTPStatus.OK,
        )

    try:
        cc_email = teacher_cc_email_for_restricted_student_email_schools(student, user_repo)
        token = create_password_token("student", student.Id, student.PasswordHash or "")
        link = build_password_link(token)
        send_password_link_email(
            to_email=email,
            link=link,
            account_type="student",
            cc_email=cc_email,
        )
    except Exception as e:
        return make_response(
            {"message": f"Failed to send email: {str(e)}"},
            HTTPStatus.INTERNAL_SERVER_ERROR,
        )

    return make_response({"message": "Success"}, HTTPStatus.OK)

@auth_api.route("/admin/request-password-reset", methods=["POST"])
@inject
def request_admin_password_reset(user_repo: UserRepository = Provide[Container.user_repo]):
    """
    Public endpoint. Always returns 200 to avoid account enumeration.
    """
    input_json = request.get_json() or {}
    email = get_value_or_empty(input_json, "email").strip().lower()

    if email:
        admin = user_repo.get_admin_by_email(email)
        if admin and (not DEBUGGER_MODE):
            try:
                token = create_password_token("admin", admin.Id, admin.PasswordHash or "")
                link = build_password_link(token)
                send_password_link_email(
                    to_email=email,
                    link=link,
                    account_type="admin",
                )
            except Exception:
                # Intentionally swallow errors here and still return 200.
                pass

    return make_response(
        {"message": "If an account exists for that email, a password link has been sent."},
        HTTPStatus.OK,
    )

@auth_api.route("/student/request-password-reset", methods=["POST"])
@inject
def request_student_password_reset(user_repo: UserRepository = Provide[Container.user_repo]):
    """
    Public endpoint. Always returns 200 to avoid account enumeration.
    """
    input_json = request.get_json() or {}
    email = get_value_or_empty(input_json, "email").strip().lower()

    if email:
        email_hash = hashlib.sha256(email.encode("utf-8")).hexdigest()
        student = user_repo.get_student_by_emailhash(email_hash)
        if student and (not DEBUGGER_MODE):
            try:
                cc_email = teacher_cc_email_for_restricted_student_email_schools(student, user_repo)
                token = create_password_token("student", student.Id, student.PasswordHash or "")
                link = build_password_link(token)
                send_password_link_email(
                    to_email=email,
                    link=link,
                    account_type="student",
                    cc_email=cc_email,
                )
            except Exception:
                # Intentionally swallow errors here and still return 200.
                pass

    return make_response(
        {"message": "If an account exists for that email, a password link has been sent."},
        HTTPStatus.OK,
    )

@auth_api.route("/password/complete", methods=["POST"])
@inject
def complete_password_reset(user_repo: UserRepository = Provide[Container.user_repo]):
    """
    Public endpoint. Consumes a signed token and sets a new password.
    Returns an auth access token for immediate login.
    """
    input_json = request.get_json() or {}
    token = get_value_or_empty(input_json, "token").strip()
    password = get_value_or_empty(input_json, "password")

    if not token or not password:
        return make_response(
            {"message": "Missing required data. token and password are required."},
            HTTPStatus.NOT_ACCEPTABLE,
        )

    if not is_valid_password(password):
        return make_response(
            {
                "message": (
                    "Password must be at least 8 characters long, "
                    "contain at least one uppercase letter, "
                    "and one special character."
                )
            },
            HTTPStatus.NOT_ACCEPTABLE,
        )

    try:
        data = decode_password_token(token)
    except SignatureExpired:
        return make_response(
            {"message": "This password link has expired. Please request a new one."},
            HTTPStatus.FORBIDDEN,
        )
    except BadSignature:
        return make_response(
            {"message": "Invalid password link. Please request a new one."},
            HTTPStatus.FORBIDDEN,
        )

    user_type = (data or {}).get("type")
    user_id = int((data or {}).get("id") or 0)
    sig = (data or {}).get("sig") or ""

    if user_id <= 0 or user_type not in ("admin", "student"):
        return make_response(
            {"message": "Invalid password link. Please request a new one."},
            HTTPStatus.FORBIDDEN,
        )

    new_hash = generate_password_hash(password)

    if user_type == "admin":
        admin = user_repo.get_admin_by_id(user_id)
        if not admin:
            return make_response(
                {"message": "Invalid password link. Please request a new one."},
                HTTPStatus.FORBIDDEN,
            )

        if sig != password_sig(admin.PasswordHash or ""):
            return make_response(
                {"message": "This password link is no longer valid. Please request a new one."},
                HTTPStatus.FORBIDDEN,
            )

        user_repo.set_admin_password_and_unlock(admin.Id, new_hash)
        admin = user_repo.get_admin_by_id(user_id)
        access_token = create_access_token(identity=admin)

        return make_response(
            {
                "message": "Success",
                "access_token": access_token,
                "role": int(getattr(admin, "Role", 0) or 0),
            },
            HTTPStatus.OK,
        )

    student = user_repo.get_student_by_id(user_id)
    if not student:
        return make_response(
            {"message": "Invalid password link. Please request a new one."},
            HTTPStatus.FORBIDDEN,
        )

    if sig != password_sig(student.PasswordHash or ""):
        return make_response(
            {"message": "This password link is no longer valid. Please request a new one."},
            HTTPStatus.FORBIDDEN,
        )

    user_repo.set_student_password_and_unlock(student.Id, new_hash)
    student = user_repo.get_student_by_id(user_id)
    access_token = create_access_token(identity=student)

    return make_response(
        {"message": "Success", "access_token": access_token, "role": 0},
        HTTPStatus.OK,
    )