#!/usr/bin/env python3
"""Fetch GitHub stargazer timestamps and render repository-owned SVG charts."""
from __future__ import annotations

import argparse
import json
import math
import os
from collections import Counter
from datetime import date, datetime
from html import escape
from pathlib import Path
from typing import Callable
from urllib.request import Request, urlopen


GRAPHQL_URL = "https://api.github.com/graphql"
GRAPHQL_QUERY = """
query StarHistory($owner: String!, $name: String!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    stargazerCount
    stargazers(
      first: 100
      after: $cursor
      orderBy: {field: STARRED_AT, direction: ASC}
    ) {
      edges { starredAt }
      pageInfo { hasNextPage endCursor }
    }
  }
}
"""

THEMES = {
    "light": {
        "background": "#ffffff",
        "grid": "#d8dee4",
        "text": "#1f2328",
        "muted": "#59636e",
        "line": "#0969da",
        "fill": "#ddf4ff",
    },
    "dark": {
        "background": "#0d1117",
        "grid": "#30363d",
        "text": "#f0f6fc",
        "muted": "#8b949e",
        "line": "#58a6ff",
        "fill": "#122d45",
    },
}


def build_daily_series(starred_at: list[str]) -> list[tuple[date, int]]:
    """Convert stargazer timestamps into cumulative daily totals."""
    counts = Counter(
        datetime.fromisoformat(timestamp.replace("Z", "+00:00")).date()
        for timestamp in starred_at
    )
    total = 0
    series: list[tuple[date, int]] = []
    for day in sorted(counts):
        total += counts[day]
        series.append((day, total))
    return series or [(date.today(), 0)]


def _request_graphql(token: str, variables: dict) -> dict:
    body = json.dumps({"query": GRAPHQL_QUERY, "variables": variables}).encode("utf-8")
    request = Request(
        GRAPHQL_URL,
        data=body,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "joinquant-skill-star-history",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="POST",
    )
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_starred_at(
    repository: str,
    token: str,
    *,
    request_json: Callable[[str, dict], dict] = _request_graphql,
) -> list[str]:
    """Fetch every current stargazer timestamp through GitHub GraphQL."""
    parts = repository.split("/", 1)
    if len(parts) != 2 or not all(parts):
        raise ValueError("repository must use the owner/name form")
    if not token:
        raise ValueError("GITHUB_TOKEN is required")

    owner, name = parts
    cursor: str | None = None
    timestamps: list[str] = []
    expected_count: int | None = None

    while True:
        payload = request_json(token, {"owner": owner, "name": name, "cursor": cursor})
        if payload.get("errors"):
            messages = "; ".join(str(item.get("message", item)) for item in payload["errors"])
            raise RuntimeError(f"GitHub GraphQL error: {messages}")

        repository_data = payload.get("data", {}).get("repository")
        if repository_data is None:
            raise RuntimeError(f"repository not found or not readable: {repository}")

        expected_count = int(repository_data["stargazerCount"])
        connection = repository_data["stargazers"]
        timestamps.extend(edge["starredAt"] for edge in connection["edges"])
        page_info = connection["pageInfo"]
        if not page_info["hasNextPage"]:
            break
        next_cursor = page_info["endCursor"]
        if not next_cursor or next_cursor == cursor:
            raise RuntimeError("GitHub returned an invalid stargazer cursor")
        cursor = next_cursor

    if expected_count is not None and len(timestamps) != expected_count:
        raise RuntimeError(
            f"GitHub reported {expected_count} stars but returned {len(timestamps)} timestamps"
        )
    return timestamps


def _nice_ceiling(value: int) -> int:
    if value <= 1:
        return 1
    magnitude = 10 ** math.floor(math.log10(value))
    normalized = value / magnitude
    step = 1 if normalized <= 1 else 2 if normalized <= 2 else 5 if normalized <= 5 else 10
    return step * magnitude


def render_svg(repository: str, series: list[tuple[date, int]], *, theme: str) -> str:
    """Render a compact, dependency-free star history SVG."""
    if theme not in THEMES:
        raise ValueError(f"unsupported theme: {theme}")
    if not series:
        raise ValueError("series must contain at least one point")

    colors = THEMES[theme]
    width, height = 800, 360
    left, right, top, bottom = 72, 24, 64, 58
    plot_width = width - left - right
    plot_height = height - top - bottom
    first_day, last_day = series[0][0], series[-1][0]
    day_span = max((last_day - first_day).days, 1)
    y_max = _nice_ceiling(max(count for _, count in series))

    def x_position(day: date) -> float:
        return left + ((day - first_day).days / day_span) * plot_width

    def y_position(count: int) -> float:
        return top + plot_height - (count / y_max) * plot_height

    points = [(x_position(day), y_position(count)) for day, count in series]
    line_path = " ".join(
        ("M" if index == 0 else "L") + f" {x:.2f} {y:.2f}"
        for index, (x, y) in enumerate(points)
    )
    area_path = (
        f"M {points[0][0]:.2f} {top + plot_height:.2f} "
        + " ".join(f"L {x:.2f} {y:.2f}" for x, y in points)
        + f" L {points[-1][0]:.2f} {top + plot_height:.2f} Z"
    )

    y_ticks = [round(y_max * index / 4) for index in range(5)]
    x_tick_days = []
    for index in range(5):
        day = first_day.fromordinal(first_day.toordinal() + round(day_span * index / 4))
        if day not in x_tick_days:
            x_tick_days.append(day)

    escaped_repository = escape(repository)
    total = series[-1][1]
    grid_lines = []
    for tick in y_ticks:
        y = y_position(tick)
        grid_lines.append(
            f'<line x1="{left}" y1="{y:.2f}" x2="{width - right}" y2="{y:.2f}" '
            f'stroke="{colors["grid"]}" stroke-width="1" />'
        )
        grid_lines.append(
            f'<text x="{left - 12}" y="{y + 4:.2f}" text-anchor="end" '
            f'fill="{colors["muted"]}" font-size="12">{tick}</text>'
        )

    x_labels = []
    for day in x_tick_days:
        x = x_position(day)
        x_labels.append(
            f'<text x="{x:.2f}" y="{height - 24}" text-anchor="middle" '
            f'fill="{colors["muted"]}" font-size="12">{day.isoformat()}</text>'
        )

    return "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
            f'<title id="title">{escaped_repository} Star History</title>',
            f'<desc id="desc">Cumulative GitHub stars from {first_day.isoformat()} to '
            f'{last_day.isoformat()}: {total} stars.</desc>',
            f'<rect width="{width}" height="{height}" rx="12" fill="{colors["background"]}" />',
            f'<text x="{left}" y="32" fill="{colors["text"]}" font-family="Segoe UI, sans-serif" '
            f'font-size="20" font-weight="600">{escaped_repository}</text>',
            f'<text x="{width - right}" y="32" text-anchor="end" fill="{colors["line"]}" '
            f'font-family="Segoe UI, sans-serif" font-size="20" font-weight="600">{total} Stars</text>',
            f'<g font-family="Segoe UI, sans-serif">',
            *grid_lines,
            f'<path d="{area_path}" fill="{colors["fill"]}" />',
            f'<path d="{line_path}" fill="none" stroke="{colors["line"]}" '
            'stroke-width="3" stroke-linecap="round" stroke-linejoin="round" />',
            *x_labels,
            "</g>",
            "</svg>",
            "",
        ]
    )


def write_charts(
    repository: str,
    starred_at: list[str],
    output_dir: Path,
) -> tuple[Path, Path]:
    """Write light and dark SVG charts and return their paths."""
    output_dir.mkdir(parents=True, exist_ok=True)
    series = build_daily_series(starred_at)
    light = output_dir / "star-history-light.svg"
    dark = output_dir / "star-history-dark.svg"
    light.write_text(render_svg(repository, series, theme="light"), encoding="utf-8")
    dark.write_text(render_svg(repository, series, theme="dark"), encoding="utf-8")
    return light, dark


def main() -> int:
    parser = argparse.ArgumentParser(description="Update repository-owned GitHub star history charts")
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument("--output-dir", type=Path, default=Path("assets"))
    args = parser.parse_args()

    if not args.repo:
        parser.error("--repo or GITHUB_REPOSITORY is required")
    token = os.environ.get("GITHUB_TOKEN", "")
    starred_at = fetch_starred_at(args.repo, token)
    light, dark = write_charts(args.repo, starred_at, args.output_dir)
    print(f"Updated {light} and {dark} with {len(starred_at)} stars")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
