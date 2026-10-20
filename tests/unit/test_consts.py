import re
from datetime import timedelta

import pytest

from consts import (
    EMAIL_MAX_LENGTH,
    EMAIL_REGEX,
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_LENGTH,
    PASSWORD_REGEX,
    TOKEN_LIFESPAN,
)


def password_ok(value: str) -> bool:
    return re.fullmatch(PASSWORD_REGEX, value) is not None


def email_ok(value: str) -> bool:
    return re.fullmatch(EMAIL_REGEX, value) is not None


class TestPasswordRegex:
    @pytest.mark.parametrize(
        "value", ["abc12", "Abc12", "12abc", "a1" * 36, "Abc12!@#$%*?&", "x" * 71 + "1"]
    )
    def test_accepted(self, value):
        assert password_ok(value)

    @pytest.mark.parametrize(
        "value, why",
        [
            ("ab12", "too short"),
            ("abcde", "no digit"),
            ("12345", "no letter"),
            ("abc 12", "space"),
            ("abc12\n", "trailing newline"),
            ("abç12", "non ASCII"),
            ("abc-12", "forbidden character"),
            ("", "empty"),
        ],
    )
    def test_refused(self, value, why):
        assert not password_ok(value), why

    def test_bounds_match_the_constants(self):
        valid = "a1" + "b" * (PASSWORD_MIN_LENGTH - 2)
        assert password_ok(valid)
        assert not password_ok(valid[:-1])

        longest = "a1" + "b" * (PASSWORD_MAX_LENGTH - 2)
        assert password_ok(longest)
        assert not password_ok(longest + "b")

    def test_max_length_is_the_bcrypt_limit(self):
        assert PASSWORD_MAX_LENGTH == 72


class TestEmailRegex:
    @pytest.mark.parametrize(
        "value", ["a@b.fr", "first.last+tag@sub.example.com", "a_b-c@ex-ample.org"]
    )
    def test_accepted(self, value):
        assert email_ok(value)

    @pytest.mark.parametrize(
        "value", ["", "plain", "a@b", "@b.fr", "a@.fr", "a b@c.fr", "a@b.fr\n", "a@@b.fr"]
    )
    def test_refused(self, value):
        assert not email_ok(value)

    def test_max_length_is_the_rfc_limit(self):
        assert EMAIL_MAX_LENGTH == 254


def test_token_lifespan_is_one_month_fixed():
    assert TOKEN_LIFESPAN == timedelta(days=30)
