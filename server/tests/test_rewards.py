"""Tests for tokenomics reward calculations."""
import pytest
from axon_server.rewards import compute_improvement_ratio, is_better, meets_threshold


# --- is_better ---

def test_is_better_maximize():
    assert is_better(0.8, 0.5, "maximize") is True
    assert is_better(0.3, 0.5, "maximize") is False
    assert is_better(0.5, 0.5, "maximize") is False  # tie = no improvement

def test_is_better_minimize():
    assert is_better(0.3, 0.5, "minimize") is True
    assert is_better(0.8, 0.5, "minimize") is False

def test_is_better_first_submission():
    assert is_better(0.5, None, "maximize") is True
    assert is_better(0.5, None, "minimize") is True


# --- meets_threshold ---

def test_meets_threshold_maximize():
    assert meets_threshold(95.0, 90.0, "maximize") is True
    assert meets_threshold(85.0, 90.0, "maximize") is False

def test_meets_threshold_minimize():
    # minimize: score <= threshold means "good enough"
    assert meets_threshold(-0.05, -0.01, "minimize") is True   # -0.05 <= -0.01
    assert meets_threshold(-0.001, -0.01, "minimize") is False  # -0.001 > -0.01 (too good is not <= threshold)

def test_meets_threshold_exact():
    assert meets_threshold(90.0, 90.0, "maximize") is True
    assert meets_threshold(-450.0, -450.0, "minimize") is True


# --- compute_improvement_ratio ---

def test_improvement_ratio_basic():
    # 60 → 72, baseline=60, threshold=95, maximize
    ratio = compute_improvement_ratio(60.0, 72.0, 60.0, 95.0, "maximize")
    # delta=12, range=35, progress=0, bonus=1.0
    # ratio = (12/35) * 1.0 = 0.3428...
    assert abs(ratio - 12/35) < 1e-6

def test_improvement_ratio_difficulty_bonus():
    # 90 → 93, baseline=60, threshold=95, maximize
    # progress = (90-60)/(95-60) = 30/35 = 0.857
    # bonus = 1/(1-0.857) = 7.0
    # ratio = (3/35) * 7.0 = 0.6
    ratio = compute_improvement_ratio(90.0, 93.0, 60.0, 95.0, "maximize")
    assert abs(ratio - 0.6) < 0.01

def test_improvement_ratio_capped_at_1():
    # Huge improvement should still cap at 1.0
    ratio = compute_improvement_ratio(0.0, 100.0, 0.0, 50.0, "maximize")
    assert ratio == 1.0

def test_improvement_ratio_zero_range():
    # threshold == baseline → no range → return 0
    ratio = compute_improvement_ratio(50.0, 51.0, 50.0, 50.0, "maximize")
    assert ratio == 0.0

def test_improvement_ratio_minimize():
    # minimize: score goes down (good), e.g. -100 → -50, baseline=-100, threshold=-10
    ratio = compute_improvement_ratio(-100.0, -50.0, -100.0, -10.0, "minimize")
    # delta=50, range=90, progress=((-100)-(-100))/90=0, bonus=1
    # ratio = 50/90 * 1.0 = 0.555...
    assert abs(ratio - 50/90) < 1e-6

def test_improvement_near_threshold_high_bonus():
    # progress = 0.95 → bonus = 20x
    # baseline=0, threshold=100, old=95, new=96
    ratio = compute_improvement_ratio(95.0, 96.0, 0.0, 100.0, "maximize")
    # delta=1, range=100, progress=0.95, bonus=1/(1-0.95)=20
    # ratio = (1/100)*20 = 0.2
    assert abs(ratio - 0.2) < 0.01
