"""The tier rule: proficient / developing / novice from theta and a KU's item difficulties."""

import pytest
from assessment_agent import readiness_level


@pytest.mark.parametrize(
    ("theta", "expected"),
    [(-2.0, 1), (-0.01, 1), (0.0, 2), (0.9, 2), (1.0, 3), (3.0, 3)],
)
def test_levels_follow_the_applied_and_advanced_difficulties(theta, expected):
    assert readiness_level(theta, b_applied=0.0, b_advanced=1.0, n_scored=4) == expected


def test_no_scored_answers_means_novice_whatever_theta_says():
    assert readiness_level(5.0, 0.0, 1.0, n_scored=0) == 1


def test_an_advanced_item_easier_than_the_applied_one_cannot_skip_developing():
    # tiers out of order: theta passes the "advanced" b but not the applied b
    assert readiness_level(0.2, b_applied=0.6, b_advanced=0.1, n_scored=3) == 1
    assert readiness_level(0.7, b_applied=0.6, b_advanced=0.1, n_scored=3) == 3


def test_each_ku_is_judged_by_its_own_items_at_the_same_theta():
    theta = 0.5
    easy_ku = readiness_level(theta, b_applied=-0.5, b_advanced=0.4, n_scored=4)
    hard_ku = readiness_level(theta, b_applied=0.8, b_advanced=1.6, n_scored=4)
    assert (easy_ku, hard_ku) == (3, 1)
