"""Family-facing public HTML completeness gate.

This gate is intentionally stricter than the generic export gate.  The generic gate
validates render hygiene; this one validates the family publishing contract when a
trip declares ``family-public-contract.yaml``.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser


DEFAULT_RESTAURANT_FIELDS = [
    "菜系",
    "距離",
    "來源",
    "地圖",
    "特色",
    "為什麼選",
    "招牌",
    "人均",
]

DEFAULT_FORBIDDEN_TOKENS = [
    "C:/",
    "C:\\",
    "_travelwork",
    ".claude",
    "poi_id",
    "must_do",
]

_SAFE_IMG_SRC = re.compile(r"(?i)^(data:image/|https://)")
_VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input",
              "link", "meta", "param", "source", "track", "wbr"}


class _FamilyHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.class_stack: list[tuple[str, set[str]]] = []
        self.images: list[str] = []
        self.photo_credit_count = 0
        self.location_keys: list[str] = []
        self.day_labels: list[str] = []
        self.meal_stack: list[str] = []
        self.meal_cards: dict[str, int] = {}
        self.provided_meals: list[str] = []
        self.restaurant_stack: list[str] = []
        self.restaurant_text: dict[str, list[str]] = {}
        self._current_h2 = False
        self._current_restaurant: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {k: v or "" for k, v in attrs}
        classes = set(attr.get("class", "").split())
        if tag not in _VOID_TAGS:
            self.class_stack.append((tag, classes))

        if tag == "img":
            self.images.append(attr.get("src", ""))
        if "photo-credit" in classes:
            self.photo_credit_count += 1
        if attr.get("data-location-key"):
            self.location_keys.append(attr["data-location-key"])
        if "meal-options" in classes:
            meal_id = attr.get("data-meal-id", "")
            self.meal_stack.append(meal_id)
            self.meal_cards.setdefault(meal_id, 0)
        if "provided-meal" in classes or attr.get("data-meal-provided"):
            meal_id = attr.get("data-meal-id", "")
            if meal_id:
                self.provided_meals.append(meal_id)
        if "restaurant-card" in classes:
            rid = attr.get("data-restaurant-id", f"restaurant-{len(self.restaurant_text) + 1}")
            if self.meal_stack:
                self.meal_cards[self.meal_stack[-1]] += 1
            self.restaurant_stack.append(rid)
            self._current_restaurant = rid
            self.restaurant_text.setdefault(rid, [])
        if tag == "h2":
            self._current_h2 = True

    def handle_endtag(self, tag: str) -> None:
        classes: set[str] = set()
        while self.class_stack:
            open_tag, open_classes = self.class_stack.pop()
            classes = open_classes
            if open_tag == tag:
                break
        if "meal-options" in classes and self.meal_stack:
            self.meal_stack.pop()
        if "restaurant-card" in classes and self.restaurant_stack:
            self.restaurant_stack.pop()
            self._current_restaurant = self.restaurant_stack[-1] if self.restaurant_stack else None
        if tag == "h2":
            self._current_h2 = False

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if not text:
            return
        if self._current_h2:
            self.day_labels.append(text)
        if self._current_restaurant:
            self.restaurant_text[self._current_restaurant].append(text)


def _as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def run_family_public_gate(html_text: str, contract: dict | None = None) -> dict:
    """Return a gate-report-shaped result for family-facing public HTML.

    Contract keys:
      - min_days: expected number of day headings.
      - expected_location_keys: every key must appear as data-location-key.
      - required_meal_ids: every id must appear as data-meal-id in a meal-options block.
      - provided_meal_ids: every id must appear as a provided-meal block.
      - required_restaurant_fields: text labels required inside every restaurant card.
      - forbidden_tokens: internal tokens banned from the public page.
    """
    contract = contract or {}
    failures: list[str] = []
    html_text = html_text or ""

    forbidden = _as_list(contract.get("forbidden_tokens")) or DEFAULT_FORBIDDEN_TOKENS
    leaked = [token for token in forbidden if token and token in html_text]
    if leaked:
        failures.append(f"internal tokens leaked into family public HTML: {', '.join(leaked)}")
    if "<script" in html_text.lower():
        failures.append("raw <script> in family public HTML")

    parser = _FamilyHtmlParser()
    parser.feed(html_text)

    unsafe_imgs = [src for src in parser.images if not _SAFE_IMG_SRC.match(src or "")]
    if unsafe_imgs:
        failures.append(f"unsafe family <img src>: {unsafe_imgs[0]}")

    min_days = contract.get("min_days")
    day_labels = [label for label in parser.day_labels if label.startswith("D")]
    if min_days is not None and len(day_labels) < int(min_days):
        failures.append(f"too few family day labels: {len(day_labels)} < {min_days}")

    expected_locations = set(_as_list(contract.get("expected_location_keys")))
    missing_locations = sorted(expected_locations - set(parser.location_keys))
    if missing_locations:
        failures.append(f"missing family location photo keys: {', '.join(missing_locations)}")

    if parser.images and parser.photo_credit_count < len(parser.images):
        failures.append(
            f"family photo credits fewer than images: {parser.photo_credit_count} < {len(parser.images)}"
        )

    required_meals = set(_as_list(contract.get("required_meal_ids")))
    missing_meals = sorted(required_meals - set(parser.meal_cards))
    if missing_meals:
        failures.append(f"missing family meal option blocks: {', '.join(missing_meals)}")

    wrong_counts = {meal: count for meal, count in parser.meal_cards.items() if count != 3}
    if wrong_counts:
        parts = [f"{meal}={count}" for meal, count in sorted(wrong_counts.items())]
        failures.append(f"family meal blocks without exactly 3 restaurant cards: {', '.join(parts)}")

    provided_required = set(_as_list(contract.get("provided_meal_ids")))
    missing_provided = sorted(provided_required - set(parser.provided_meals))
    if missing_provided:
        failures.append(f"missing family provided-meal blocks: {', '.join(missing_provided)}")

    required_fields = _as_list(contract.get("required_restaurant_fields")) or DEFAULT_RESTAURANT_FIELDS
    bad_restaurants: list[str] = []
    for rid, chunks in parser.restaurant_text.items():
        joined = "\n".join(chunks)
        missing = [field for field in required_fields if field not in joined]
        if missing:
            bad_restaurants.append(f"{rid} missing {','.join(missing)}")
    if bad_restaurants:
        failures.append(f"family restaurant cards missing required fields: {'; '.join(bad_restaurants)}")

    checks = [
        {"name": "no_internal_tokens", "passed": not leaked},
        {"name": "no_raw_script", "passed": "<script" not in html_text.lower()},
        {"name": "img_src_safe", "passed": not unsafe_imgs},
        {"name": "day_labels", "passed": not any("day labels" in f for f in failures)},
        {"name": "location_photos", "passed": not missing_locations},
        {"name": "photo_credits", "passed": not any("photo credits" in f for f in failures)},
        {"name": "meal_options", "passed": not missing_meals and not wrong_counts},
        {"name": "provided_meals", "passed": not missing_provided},
        {"name": "restaurant_detail", "passed": not bad_restaurants},
    ]
    return {
        "status": "pass" if not failures else "fail",
        "distributable": True,
        "retryable": not failures,
        "checks": checks,
        "failures": failures,
    }
