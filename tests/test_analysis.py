"""Tests for game review and move classification."""

from __future__ import annotations

import time

import pytest

from iago.app.analysis import (
    BEST,
    BLUNDER,
    GOOD,
    INACCURACY,
    LABEL_ORDER,
    MISTAKE,
    GameReview,
    MoveAssessment,
    ReviewWorker,
    analyse_moves,
    classify,
    win_probability_from_score,
)
from iago.app.session import Session
from iago.core.constants import PLAYER_BLACK, PLAYER_WHITE


def played_game(moves: int = 20) -> list[tuple[int, int, int]]:
    session = Session(size=8, mode="hvh")
    for _ in range(moves):
        options = session.legal_moves()
        if not options:
            session.play_pending_pass()
            continue
        session.apply_move(*options[0])
    return session.to_move_log()


def test_probability_is_monotonic_and_bounded():
    assert win_probability_from_score(0) == pytest.approx(0.5)
    assert 0.0 < win_probability_from_score(-100) < 0.5
    assert 0.5 < win_probability_from_score(100) < 1.0
    assert win_probability_from_score(10_000_000) > 0.99
    assert win_probability_from_score(-10_000_000) < 0.01


@pytest.mark.parametrize(
    "loss,expected",
    [
        (0.0, BEST),
        (0.4, BEST),
        (1.0, GOOD),
        (3.0, INACCURACY),
        (8.0, MISTAKE),
        (30.0, BLUNDER),
    ],
)
def test_classify_thresholds(loss, expected):
    assert classify(loss) == expected


def test_classify_is_monotonic():
    labels = [classify(loss) for loss in (0, 1, 3, 8, 20)]
    indexes = [LABEL_ORDER.index(label) for label in labels]
    assert indexes == sorted(indexes)


def test_analyse_moves_produces_one_assessment_per_move():
    moves = played_game(12)
    review = analyse_moves(moves, depth=2)
    assert len(review.assessments) == len(moves)
    assert review.engine_depth == 2
    for assessment in review.assessments:
        assert assessment.label in LABEL_ORDER
        assert assessment.loss >= 0.0


def test_accuracy_is_a_percentage():
    review = analyse_moves(played_game(16), depth=2)
    for player in (PLAYER_BLACK, PLAYER_WHITE):
        accuracy = review.accuracy(player)
        assert 0.0 <= accuracy <= 100.0


def test_counts_cover_every_label():
    review = analyse_moves(played_game(10), depth=2)
    counts = review.counts(PLAYER_BLACK)
    assert set(counts) == set(LABEL_ORDER)
    assert sum(counts.values()) == sum(
        1 for item in review.assessments if item.player == PLAYER_BLACK
    )


def test_assessment_lookup_and_worst():
    review = analyse_moves(played_game(14), depth=2)
    first = review.assessments[0]
    assert review.assessment_for(1) == first
    assert review.assessment_for(999) is None
    worst = review.worst(limit=2)
    assert len(worst) <= 2
    assert all(item.label in (MISTAKE, BLUNDER) for item in worst)


def test_summary_mentions_both_sides():
    review = analyse_moves(played_game(8), depth=2)
    text = review.summary()
    assert "Black" in text and "White" in text and "Accuracy" in text


def test_progress_callback_runs():
    seen: list[tuple[int, int]] = []
    moves = played_game(6)
    analyse_moves(
        moves, depth=1, progress=lambda done, total: seen.append((done, total))
    )
    assert seen[-1] == (len(moves), len(moves))


def test_should_stop_aborts_early():
    moves = played_game(12)
    review = analyse_moves(moves, depth=1, should_stop=lambda: True)
    assert not review.assessments


def test_empty_review_defaults():
    review = GameReview()
    assert review.accuracy(PLAYER_BLACK) == 0.0
    assert review.worst() == []
    assert review.assessment_for(1) is None


def test_move_assessment_names():
    item = MoveAssessment(
        ply=1,
        player=PLAYER_BLACK,
        row=2,
        col=3,
        best_row=3,
        best_col=2,
        loss=0.0,
        label=BEST,
        score=10,
    )
    assert item.move_name == "d3"
    assert item.best_move_name == "c4"


def test_review_worker_completes():
    worker = ReviewWorker()
    moves = played_game(10)
    worker.start(moves, depth=1)
    deadline = time.perf_counter() + 10.0
    review = None
    while time.perf_counter() < deadline:
        _, result = worker.poll()
        if result is not None:
            review = result
            break
        time.sleep(0.01)
    worker.cancel()
    assert review is not None
    assert len(review.assessments) == len(moves)


def test_review_worker_cancel_is_safe():
    worker = ReviewWorker()
    worker.start(played_game(40), depth=3)
    worker.cancel()
    assert not worker.busy
