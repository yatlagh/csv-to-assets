from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def root() -> Path:
    return ROOT


@pytest.fixture(scope="session")
def sample_csv(root: Path) -> Path:
    return root / "samples" / "books.csv"


@pytest.fixture(scope="session")
def card_template(root: Path) -> Path:
    return root / "templates" / "card.json"


@pytest.fixture
def sample_row() -> dict[str, str]:
    return {
        "id": "RL-A-03",
        "title": "Maps and Journeys",
        "subtitle": "How people find their way",
        "series": "Reading Level A - Unit 3",
        "grade_band": "Grades K-1",
        "level": "A",
        "pages": "24",
        "color": "#2F6F9F",
        "cover_image": "covers/cover-a-03.png",
    }
