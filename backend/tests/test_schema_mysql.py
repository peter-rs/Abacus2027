import os
from pathlib import Path

import pytest

pymysql = pytest.importorskip("pymysql")

pytestmark = [
    pytest.mark.mysql,
    pytest.mark.skipif(not os.getenv("TEST_MYSQL_HOST"), reason="TEST_MYSQL_HOST not set"),
]

INIT_SQL = Path(__file__).resolve().parents[2] / "init-db" / "init.sql"
SCRATCH_DB = "abacus_schema_test"

# Mismatches that already existed before Phase 2. New ones fail the test; when you
# fix one, delete it from this set (the test tells you when it is safe to).
KNOWN_DRIFT = {
    "AdminUsers.Firstname: nullable is True in models.py, False in init.sql",
    "AdminUsers.IsLocked: nullable is True in models.py, False in init.sql",
    "AdminUsers.Lastname: nullable is True in models.py, False in init.sql",
    "HelpRequests.CreatedAt: nullable is False in models.py, True in init.sql",
    "HelpRequests.Description: nullable is False in models.py, True in init.sql",
    "LoginAttempts.IPAddress: nullable is True in models.py, False in init.sql",
    "LoginAttempts.Time: nullable is True in models.py, False in init.sql",
    "StudentUsers.IsLocked: nullable is True in models.py, False in init.sql",
    "Submissions.CodeFilepath: nullable is True in models.py, False in init.sql",
    "Submissions.IsPassing: nullable is True in models.py, False in init.sql",
    "Submissions.OutputFilepath: nullable is True in models.py, False in init.sql",
    "Submissions.Project: nullable is True in models.py, False in init.sql",
    "Submissions.Team: nullable is True in models.py, False in init.sql",
    "Submissions.Time: nullable is True in models.py, False in init.sql",
    "Submissions.User: nullable is True in models.py, False in init.sql",
    "Teams.IsOnline: nullable is True in models.py, False in init.sql",
    "Testcases.Hidden: nullable is True in models.py, False in init.sql",
}


@pytest.fixture(scope="module")
def conn():
    kw = dict(host=os.environ["TEST_MYSQL_HOST"], user=os.getenv("TEST_MYSQL_USER", "root"),
              password=os.getenv("TEST_MYSQL_PASSWORD", ""), port=int(os.getenv("TEST_MYSQL_PORT", "3306")),
              autocommit=True, client_flag=pymysql.constants.CLIENT.MULTI_STATEMENTS)
    c = pymysql.connect(**kw)
    cur = c.cursor()
    cur.execute(f"DROP DATABASE IF EXISTS {SCRATCH_DB}")
    cur.execute(f"CREATE DATABASE {SCRATCH_DB}")
    cur.execute(f"USE {SCRATCH_DB}")
    cur.execute(INIT_SQL.read_text())
    while cur.nextset():
        pass
    yield c
    cur.execute(f"DROP DATABASE IF EXISTS {SCRATCH_DB}")
    c.close()


def _exec(conn, sql, args=None):
    cur = conn.cursor()
    cur.execute(sql, args)
    return cur


def _admin(conn, email, role, school=None):
    _exec(conn, "INSERT INTO AdminUsers (Firstname,Lastname,Email,SchoolId,Role) VALUES ('f','l',%s,%s,%s)",
          (email, school, role))
    return _exec(conn, "SELECT Id FROM AdminUsers WHERE Email=%s", (email,)).fetchone()[0]


def test_staff_without_a_school_is_allowed(conn):
    assert _admin(conn, "sys@x", 1, None)
    assert _admin(conn, "comp@x", 2, None)


def test_role_outside_0_1_2_is_rejected(conn):
    with pytest.raises(pymysql.err.OperationalError) as e:      # 3819 = CHECK violated
        _admin(conn, "bad-role@x", 5, 1)
    assert e.value.args[0] == 3819


def test_unknown_school_is_rejected(conn):
    with pytest.raises(pymysql.err.IntegrityError):
        _admin(conn, "bad-school@x", 0, 99999)


def test_division_rules(conn):
    admin = _admin(conn, "judge@x", 2, None)
    ins = "INSERT INTO CompetitionAdminDivisions (AdminId, Division) VALUES (%s, %s)"
    _exec(conn, ins, (admin, "Gold"))
    _exec(conn, ins, (admin, "Eagle"))
    with pytest.raises(pymysql.err.IntegrityError):              # duplicate pair
        _exec(conn, ins, (admin, "Gold"))
    for bad in ("blue", "GOLD", "Green"):                        # wrong casing / not a division
        with pytest.raises(pymysql.err.OperationalError):
            _exec(conn, ins, (admin, bad))
    with pytest.raises(pymysql.err.IntegrityError):              # admin must exist
        _exec(conn, ins, (987654, "Blue"))


def test_deleting_admin_removes_their_divisions(conn):
    admin = _admin(conn, "cascade@x", 2, None)
    _exec(conn, "INSERT INTO CompetitionAdminDivisions (AdminId, Division) VALUES (%s,'Blue')", (admin,))
    _exec(conn, "DELETE FROM AdminUsers WHERE Id=%s", (admin,))
    left = _exec(conn, "SELECT COUNT(*) FROM CompetitionAdminDivisions WHERE AdminId=%s", (admin,)).fetchone()[0]
    assert left == 0


def test_models_match_init_sql(conn):
    """models.py and init.sql must agree on tables, columns and nullability."""
    from src.repositories.database import db
    import src.repositories.models  # noqa: F401  (registers the tables)

    cur = _exec(conn, "SELECT table_name, column_name, is_nullable FROM information_schema.columns "
                      "WHERE table_schema=%s", (SCRATCH_DB,))
    sql = {}
    for table, col, nullable in cur.fetchall():
        sql.setdefault(table, {})[col] = (nullable == "YES")

    problems = []
    for name, table in db.metadata.tables.items():
        if name not in sql:
            problems.append(f"{name}: in models.py but not in init.sql")
            continue
        model_cols = {c.name: c for c in table.columns}
        for col in set(model_cols) - set(sql[name]):
            problems.append(f"{name}.{col}: in models.py only")
        for col in set(sql[name]) - set(model_cols):
            problems.append(f"{name}.{col}: in init.sql only")
        for col in set(model_cols) & set(sql[name]):
            c = model_cols[col]
            if not c.primary_key and c.nullable != sql[name][col]:
                problems.append(f"{name}.{col}: nullable is {c.nullable} in models.py, {sql[name][col]} in init.sql")
    for name in set(sql) - set(db.metadata.tables):
        problems.append(f"{name}: in init.sql but not in models.py")
    unexpected = set(problems) - KNOWN_DRIFT
    assert not unexpected, "New models.py / init.sql mismatch:\n" + "\n".join(sorted(unexpected))
    fixed = KNOWN_DRIFT - set(problems)
    assert not fixed, "Fixed - remove from KNOWN_DRIFT:\n" + "\n".join(sorted(fixed))
