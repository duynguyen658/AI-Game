from sqlalchemy.exc import IntegrityError

from app.database.integrity import get_constraint_name


class Diag:
    constraint_name = "uq_example"


class Orig:
    diag = Diag()


def test_get_constraint_name_reads_postgres_diag() -> None:
    exc = IntegrityError("statement", {}, Orig())

    assert get_constraint_name(exc) == "uq_example"


def test_get_constraint_name_handles_missing_diag() -> None:
    exc = IntegrityError("statement", {}, object())

    assert get_constraint_name(exc) is None
