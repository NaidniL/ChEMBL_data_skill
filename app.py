"""Streamlit presentation layer for the deterministic ChEMBL workflow."""

from __future__ import annotations

import streamlit as st

from src.workflow.runner import (
    TargetSelectionRequired,
    WorkflowExecutionError,
    WorkflowRun,
    available_offline_fixtures,
    run_workflow,
)


def _clear_candidates() -> None:
    st.session_state.pop("target_candidates", None)
    st.session_state.pop("candidate_query", None)


def _render_run(run: WorkflowRun) -> None:
    st.success(f"Workflow completed and independently validated. Run: {run.run_directory}")
    st.caption(f"Resolved target: {run.target_chembl_id} · Source: {run.source}")

    st.subheader("Validation")
    st.json(run.validation_report)

    st.subheader("Statistics")
    st.json(run.statistics)

    st.subheader("Exclusions")
    st.json(run.exclusions)

    left, right = st.columns(2)
    with left:
        st.subheader("Highest pIC50 records")
        st.dataframe(run.top_records, width="stretch")
    with right:
        st.subheader("Lowest pIC50 records")
        st.dataframe(run.bottom_records, width="stretch")


def main() -> None:
    st.set_page_config(page_title="ChEMBL workflow", page_icon="🧪", layout="wide")
    st.title("ChEMBL IC50 workflow")
    st.caption("This interface only runs the existing deterministic M1–M5 workflow and displays its artifacts.")

    target = st.text_input(
        "Target",
        placeholder="human EGFR",
        help="Enter a ChEMBL target ID, UniProt accession, or ChEMBL preferred target name.",
        on_change=_clear_candidates,
    )
    activity_type = st.selectbox("Activity", ["IC50"])
    source_label = st.radio("Source", ["Live ChEMBL", "Offline fixture"], horizontal=True)
    source = "live" if source_label == "Live ChEMBL" else "offline"
    limit = None
    offline_fixture = None

    selected_target = target
    candidates = st.session_state.get("target_candidates")
    if source == "offline":
        fixtures = available_offline_fixtures()
        if not fixtures:
            st.error("No valid offline fixture is available under tests/fixtures.")
            return
        offline_fixture = st.selectbox("Offline fixture", fixtures)
        st.caption("Fixtures are read only from `tests/fixtures/`; no ChEMBL network request is made.")
    else:
        limit = st.number_input(
            "Record limit",
            min_value=1,
            value=200,
            step=100,
            help="Maximum number of raw ChEMBL activity records to retrieve. The default avoids a long full-dataset query.",
        )
        if candidates:
            st.warning("Target discovery returned multiple candidates. Select the intended ChEMBL target ID.")
            st.dataframe(candidates, width="stretch")
            selected_target = st.selectbox("Confirmed ChEMBL target ID", [candidate["target_chembl_id"] for candidate in candidates])

    if st.button("Run workflow", type="primary"):
        status = st.status("Starting workflow", expanded=True)
        try:
            result = run_workflow(
                selected_target,
                activity_type,
                source,
                limit=limit,
                offline_fixture=offline_fixture or "egfr-limit20",
                original_target_query=target or None,
                progress=status.write,
            )
        except TargetSelectionRequired as exc:
            st.session_state["target_candidates"] = exc.candidates
            st.session_state["candidate_query"] = target
            status.update(label="Target selection required", state="error")
            st.error(str(exc))
        except (ValueError, WorkflowExecutionError) as exc:
            status.update(label="Workflow failed", state="error")
            st.error(str(exc))
        else:
            status.update(label="Workflow completed", state="complete")
            _render_run(result)


if __name__ == "__main__":
    main()
