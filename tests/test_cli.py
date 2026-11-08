from csv_to_assets.cli import main


def test_cli_generate_smoke(sample_csv, card_template, tmp_path, capsys):
    out = tmp_path / "out"
    code = main([
        "generate", "--csv", str(sample_csv), "--template", str(card_template),
        "--out", str(out), "--formats", "png,pdf", "--size", "150x200",
        "--workers", "2", "--limit", "6", "--quiet",
    ])
    assert code == 0
    pngs = sorted((out / "png").glob("*.png"))
    pdfs = sorted((out / "pdf").glob("*.pdf"))
    assert len(pngs) == 6 and len(pdfs) == 6
    assert pngs[0].name == "rl-a-01.png"
    assert "6 rows -> 6 PNG, 6 PDF" in capsys.readouterr().out


def test_cli_reports_missing_column(card_template, tmp_path, capsys):
    csv_path = tmp_path / "bad.csv"
    csv_path.write_text("title,subtitle\nOnly,Two columns\n")
    code = main(["generate", "--csv", str(csv_path), "--template", str(card_template), "--out", str(tmp_path / "o")])
    assert code == 2
    err = capsys.readouterr().err
    assert "needs column(s)" in err and "cover_image" in err


def test_cli_validate(card_template, sample_csv, capsys):
    assert main(["validate", "--template", str(card_template), "--csv", str(sample_csv)]) == 0
    assert "all bound columns present" in capsys.readouterr().out
