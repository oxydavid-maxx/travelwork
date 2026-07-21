from scripts.family_public_gate import run_family_public_gate


FIELDS = "菜系 距離 來源 地圖 特色 為什麼選 招牌 人均"


def _restaurant(i: int) -> str:
    return (
        f'<article class="restaurant-card" data-restaurant-id="r{i}">'
        f"<h3>Restaurant {i}</h3><p>{FIELDS}</p></article>"
    )


def _valid_html() -> str:
    return f"""
    <h2>D1 8/1（週六）</h2>
    <figure class="place-card" data-location-key="station">
      <img src="https://img.example/station.jpg" alt="station">
      <figcaption class="photo-credit">photo source</figcaption>
    </figure>
    <section class="meal-options" data-meal-id="lunch">
      {_restaurant(1)}{_restaurant(2)}{_restaurant(3)}
    </section>
    <section class="provided-meal" data-meal-id="hotel-breakfast" data-meal-provided="lodging">
      <img src="https://img.example/breakfast.jpg" alt="breakfast">
      <p class="photo-credit">photo source</p>
    </section>
    """


def test_family_public_gate_passes_complete_contract():
    contract = {
        "min_days": 1,
        "expected_location_keys": ["station"],
        "required_meal_ids": ["lunch"],
        "provided_meal_ids": ["hotel-breakfast"],
    }
    report = run_family_public_gate(_valid_html(), contract)
    assert report["status"] == "pass", report["failures"]
    assert report["retryable"] is True


def test_family_public_gate_fails_missing_location_and_meal_cards():
    contract = {
        "min_days": 1,
        "expected_location_keys": ["airport"],
        "required_meal_ids": ["dinner"],
    }
    report = run_family_public_gate(_valid_html(), contract)
    assert report["status"] == "fail"
    assert report["retryable"] is False
    assert any("missing family location photo keys: airport" in f for f in report["failures"])
    assert any("missing family meal option blocks: dinner" in f for f in report["failures"])


def test_family_public_gate_fails_restaurant_missing_required_fields():
    html = """
    <h2>D1 8/1（週六）</h2>
    <figure data-location-key="station"><img src="https://img.example/station.jpg"><p class="photo-credit">x</p></figure>
    <section class="meal-options" data-meal-id="lunch">
      <article class="restaurant-card" data-restaurant-id="r1">菜系 距離</article>
      <article class="restaurant-card" data-restaurant-id="r2">菜系 距離</article>
      <article class="restaurant-card" data-restaurant-id="r3">菜系 距離</article>
    </section>
    """
    report = run_family_public_gate(html, {"required_meal_ids": ["lunch"]})
    assert report["status"] == "fail"
    assert any("restaurant cards missing required fields" in f for f in report["failures"])


def test_family_public_gate_fails_without_visible_photo_credit():
    html = '<h2>D1 8/1（週六）</h2><img src="https://img.example/a.jpg" alt="a">'
    report = run_family_public_gate(html, {"min_days": 1})
    assert report["status"] == "fail"
    assert any("photo credits fewer than images" in f for f in report["failures"])
