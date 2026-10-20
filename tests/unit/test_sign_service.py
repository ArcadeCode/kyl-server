from unittest import mock

import bcrypt
import pytest

import services.sign as sign
from services.sign import compare_password, create_hash, fake_verify


def _cost(bcrypt_hash: str) -> str:
    # "$2b$12$<salt+hash>" -> "12"
    return bcrypt_hash.split("$")[2]


class TestCreateHash:
    def test_returns_a_bcrypt_string_hash(self):
        h = create_hash("abc12")
        assert isinstance(h, str)
        assert h.startswith("$2b$")
        assert len(h) == 60

    def test_hash_is_not_the_password(self):
        assert "abc12" not in create_hash("abc12")

    def test_same_password_gives_different_hashes(self):
        assert create_hash("abc12") != create_hash("abc12")

    def test_hash_verifies_with_bcrypt(self):
        assert bcrypt.checkpw(b"abc12", create_hash("abc12").encode())

    def test_accepts_exactly_72_bytes(self):
        create_hash("a" * 72)

    def test_rejects_more_than_72_bytes(self):
        with pytest.raises(ValueError):
            create_hash("a" * 73)

    def test_limit_is_in_bytes_not_characters(self):
        # 37 x "é" = 37 characters but 74 bytes in UTF-8
        with pytest.raises(ValueError):
            create_hash("é" * 37)


class TestComparePassword:
    def test_valid_password(self):
        old = create_hash("abc12")
        is_valid, new_hash = compare_password("abc12", old)
        assert is_valid is True
        assert new_hash is not None

    def test_valid_password_returns_a_fresh_working_hash(self):
        old = create_hash("abc12")
        _, new_hash = compare_password("abc12", old)
        assert new_hash != old
        assert compare_password("abc12", new_hash)[0] is True

    def test_wrong_password(self):
        assert compare_password("wrong1", create_hash("abc12")) == (False, None)

    def test_password_is_case_sensitive(self):
        assert compare_password("ABC12", create_hash("abc12")) == (False, None)

    def test_empty_password(self):
        assert compare_password("", create_hash("abc12")) == (False, None)

    def test_too_long_password_is_refused_without_raising(self):
        assert compare_password("a" * 100, create_hash("abc12")) == (False, None)

    def test_too_long_password_never_reaches_bcrypt(self):
        # Defence in depth: an older bcrypt silently truncates at 72 bytes, which would
        # accept "<72 right bytes>garbage". The guard must run before bcrypt is called.
        with mock.patch.object(sign.bcrypt, "checkpw") as checkpw:
            assert compare_password("a1" * 36 + "garbage", create_hash("a1" * 36)) == (False, None)
        checkpw.assert_not_called()

    @pytest.mark.parametrize("bad_hash", ["", "not-a-hash", "$2b$12$tooshort"])
    def test_malformed_hash_is_refused_without_raising(self, bad_hash):
        assert compare_password("abc12", bad_hash) == (False, None)


class TestFakeVerify:
    """fake_verify must cost the same as a real check, otherwise it protects nothing."""

    def setup_method(self):
        sign._dummy_hash.cache_clear()

    def test_returns_nothing(self):
        assert fake_verify("whatever1") is None

    def test_really_runs_bcrypt(self):
        with mock.patch.object(sign.bcrypt, "checkpw", wraps=bcrypt.checkpw) as checkpw:
            fake_verify("whatever1")
        checkpw.assert_called_once()

    def test_dummy_hash_is_a_valid_hash_with_the_real_cost(self):
        dummy = sign._dummy_hash()
        assert bcrypt.checkpw(b"not-a-real-password-1", dummy.encode())
        assert _cost(dummy) == _cost(create_hash("abc12"))

    def test_dummy_hash_is_computed_only_once(self):
        with mock.patch.object(sign, "create_hash", wraps=create_hash) as spy:
            fake_verify("a1")
            fake_verify("b2")
            fake_verify("c3")
        assert spy.call_count == 1
