import pytest

from app.core.config import _parse_cors_origins


@pytest.mark.parametrize(
    ("raw", "frontend_url", "expected"),
    [
        (None, "http://localhost", ["http://localhost"]),
        ("", "http://localhost", ["http://localhost"]),
        ("*", "http://localhost", ["*"]),
        (
            '["https://kiboagenda.com","https://www.kiboagenda.com"]',
            "http://localhost",
            ["https://kiboagenda.com", "https://www.kiboagenda.com"],
        ),
        (
            "https://a.com, https://b.com",
            "http://localhost",
            ["https://a.com", "https://b.com"],
        ),
    ],
)
def test_parse_cors_origins(raw, frontend_url, expected):
    assert _parse_cors_origins(raw, frontend_url) == expected
