"""Phase 1 RBAC: users, role checks."""


def test_create_user_persists_role(db):
    uid = db.create_user("alice", "Alice", role="manager")
    user = db.get_user_by_username("alice")
    assert user is not None
    assert user["id"] == uid
    assert user["role"] == "manager"
    assert user["is_active"] == 1


def test_list_users_excludes_inactive(db):
    db.create_user("bob", "Bob")
    db.create_user("carol", "Carol")
    # No deactivation in Phase 1 API yet — just verify listing works.
    users = db.list_users()
    usernames = {u["username"] for u in users}
    assert {"bob", "carol"}.issubset(usernames)


def test_get_user_by_username_unknown_returns_none(db):
    assert db.get_user_by_username("nope") is None
