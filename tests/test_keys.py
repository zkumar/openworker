"""Per-tenant API keys: hashed at rest, revocable, and rotation-friendly."""

import pathlib
import sqlite3

from coworker.auth.keys import KeyStore


def _store(tmp_path) -> KeyStore:
    return KeyStore(str(pathlib.Path(tmp_path) / "keys.sqlite"))


def test_a_minted_key_authenticates_its_tenant(tmp_path):
    ks = _store(tmp_path)
    key, _ = ks.mint("medtech.demo", "ui")
    assert ks.verify(key) == "medtech.demo"


def test_an_unknown_key_does_not_authenticate(tmp_path):
    ks = _store(tmp_path)
    ks.mint("a", "")
    assert ks.verify("ow_deadbeef") is None
    assert ks.verify("") is None


def test_a_revoked_key_stops_authenticating_immediately(tmp_path):
    ks = _store(tmp_path)
    key, kid = ks.mint("a", "")
    assert ks.verify(key) == "a"
    assert ks.revoke(kid) is True
    assert ks.verify(key) is None, "a revoked key must not authenticate"
    assert ks.revoke(kid) is False, "revoking twice is a no-op, not a second success"


def test_the_plaintext_key_is_never_stored(tmp_path):
    ks = _store(tmp_path)
    key, _ = ks.mint("a", "label")
    con = sqlite3.connect(str(pathlib.Path(tmp_path) / "keys.sqlite"))
    dump = " ".join(str(r) for r in con.execute("SELECT * FROM api_key").fetchall())
    assert key not in dump, "the key must be stored hashed only"
    assert key[:20] not in dump


def test_listing_never_returns_key_material(tmp_path):
    ks = _store(tmp_path)
    ks.mint("a", "x")
    row = ks.list()[0]
    assert set(row) == {"id", "tenant", "label", "created_at", "revoked", "last_used_at",
                        "role", "expires_at", "expired"}


def test_rotation_keeps_both_keys_valid_until_the_old_one_is_revoked(tmp_path):
    ks = _store(tmp_path)
    old, old_id = ks.mint("a", "old")
    new, _ = ks.mint("a", "new")
    assert ks.verify(old) == "a" and ks.verify(new) == "a", "overlap avoids a hard cutover"
    ks.revoke(old_id)
    assert ks.verify(old) is None and ks.verify(new) == "a"


def test_an_existing_env_token_is_adopted_without_lockout(tmp_path):
    ks = _store(tmp_path)
    assert ks.adopt("devtoken-loop", "default") is not None
    assert ks.verify("devtoken-loop") == "default"
    before = ks.count()
    ks.adopt("devtoken-loop")           # idempotent
    assert ks.count() == before


def test_a_key_can_carry_a_role(tmp_path):
    ks = _store(tmp_path)
    admin_key, _ = ks.mint("t", "ops", role="admin")
    agent_key, _ = ks.mint("t", "svc")
    assert ks.authenticate(admin_key)["role"] == "admin"
    assert ks.authenticate(agent_key)["role"] == "agent"


def test_an_expired_key_stops_authenticating(tmp_path):
    ks = _store(tmp_path)
    key, _ = ks.mint("t", "short", ttl_days=-1)      # already past
    assert ks.authenticate(key) is None, "an expired key must not authenticate"
    live, _ = ks.mint("t", "live", ttl_days=7)
    assert ks.authenticate(live)["tenant"] == "t"
    assert [k["expired"] for k in ks.list() if k["tenant"] == "t"][-1] in (False, True)


def test_an_adopted_env_token_is_admin(tmp_path):
    ks = _store(tmp_path)
    ks.adopt("legacy-token")
    assert ks.authenticate("legacy-token")["role"] == "admin", \
        "the operator credential must be able to manage keys"


def test_listing_reports_expiry_state(tmp_path):
    ks = _store(tmp_path)
    ks.mint("t", "short", ttl_days=-1)
    ks.mint("t", "fine", ttl_days=7)
    flags = sorted(k["expired"] for k in ks.list())
    assert flags == [False, True]
