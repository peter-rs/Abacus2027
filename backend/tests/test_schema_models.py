import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.repositories.database import db
from src.repositories.models import AdminUsers, CompetitionAdminDivisions, Schools


@pytest.fixture()
def session():
    engine = create_engine("sqlite://")
    db.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


def test_admin_school_is_optional():
    assert AdminUsers.__table__.c.SchoolId.nullable is True


def test_competition_admin_divisions_table_shape():
    t = CompetitionAdminDivisions.__table__
    assert {c.name for c in t.columns} == {"Id", "AdminId", "Division"}
    assert t.c.AdminId.nullable is False and t.c.Division.nullable is False


def test_can_store_competition_admin_with_divisions(session):
    admin = AdminUsers(Firstname="C", Lastname="A", Email="c@x", SchoolId=None, Role=2)
    session.add(admin)
    session.flush()
    session.add_all([CompetitionAdminDivisions(AdminId=admin.Id, Division="Gold")])
    session.commit()
    rows = session.query(CompetitionAdminDivisions).filter_by(AdminId=admin.Id).all()
    assert sorted(r.Division for r in rows) == ["Gold"]
