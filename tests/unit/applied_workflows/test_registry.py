from app.applied_workflows.registry import AppliedWorkflowRegistry
from app.core.constants import AppliedWorkflowType, JobType


def test_registry_is_stable_for_m8_contracts() -> None:
    registry = AppliedWorkflowRegistry()
    assert {item.workflow_type for item in registry.list()} == set(AppliedWorkflowType)
    assert (
        registry.get(AppliedWorkflowType.DATA_ANALYSIS).job_type
        == JobType.DATA_ANALYSIS
    )
    assert registry.get(AppliedWorkflowType.IMAGE_GENERATION).required_capabilities == [
        "image_generation"
    ]
