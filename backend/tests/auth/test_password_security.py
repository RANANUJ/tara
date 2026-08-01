from tara_api.auth.security import Argon2idPasswordHasher


def test_argon2id_hashes_and_verifies_without_plaintext() -> None:
    hasher = Argon2idPasswordHasher(time_cost=1, memory_cost=8192)
    password_hash = hasher.hash("correct horse battery staple")
    assert password_hash.startswith("$argon2id$")
    assert "correct horse battery staple" not in password_hash
    assert hasher.verify(password_hash, "correct horse battery staple") is True
    assert hasher.verify(password_hash, "wrong password here") is False
