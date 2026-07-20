from sqlalchemy.exc import IntegrityError


def get_constraint_name(exc: IntegrityError) -> str | None:
    current: object | None = exc.orig
    seen: set[int] = set()

    while current is not None and id(current) not in seen:
        seen.add(id(current))
        diagnostic_name = getattr(
            getattr(current, "diag", None), "constraint_name", None
        )
        constraint_name = diagnostic_name or getattr(current, "constraint_name", None)
        if isinstance(constraint_name, str):
            return constraint_name
        current = getattr(current, "__cause__", None) or getattr(
            current, "__context__", None
        )

    return None
