from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for all platform tables. Models land via 01-postgres-schema.md."""
