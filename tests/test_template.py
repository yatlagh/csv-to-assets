import json

import pytest

from csv_to_assets.template import TemplateError, bind, load_template, parse_template


def test_load_shipped_templates(root):
    for name in ("card", "banner"):
        t = load_template(root / "templates" / f"{name}.json")
        assert t.name == name
        assert t.width > 0 and t.height > 0
        assert {"title", "subtitle", "color", "cover_image"} <= t.required_columns()
        assert all(el.type in {"rect", "image", "text", "pill"} for el in t.elements)


def test_bind_substitutes_columns_and_reports_missing():
    row = {"title": "Night Sky", "color": "#112233"}
    assert bind("{title} ({color})", row) == "Night Sky (#112233)"
    assert bind(42, row) == 42
    with pytest.raises(KeyError, match="not in the CSV"):
        bind("{missing}", row)


@pytest.mark.parametrize(
    "data, message",
    [
        ({"elements": []}, "missing required key 'size'"),
        ({"size": [600, 800], "elements": [{"type": "blob", "box": [0, 0, 1, 1]}]}, "unknown type"),
        ({"size": [600, 800], "elements": [{"type": "text", "box": [0, 0, 1, 1]}]}, "needs a 'text'"),
        ({"size": [600, 800], "elements": [{"type": "rect", "box": [10, 10, 5, 20]}]}, "positive width"),
        ({"size": [600, 800], "elements": [{"type": "text", "box": [0, 0, 1, 1], "text": "x", "align": "top"}]}, "'align'"),
    ],
)
def test_parse_template_rejects_bad_input(data, message):
    with pytest.raises(TemplateError, match=message):
        parse_template(data)


def test_scale_for_fits_inside_target(tmp_path):
    p = tmp_path / "t.json"
    p.write_text(json.dumps({"size": [600, 800], "elements": []}))
    t = load_template(p)
    assert t.scale_for(None) == 1.0
    assert t.scale_for((300, 400)) == 0.5
    assert t.scale_for((1200, 800)) == 1.0  # height-limited
