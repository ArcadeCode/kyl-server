import re
from unittest import mock

from blake3 import blake3

import services.token as tokens
from services.token import generate_and_hash_token, hash_token, is_hash_valid


class TestHashToken:
    def test_is_64_lowercase_hex_chars(self):
        assert re.fullmatch(r"[0-9a-f]{64}", hash_token("some-key"))

    def test_is_blake3_256_of_the_utf8_key(self):
        assert hash_token("some-key") == blake3(b"some-key").hexdigest()

    def test_is_deterministic(self):
        assert hash_token("k") == hash_token("k")

    def test_differs_for_different_keys(self):
        assert hash_token("k1") != hash_token("k2")

    def test_hash_does_not_contain_the_key(self):
        assert "some-key" not in hash_token("some-key")


class TestGenerateAndHashToken:
    def test_returns_key_and_matching_hash(self):
        key, key_hash = generate_and_hash_token()
        assert key_hash == hash_token(key)

    def test_key_is_url_safe(self):
        key, _ = generate_and_hash_token()
        assert re.fullmatch(r"[A-Za-z0-9_-]+", key)

    def test_default_key_has_at_least_256_bits_of_entropy(self):
        key, _ = generate_and_hash_token()
        assert len(key) >= 43  # token_urlsafe(32) -> 43 chars

    def test_length_parameter_is_honoured(self):
        short, _ = generate_and_hash_token(length=16)
        long, _ = generate_and_hash_token(length=64)
        assert len(short) < len(long)

    def test_keys_are_unique(self):
        keys = {generate_and_hash_token()[0] for _ in range(500)}
        assert len(keys) == 500

    def test_raw_key_is_not_the_hash(self):
        key, key_hash = generate_and_hash_token()
        assert key != key_hash


class TestIsHashValid:
    def test_accepts_the_right_key(self):
        key, key_hash = generate_and_hash_token()
        assert is_hash_valid(key_hash, key) is True

    def test_rejects_another_key(self):
        _, key_hash = generate_and_hash_token()
        other_key, _ = generate_and_hash_token()
        assert is_hash_valid(key_hash, other_key) is False

    def test_rejects_the_hash_used_as_a_key(self):
        # Stealing the DB must not give usable credentials.
        key, key_hash = generate_and_hash_token()
        assert is_hash_valid(key_hash, key_hash) is False

    def test_rejects_empty_key(self):
        _, key_hash = generate_and_hash_token()
        assert is_hash_valid(key_hash, "") is False

    def test_comparison_is_constant_time(self):
        key, key_hash = generate_and_hash_token()
        with mock.patch.object(tokens.hmac, "compare_digest", wraps=tokens.hmac.compare_digest) as cmp:
            is_hash_valid(key_hash, key)
        cmp.assert_called_once()
