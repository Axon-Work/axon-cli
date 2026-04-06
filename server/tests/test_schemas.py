"""Tests for Pydantic schemas — validation, edge cases."""
import pytest
from pydantic import ValidationError
from axon_server.schemas import TaskCreate, SubmissionCreate


def test_task_create_valid():
    t = TaskCreate(
        title="Test", description="Desc", eval_type="exact_match",
        eval_config={"expected": "42"}, completion_threshold=1.0, task_burn=100,
    )
    assert t.task_burn == 100
    assert t.direction == "maximize"  # default


def test_task_create_invalid_eval_type():
    with pytest.raises(ValidationError):
        TaskCreate(
            title="Test", description="Desc", eval_type="invalid_type",
            eval_config={}, completion_threshold=1.0, task_burn=100,
        )


def test_task_create_zero_burn():
    with pytest.raises(ValidationError):
        TaskCreate(
            title="Test", description="Desc", eval_type="exact_match",
            eval_config={}, completion_threshold=1.0, task_burn=0,
        )


def test_task_create_direction_values():
    t1 = TaskCreate(title="T", description="D", eval_type="numeric",
                    eval_config={}, completion_threshold=1.0, task_burn=10, direction="maximize")
    assert t1.direction == "maximize"

    t2 = TaskCreate(title="T", description="D", eval_type="numeric",
                    eval_config={}, completion_threshold=1.0, task_burn=10, direction="minimize")
    assert t2.direction == "minimize"

    with pytest.raises(ValidationError):
        TaskCreate(title="T", description="D", eval_type="numeric",
                   eval_config={}, completion_threshold=1.0, task_burn=10, direction="invalid")


def test_submission_create_valid():
    s = SubmissionCreate(answer="42", thinking="math")
    assert s.answer == "42"
    assert s.llm_model_used is None


def test_submission_create_empty_answer():
    with pytest.raises(ValidationError):
        SubmissionCreate(answer="", thinking="t")
