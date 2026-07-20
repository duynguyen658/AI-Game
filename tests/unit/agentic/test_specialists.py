from app.agentic.agents import (
    BriefAnalystAgent,
    ContentGeneratorAgent,
    ContentReviewerAgent,
)


def test_specialists_have_distinct_schemas_tools_and_safety_boundaries() -> None:
    agents = [BriefAnalystAgent(), ContentGeneratorAgent(), ContentReviewerAgent()]
    assert len({agent.output_schema for agent in agents}) == 3
    assert all(agent.allowed_tool_names for agent in agents)
    for agent in agents:
        prompt = agent.build_system_prompt().lower()
        assert "no workflow-state or approval authority" in prompt
        assert "untrusted" in prompt
        assert "chain-of-thought" in prompt
