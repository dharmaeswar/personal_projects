"""Tests for the text-to-SQL stand-in and the agent workflow."""

import pytest

from agent_eval.agent import AnalyticsAgent
from agent_eval.sandbox import Sandbox
from agent_eval.text_to_sql import translate, TranslationError
from agent_eval.tools import ToolServer


@pytest.fixture
def agent():
    return AnalyticsAgent(ToolServer(Sandbox()))


def test_translate_top_communities():
    sql = translate("Which 3 communities have the most posts in the last 7 days?")
    assert "ORDER BY post_count DESC" in sql
    assert "LIMIT 3" in sql
    assert "created_day >= 23" in sql


def test_translate_average_score():
    sql = translate("What is the average score of posts in datascience?")
    assert "AVG(score)" in sql
    assert "datascience" in sql


def test_translate_unknown_community_raises():
    with pytest.raises(TranslationError):
        translate("What is the average score of posts in quantumcomputing?")


def test_translate_unsupported_pattern_raises():
    with pytest.raises(TranslationError):
        translate("Tell me a joke about statistics.")


def test_agent_answers_aggregation_question(agent):
    result = agent.answer("What is the total score of all posts in python?")
    assert result.status == "complete"
    assert result.sql is not None
    assert len(result.rows) == 1
    assert result.summary is not None
    assert result.provenance["dataset_version"] == "community-analytics-v1"
    assert len(result.tool_calls) == 5  # context, sql, run, validate, summarize


def test_agent_marks_unknown_community_incomplete(agent):
    result = agent.answer(
        "What is the average score of posts in quantumcomputing?")
    assert result.status == "incomplete"
    assert result.summary is None
    assert result.rows == []
    assert "could not translate" in result.failure_reason


def test_agent_summary_is_grounded_in_rows(agent):
    result = agent.answer("How many posts did machinelearning have in the last 14 days?")
    assert result.status == "complete"
    count = str(result.rows[0][0])
    assert count in result.summary


def test_agent_plan_names_all_five_steps(agent):
    result = agent.answer("What is the total score of all posts in python?")
    assert result.plan == [
        "retrieve dataset context",
        "translate question to SQL",
        "execute SQL in the sandbox",
        "validate the result",
        "summarize from the returned rows only",
    ]
