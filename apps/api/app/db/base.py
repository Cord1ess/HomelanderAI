"""SQLAlchemy Declarative Base class."""

import enum

from sqlalchemy import Enum
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""

    pass


def pg_enum(enum_class: type[enum.Enum], name: str) -> Enum:
    """A native Postgres enum column, spelled with the member *values*.

    Without `values_callable` SQLAlchemy sends the member names, so a Python
    `SUBMITTED` reaches a Postgres type that only holds `submitted` and the
    insert fails. `create_type=False` because db/schema.sql already creates
    every type — the migration runs that file, so nothing here should try again.
    """
    return Enum(
        enum_class,
        name=name,
        native_enum=True,
        create_type=False,
        values_callable=lambda obj: [e.value for e in obj],
    )
