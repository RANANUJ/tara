import sqlite3


def test_auth_migration_creates_owner_and_session_indexes(database, database_path) -> None:
    with sqlite3.connect(database_path) as connection:
        indexes = {row[1] for row in connection.execute("PRAGMA index_list('owner_sessions')")}
    assert {"ix_owner_sessions_owner_active", "ix_owner_sessions_expiry"}.issubset(indexes)
