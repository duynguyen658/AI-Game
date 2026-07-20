from app.core.constants import ACTIVE_WORKFLOW_STATUS_VALUES
from app.database.base import Base


def test_backend_tables_are_registered() -> None:
    assert {
        "campaigns",
        "workflow_runs",
        "approval_records",
        "security_events",
    }.issubset(Base.metadata.tables)


def test_campaign_jsonb_artifact_columns_exist() -> None:
    columns = Base.metadata.tables["campaigns"].columns

    assert "brief_analysis" in columns
    assert "generated_content" in columns
    assert "quality_review" in columns


def test_approval_allows_only_one_record_per_workflow_in_metadata() -> None:
    table = Base.metadata.tables["approval_records"]

    assert any(
        constraint.name == "uq_approval_records_workflow_id"
        for constraint in table.constraints
    )
    assert not any(
        constraint.name == "uq_approval_workflow_decision"
        for constraint in table.constraints
    )


def test_active_workflow_partial_unique_index_is_registered() -> None:
    table = Base.metadata.tables["workflow_runs"]

    assert any(
        index.name == "uq_workflow_runs_one_active_per_campaign" and index.unique
        for index in table.indexes
    )


def test_revision_number_check_constraint_name_matches_migration() -> None:
    table = Base.metadata.tables["workflow_runs"]

    assert any(
        constraint.name == "ck_workflow_runs_revision_number_non_negative"
        for constraint in table.constraints
    )
    assert not any(
        constraint.name == "ck_workflow_revision_nonnegative"
        for constraint in table.constraints
    )


def test_active_workflow_status_values_match_partial_index_predicate() -> None:
    table = Base.metadata.tables["workflow_runs"]
    index = next(
        index
        for index in table.indexes
        if index.name == "uq_workflow_runs_one_active_per_campaign"
    )
    predicate = str(index.dialect_options["postgresql"]["where"])

    for status in ACTIVE_WORKFLOW_STATUS_VALUES:
        assert f"'{status}'" in predicate
