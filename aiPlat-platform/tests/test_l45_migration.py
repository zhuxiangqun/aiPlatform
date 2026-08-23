"""Dynamic tests for L4.5 DB schema migration (plan-app-factory-l45 §3.3/§3.4/§3.5)."""
import pytest

from builder.schema_migration import (
    extract_schema,
    diff_schema,
    generate_migration,
)


class TestSchemaExtractor:
    def test_sqlalchemy_model(self):
        code = {
            "models.py": (
                "class Base: pass\n"
                "class User(Base):\n"
                "    __tablename__ = 'users'\n"
                "    id = Column(Integer, primary_key=True)\n"
                "    name = Column(String, nullable=False)\n"
            ),
        }
        schema = extract_schema(code)
        assert "users" in schema
        assert schema["users"]["id"]["type"] == "INTEGER"
        assert schema["users"]["id"]["primary"] is True
        assert schema["users"]["name"]["type"] == "TEXT"
        assert schema["users"]["name"]["nullable"] is False

    def test_pydantic_model(self):
        code = {
            "schemas.py": (
                "class User(BaseModel):\n"
                "    id: int\n"
                "    name: str\n"
            ),
        }
        schema = extract_schema(code)
        assert "user" in schema
        assert schema["user"]["id"]["type"] == "INTEGER"
        assert schema["user"]["name"]["type"] == "TEXT"

    def test_no_models(self):
        assert extract_schema({"x.py": "def f(): pass\n"}) == {}


class TestSchemaDiff:
    def _schemas(self):
        old = {"users": {"id": {"type": "INTEGER"}, "name": {"type": "TEXT"}}}
        new = {"users": {"id": {"type": "INTEGER"}, "name": {"type": "TEXT"},
                        "verification_code": {"type": "TEXT"}}}
        return old, new

    def test_added_column_not_destructive(self):
        old, new = self._schemas()
        d = diff_schema(old, new)
        assert "verification_code" in d["added_columns"]["users"]
        assert d["destructive"] is False
        assert d["has_changes"] is True

    def test_removed_column_destructive(self):
        old, new = self._schemas()
        del new["users"]["verification_code"]
        new["users"].pop("name", None)
        d = diff_schema(old, new)
        assert "name" in d["removed_columns"]["users"]
        assert d["destructive"] is True

    def test_type_change_destructive(self):
        old, new = self._schemas()
        new["users"]["name"]["type"] = "INTEGER"
        d = diff_schema(old, new)
        assert "name" in d["type_changed"]["users"]
        assert d["destructive"] is True

    def test_no_changes(self):
        old, new = self._schemas()
        d = diff_schema(old, new)
        d2 = diff_schema(old, old)
        assert d2["has_changes"] is False and d2["destructive"] is False


class TestMigrationGenerator:
    def test_add_column_up_down_paired(self):
        old = {"users": {"id": {"type": "INTEGER"}}}
        new = {"users": {"id": {"type": "INTEGER"}, "code": {"type": "TEXT"}}}
        mig = generate_migration(diff_schema(old, new), "p1", new)
        assert mig is not None
        assert "ALTER TABLE users ADD COLUMN code TEXT" in mig["up_sql"]
        assert "ALTER TABLE users DROP COLUMN code" in mig["down_sql"]
        assert mig["destructive"] is False

    def test_removed_column_destructive(self):
        old = {"users": {"id": {"type": "INTEGER"}, "secret": {"type": "TEXT"}}}
        new = {"users": {"id": {"type": "INTEGER"}}}
        mig = generate_migration(diff_schema(old, new), "p1", new)
        assert mig is not None
        assert "ALTER TABLE users DROP COLUMN secret" in mig["up_sql"]
        assert mig["destructive"] is True

    def test_type_change_up_down(self):
        old = {"users": {"status": {"type": "INTEGER"}}}
        new = {"users": {"status": {"type": "TEXT"}}}
        mig = generate_migration(diff_schema(old, new), "p1", new)
        assert "ALTER TABLE users ALTER COLUMN status TYPE TEXT" in mig["up_sql"]
        assert "TYPE INTEGER" in mig["down_sql"]
        assert mig["destructive"] is True

    def test_no_changes_returns_none(self):
        old = {"users": {"id": {"type": "INTEGER"}}}
        assert generate_migration(diff_schema(old, old), "p1", old) is None

    def test_created_table(self):
        old = {}
        new = {"users": {"id": {"type": "INTEGER", "primary": True}}}
        mig = generate_migration(diff_schema(old, new), "p1", new)
        assert "CREATE TABLE users (id INTEGER PRIMARY KEY)" in mig["up_sql"]
        assert "DROP TABLE users" in mig["down_sql"]
