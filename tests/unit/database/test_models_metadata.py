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
