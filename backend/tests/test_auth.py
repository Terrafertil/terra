from __future__ import annotations

import unittest
from unittest.mock import patch

from app import auth


class AuthTokenTests(unittest.TestCase):
    def test_hs256_token_round_trip_with_pyjwt(self):
        with patch.object(auth.settings, "secret_key", "test-secret-with-32-characters-min"):
            token = auth.criar_token("usuario-teste", {"role": "admin"})
            payload = auth._decodar(token)

        self.assertEqual(payload["sub"], "usuario-teste")
        self.assertEqual(payload["role"], "admin")
        self.assertIn("exp", payload)


if __name__ == "__main__":
    unittest.main()
