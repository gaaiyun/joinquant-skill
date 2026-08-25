"""Tests for the repository-owned GitHub star history chart."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from scripts.update_star_history import (
    build_daily_series,
    fetch_starred_at,
    render_svg,
    write_charts,
)


def test_build_daily_series_sorts_and_groups_same_day() -> None:
    starred_at = [
        "2026-05-03T10:00:00Z",
        "2026-05-01T12:00:00Z",
        "2026-05-03T18:00:00Z",
    ]

    assert build_daily_series(starred_at) == [
        (date(2026, 5, 1), 1),
        (date(2026, 5, 3), 3),
    ]


def test_fetch_starred_at_paginates_graphql_connection() -> None:
    calls: list[dict] = []

    def request_json(_token: str, variables: dict) -> dict:
        calls.append(variables)
        if variables["cursor"] is None:
            return {
                "data": {
                    "repository": {
                        "stargazerCount": 2,
                        "stargazers": {
                            "edges": [{"starredAt": "2026-05-01T12:00:00Z"}],
                            "pageInfo": {"hasNextPage": True, "endCursor": "next"},
                        },
                    }
                }
            }
        return {
            "data": {
                "repository": {
                    "stargazerCount": 2,
                    "stargazers": {
                        "edges": [{"starredAt": "2026-05-03T10:00:00Z"}],
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                    },
                }
            }
        }

    result = fetch_starred_at("gaaiyun/joinquant-skill", "token", request_json=request_json)

    assert result == ["2026-05-01T12:00:00Z", "2026-05-03T10:00:00Z"]
    assert [call["cursor"] for call in calls] == [None, "next"]
    assert all(call["owner"] == "gaaiyun" for call in calls)
    assert all(call["name"] == "joinquant-skill" for call in calls)


def test_render_svg_is_accessible_and_escapes_repository_name() -> None:
    svg = render_svg(
        "owner/repo&chart",
        [(date(2026, 5, 1), 1), (date(2026, 5, 3), 3)],
        theme="light",
    )

    assert svg.startswith("<svg")
    assert "<title id=\"title\">owner/repo&amp;chart Star History</title>" in svg
    assert "aria-labelledby=\"title desc\"" in svg
    assert "<path" in svg
    assert "3 Stars" in svg


def test_write_charts_creates_light_and_dark_svg(tmp_path: Path) -> None:
    light, dark = write_charts(
        "gaaiyun/joinquant-skill",
        ["2026-05-01T12:00:00Z", "2026-05-03T10:00:00Z"],
        tmp_path,
    )

    assert light == tmp_path / "star-history-light.svg"
    assert dark == tmp_path / "star-history-dark.svg"
    assert light.exists()
    assert dark.exists()
    assert light.read_text(encoding="utf-8") != dark.read_text(encoding="utf-8")
