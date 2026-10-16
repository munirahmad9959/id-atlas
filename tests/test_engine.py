import threading
import time
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
from factories import bgr, card_image

from id_atlas import engine
from id_atlas.engine import Line

ROWS = ["REPUBLICA DE COSTA RICA", "Nombre: ANA MARIA", "Vence: 05/03/2030"]
PAGE = bgr(card_image(*ROWS))
ROTATIONS = [
    pytest.param(cv2.ROTATE_90_CLOCKWISE, id="90-clockwise"),
    pytest.param(cv2.ROTATE_180, id="180"),
    pytest.param(cv2.ROTATE_90_COUNTERCLOCKWISE, id="90-counterclockwise"),
]


def texts(lines: list[Line]) -> list[str]:
    return [ln.text for ln in lines]


def wide(text: str, score: float = 0.99, y: float = 0) -> Line:
    return Line(text, score, 0, y, 200, 20)


def tall(text: str, score: float = 0.99, y: float = 0) -> Line:
    return Line(text, score, 0, y, 20, 200)


# --- reading real pixels (runs the OCR model) ---------------------------------------------------


def test_reads_the_rows_top_to_bottom_with_geometry():
    lines = engine.read_lines(PAGE, 0.8)
    assert texts(lines) == ROWS
    assert all(ln.score > 0.9 for ln in lines)
    assert [ln.y for ln in lines] == sorted(ln.y for ln in lines)
    assert all(ln.w > ln.h for ln in lines)
    assert all(abs(ln.x - 30) < 20 for ln in lines)


@pytest.mark.parametrize("rotation", ROTATIONS)
def test_a_rotated_page_is_read_in_the_right_order(rotation):
    assert texts(engine.read_lines(cv2.rotate(PAGE, rotation), 0.8)) == ROWS


def test_a_single_line_page_is_read_in_every_orientation():
    page = bgr(card_image("Vence: 05/03/2030"))
    assert texts(engine.read_lines(page, 0.8)) == ["Vence: 05/03/2030"]
    assert texts(engine.read_lines(cv2.rotate(page, cv2.ROTATE_180), 0.8)) == ["Vence: 05/03/2030"]


def test_a_blank_page_reads_nothing():
    assert engine.read_lines(np.full((300, 600, 3), 255, np.uint8), 0.8) == []


def test_warm_up_loads_the_models_once():
    engine.warm_up()
    engine.warm_up()
    assert engine._engine.cache_info().currsize == 1


# --- orientation logic (no OCR: the model is replaced by scripted readings) ---------------------


def scripted(monkeypatch, readings):
    """Replace the OCR with a sequence of readings; returns the list of image shapes it was given."""
    seen, queue = [], list(readings)
    monkeypatch.setattr(engine, "_run", lambda image: (seen.append(image.shape[:2]), queue.pop(0))[1])
    return seen


def test_a_clean_reading_is_accepted_without_retrying(monkeypatch):
    seen = scripted(monkeypatch, [[wide("A"), wide("B")]])
    assert texts(engine.read_lines(np.zeros((10, 20, 3), np.uint8), 0.8)) == ["A", "B"]
    assert len(seen) == 1


def test_a_weak_reading_is_retried_at_every_rotation(monkeypatch):
    seen = scripted(monkeypatch, [[wide("noise", 0.5)], [], [wide("good one"), wide("good two")], []])
    result = engine.read_lines(np.zeros((10, 20, 3), np.uint8), 0.8)
    assert texts(result) == ["good one", "good two"]
    assert seen == [(10, 20), (20, 10), (10, 20), (20, 10)]  # as given, then 90 cw, 180, 90 ccw


@pytest.mark.parametrize(
    "readings", [[[wide("only one")]], [[wide("a", 0.5), wide("b", 0.5)]]], ids=["one line", "low score"]
)
def test_too_little_or_too_unsure_triggers_a_retry(monkeypatch, readings):
    seen = scripted(monkeypatch, [*readings, [], [], []])
    engine.read_lines(np.zeros((10, 20, 3), np.uint8), 0.8)
    assert len(seen) == 4


def test_the_retry_threshold_is_configurable(monkeypatch):
    seen = scripted(monkeypatch, [[wide("a", 0.5), wide("b", 0.5)]])
    engine.read_lines(np.zeros((10, 20, 3), np.uint8), 0.4)
    assert len(seen) == 1


def test_sideways_text_never_wins_on_confidence_alone(monkeypatch):
    # The model reads rotated text as tall boxes, and reads it well; an upright reading must still win.
    sideways = [tall("long sideways text", 1.0), tall("more sideways text", 1.0), tall("and more", 1.0)]
    upright = [wide("short", 0.9), wide("page", 0.9)]
    scripted(monkeypatch, [sideways, [], upright, []])
    assert texts(engine.read_lines(np.zeros((10, 20, 3), np.uint8), 0.8)) == ["short", "page"]


def test_upright_filters_tall_boxes():
    mixed = [wide("a"), tall("b"), Line("square", 1.0, 0, 0, 20, 20)]
    assert texts(engine._upright(mixed)) == ["a", "square"]
    assert engine._quality([tall("ignored")]) == 0
    assert engine._quality([wide("abcd", 0.5)]) == 2.0


# --- converting the model's output (no OCR: the model is a fake) --------------------------------


def fake_model(monkeypatch, result):
    monkeypatch.setattr(engine, "_engine", lambda: lambda image: result)


def test_model_output_becomes_sorted_lines_with_box_geometry(monkeypatch):
    box = lambda x, y, w, h: np.array([[x, y], [x + w, y], [x + w, y + h], [x, y + h]], dtype=float)
    fake_model(
        monkeypatch,
        SimpleNamespace(
            txts=("lower", "upper"), scores=(0.8, 0.9), boxes=[box(10, 100, 50, 20), box(40, 10, 120, 30)]
        ),
    )
    lines = engine._run(np.zeros((5, 5, 3), np.uint8))
    assert texts(lines) == ["upper", "lower"]  # sorted top to bottom
    assert lines[0] == Line("upper", 0.9, 40.0, 25.0, 120.0, 30.0)  # x is the left edge, y the centre


def test_no_text_found_is_an_empty_list(monkeypatch):
    fake_model(monkeypatch, SimpleNamespace(txts=None, scores=None, boxes=None))
    assert engine._run(np.zeros((5, 5, 3), np.uint8)) == []


def test_only_one_inference_runs_at_a_time(monkeypatch):
    active, peak = 0, 0
    guard = threading.Lock()

    def slow_model(image):
        nonlocal active, peak
        with guard:
            active += 1
            peak = max(peak, active)
        time.sleep(0.03)
        with guard:
            active -= 1
        return SimpleNamespace(txts=None, scores=None, boxes=None)

    monkeypatch.setattr(engine, "_engine", lambda: slow_model)
    threads = [threading.Thread(target=engine._run, args=(np.zeros((5, 5, 3), np.uint8),)) for _ in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert peak == 1
