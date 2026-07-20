from app.agentic.memory.working_memory import WorkingMemory


def test_working_memory_is_bounded_and_redacted() -> None:
    memory = WorkingMemory(max_items=2, max_characters=200)
    memory.add("policy", "token=private-value first")
    memory.add("action", "second")
    memory.add("result", "third")

    assert len(memory.items) == 2
    assert [item.kind for item in memory.items] == ["action", "result"]
    assert "private-value" not in str(memory.items)
