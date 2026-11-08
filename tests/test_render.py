from PIL import Image

from csv_to_assets.render_pdf import render_pdf
from csv_to_assets.render_png import render_png
from csv_to_assets.template import load_template


def test_render_png_matches_requested_size(card_template, sample_csv, sample_row):
    t = load_template(card_template)
    img = render_png(t, sample_row, size=(300, 400), base_dir=sample_csv.parent)
    assert img.size == (300, 400)
    assert img.mode == "RGB"
    # The bottom panel is white in this template; the cover area is not.
    assert img.getpixel((150, 390)) == (255, 255, 255)
    assert img.getpixel((150, 100)) != (255, 255, 255)


def test_render_pdf_writes_single_page_with_text(card_template, sample_csv, sample_row, tmp_path):
    t = load_template(card_template)
    out = tmp_path / "card.pdf"
    render_pdf(t, sample_row, out, base_dir=sample_csv.parent)
    data = out.read_bytes()
    assert data.startswith(b"%PDF")
    assert b"/Count 1" in data  # exactly one page
    assert b"/MediaBox [ 0 0 600 800 ]" in data
    assert b"/FontFile2" in data  # embedded TrueType, so text is real text


def test_text_shrinks_instead_of_overflowing(card_template, sample_csv, sample_row):
    t = load_template(card_template)
    long_row = dict(sample_row, title="An Unreasonably Long Title That Must Wrap And Then Shrink To Fit The Box")
    img = render_png(t, long_row, base_dir=sample_csv.parent)
    assert isinstance(img, Image.Image)
    # Nothing should spill below the title box into the subtitle gutter row at y=714.
    assert all(img.getpixel((x, 714)) == (255, 255, 255) for x in range(40, 560, 8))
