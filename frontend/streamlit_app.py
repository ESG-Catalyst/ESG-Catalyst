"""ESG Catalyst — Phase 1 Streamlit UI.

Single-file dashboard for the consultant workflow:
    1. Select / create a company
    2. Upload documents (PDF, XLSX, CSV)
    3. Create a report & trigger extraction pipeline
    4. Monitor pipeline progress in real time
    5. View results: scores, metrics table, gap analysis
    6. Export report as JSON

Run:
    cd frontend && streamlit run streamlit_app.py
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from uuid import UUID, uuid4

import pandas as pd
import requests
import streamlit as st

# ── Configuration ─────────────────────────────────────────────────────────
API_BASE = "http://localhost:8000"

# Placeholder user ID for Phase 1 (no auth yet — Step 11)
_PLACEHOLDER_USER_ID = str(uuid4())


# ── API helpers ───────────────────────────────────────────────────────────
def api_get(path: str, params: dict | None = None) -> requests.Response:
    """GET request to backend API."""
    return requests.get(f"{API_BASE}{path}", params=params, timeout=30)


def api_post(path: str, json_data: dict | None = None, **kwargs) -> requests.Response:
    """POST request to backend API."""
    return requests.post(f"{API_BASE}{path}", json=json_data, timeout=60, **kwargs)


def api_post_file(path: str, files: dict, params: dict) -> requests.Response:
    """POST multipart file upload to backend API."""
    return requests.post(f"{API_BASE}{path}", files=files, params=params, timeout=120)


# ── Page config ───────────────────────────────────────────────────────────
st.set_page_config(
    page_title="ESG Catalyst",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("ESG Catalyst")
st.caption("AI-powered ESG reporting & scoring platform")


# ── Sidebar: Company management ───────────────────────────────────────────
st.sidebar.header("Company")

# Fetch existing companies
try:
    companies_resp = api_get("/companies/")
    companies = companies_resp.json() if companies_resp.status_code == 200 else []
except requests.ConnectionError:
    companies = []
    st.sidebar.error("Cannot connect to backend API. Is the server running?")

# Company selector
company_options = {c["name"]: c["id"] for c in companies}

if company_options:
    selected_name = st.sidebar.selectbox("Select company", options=list(company_options.keys()))
    selected_company_id = company_options[selected_name]
else:
    selected_company_id = None
    st.sidebar.info("No companies yet. Create one below.")

# Create new company
with st.sidebar.expander("Create new company"):
    with st.form("create_company", clear_on_submit=True):
        new_name = st.text_input("Company name")
        new_industry = st.selectbox("Industry", ["Banking", "Insurance", "Energy", "Manufacturing", "Other"])
        new_country = st.selectbox("Country", ["Egypt", "Saudi Arabia", "UAE", "Kuwait", "Other"])
        submitted = st.form_submit_button("Create")

        if submitted and new_name:
            resp = api_post("/companies/", json_data={
                "name": new_name,
                "industry": new_industry.lower(),
                "country": new_country.lower(),
            })
            if resp.status_code == 201:
                st.success(f"Created: {new_name}")
                st.rerun()
            else:
                st.error(f"Error: {resp.text}")


# ── Guard: require a company ──────────────────────────────────────────────
if not selected_company_id:
    st.info("Create a company in the sidebar to get started.")
    st.stop()


# ── Main area: tabbed workflow ────────────────────────────────────────────
tab_upload, tab_extract, tab_results, tab_export = st.tabs([
    "1. Upload Documents",
    "2. Run Extraction",
    "3. View Results",
    "4. Export Report",
])


# ═══════════════════════════════════════════════════════════════════════════
# TAB 1: Upload Documents
# ═══════════════════════════════════════════════════════════════════════════
with tab_upload:
    st.header("Upload Documents")
    st.markdown("Upload ESG-related documents (annual reports, utility bills, HR data, etc.)")

    uploaded_files = st.file_uploader(
        "Choose files",
        accept_multiple_files=True,
        type=["pdf", "xlsx", "xls", "csv", "png", "jpg", "jpeg", "tiff"],
    )

    if uploaded_files:
        st.write(f"**{len(uploaded_files)} file(s) selected**")

        if st.button("Upload all files", type="primary"):
            progress = st.progress(0)
            upload_results = []

            for idx, file in enumerate(uploaded_files):
                with st.spinner(f"Uploading {file.name}..."):
                    resp = api_post_file(
                        "/documents/upload",
                        files={"file": (file.name, file.getvalue(), file.type)},
                        params={
                            "company_id": selected_company_id,
                            "uploaded_by": _PLACEHOLDER_USER_ID,
                        },
                    )

                    if resp.status_code == 201:
                        doc = resp.json()
                        upload_results.append(doc)
                        st.success(f"Uploaded: {file.name} (ID: {doc['id'][:8]}...)")
                    else:
                        st.error(f"Failed to upload {file.name}: {resp.text}")

                progress.progress((idx + 1) / len(uploaded_files))

            if upload_results:
                st.session_state["uploaded_docs"] = upload_results
                st.info(f"{len(upload_results)} document(s) uploaded successfully.")

    # Show existing documents for this company
    st.subheader("Uploaded Documents")
    docs_resp = api_get("/documents/", params={"company_id": selected_company_id})
    if docs_resp.status_code == 200:
        docs = docs_resp.json()
        if docs:
            docs_df = pd.DataFrame(docs)[["filename", "file_type", "status", "page_count", "language", "id"]]
            docs_df.columns = ["Filename", "Type", "Status", "Pages", "Language", "ID"]
            st.dataframe(docs_df, use_container_width=True, hide_index=True)
        else:
            st.info("No documents uploaded yet for this company.")
    else:
        st.warning("Could not fetch documents.")


# ═══════════════════════════════════════════════════════════════════════════
# TAB 2: Run Extraction
# ═══════════════════════════════════════════════════════════════════════════
with tab_extract:
    st.header("Run Extraction Pipeline")

    # Fetch documents for this company
    docs_resp = api_get("/documents/", params={"company_id": selected_company_id})
    available_docs = docs_resp.json() if docs_resp.status_code == 200 else []
    pending_docs = [d for d in available_docs if d["status"] in ("pending", "processed")]

    if not pending_docs:
        st.info("Upload documents first, then come back here to run extraction.")
        st.stop()

    # Report setup
    st.subheader("Report Setup")
    col1, col2 = st.columns(2)
    with col1:
        report_title = st.text_input("Report title", value=f"ESG Report {datetime.now().year}")
    with col2:
        reporting_year = st.number_input("Reporting year", min_value=2020, max_value=2030, value=datetime.now().year)

    frameworks = st.multiselect("Frameworks", ["GRI", "FRA", "SASB"], default=["GRI", "FRA", "SASB"])

    # Document selection
    st.subheader("Select Documents")
    doc_options = {d["filename"]: d for d in pending_docs}
    selected_doc_names = st.multiselect(
        "Documents to process",
        options=list(doc_options.keys()),
        default=list(doc_options.keys()),
    )
    selected_docs = [doc_options[name] for name in selected_doc_names]

    if not selected_docs:
        st.warning("Select at least one document.")
        st.stop()

    # Run pipeline
    if st.button("Start Extraction Pipeline", type="primary"):
        # 1. Create report
        with st.spinner("Creating report..."):
            report_resp = api_post("/reports/generate", json_data={
                "company_id": selected_company_id,
                "title": report_title,
                "reporting_year": reporting_year,
                "frameworks": frameworks,
            })

            if report_resp.status_code != 201:
                st.error(f"Failed to create report: {report_resp.text}")
                st.stop()

            report = report_resp.json()
            report_id = report["id"]
            st.session_state["current_report_id"] = report_id
            st.success(f"Report created: {report_title} (ID: {report_id[:8]}...)")

        # 2. Run extraction for each document
        task_ids = []
        for doc in selected_docs:
            with st.spinner(f"Queuing {doc['filename']}..."):
                run_resp = api_post("/extraction/run", json_data={
                    "document_id": doc["id"],
                    "company_id": selected_company_id,
                    "report_id": report_id,
                })

                if run_resp.status_code == 200:
                    task = run_resp.json()
                    task_ids.append((doc["filename"], task["task_id"]))
                    st.info(f"Pipeline started for {doc['filename']}")
                else:
                    st.error(f"Failed to start pipeline for {doc['filename']}: {run_resp.text}")

        # 3. Poll progress
        if task_ids:
            st.subheader("Pipeline Progress")

            # Pipeline stages for the progress bar
            STAGES = {
                "PENDING": 0.0,
                "INGESTING": 0.10,
                "CHUNKING": 0.25,
                "CLASSIFYING": 0.40,
                "EXTRACTING": 0.60,
                "SCORING": 0.80,
                "PERSISTING": 0.90,
                "SUCCESS": 1.0,
            }

            for filename, task_id in task_ids:
                st.write(f"**{filename}**")
                progress_bar = st.progress(0)
                status_text = st.empty()

                completed = False
                while not completed:
                    status_resp = api_get(f"/extraction/status/{task_id}")
                    if status_resp.status_code != 200:
                        status_text.error("Failed to fetch status")
                        break

                    status_data = status_resp.json()
                    state = status_data["state"]
                    msg = status_data.get("status", "Processing...")

                    progress_val = STAGES.get(state, 0.05)
                    progress_bar.progress(progress_val)
                    status_text.text(f"Stage: {state} — {msg}")

                    if state == "SUCCESS":
                        progress_bar.progress(1.0)
                        status_text.success("Pipeline complete!")
                        completed = True

                        # Store result for the results tab
                        st.session_state["pipeline_result"] = status_data.get("result")

                    elif state == "FAILURE":
                        status_text.error(f"Pipeline failed: {msg}")
                        completed = True

                    else:
                        time.sleep(2)

            st.balloons()
            st.info("Go to the **View Results** tab to see extracted metrics and scores.")


# ═══════════════════════════════════════════════════════════════════════════
# TAB 3: View Results
# ═══════════════════════════════════════════════════════════════════════════
with tab_results:
    st.header("Extraction Results")

    # Get report ID from session or let user enter it
    report_id = st.session_state.get("current_report_id")

    if not report_id:
        report_id_input = st.text_input("Enter Report ID (from extraction step)")
        if report_id_input:
            report_id = report_id_input
        else:
            st.info("Run an extraction first, or enter a report ID above.")
            st.stop()

    # Fetch report details
    report_resp = api_get(f"/reports/{report_id}")
    if report_resp.status_code != 200:
        st.warning("Report not found. Run extraction first.")
        st.stop()

    report = report_resp.json()

    # ── Score cards ───────────────────────────────────────────────────
    st.subheader("ESG Scores")
    col1, col2, col3, col4 = st.columns(4)

    total = report.get("total_score")
    gri = report.get("gri_score")
    fra = report.get("fra_score")
    sasb = report.get("sasb_score")

    col1.metric("Total Score", f"{total:.1f}/100" if total else "N/A")
    col2.metric("GRI Score", f"{gri:.1f}/100" if gri else "N/A")
    col3.metric("FRA Score", f"{fra:.1f}/100" if fra else "N/A")
    col4.metric("SASB Score", f"{sasb:.1f}/100" if sasb else "N/A")

    # ── Score bar chart ───────────────────────────────────────────────
    if total is not None:
        scores_df = pd.DataFrame({
            "Framework": ["Total", "GRI (50%)", "FRA (30%)", "SASB (20%)"],
            "Score": [total or 0, gri or 0, fra or 0, sasb or 0],
        })
        st.bar_chart(scores_df.set_index("Framework"))

    # ── Metrics table ─────────────────────────────────────────────────
    st.subheader("Extracted Metrics")

    metrics_resp = api_get(f"/extraction/results/{report_id}")
    if metrics_resp.status_code == 200:
        metrics = metrics_resp.json()

        # Summary counts
        counts = {}
        for m in metrics:
            s = m["status"]
            counts[s] = counts.get(s, 0) + 1

        count_cols = st.columns(len(counts))
        for i, (status_name, count) in enumerate(sorted(counts.items())):
            color = {
                "extracted": "green",
                "approved": "blue",
                "ambiguous": "orange",
                "missing": "red",
                "rejected": "gray",
            }.get(status_name, "gray")
            count_cols[i].markdown(
                f":{color}[**{status_name.upper()}**: {count}]"
            )

        # Detailed table
        metrics_rows = []
        for m in metrics:
            confidence_pct = f"{m['confidence']:.0%}"
            # Confidence color indicator
            if m["confidence"] >= 0.8:
                conf_display = f"**{confidence_pct}**"
            elif m["confidence"] >= 0.5:
                conf_display = f"*{confidence_pct}*"
            else:
                conf_display = confidence_pct

            metrics_rows.append({
                "GRI Code": m["gri_code"],
                "Label": m["label"],
                "Value": m.get("value") or "—",
                "Unit": m.get("unit") or "—",
                "Original Value": m.get("original_value") or "—",
                "Confidence": m["confidence"],
                "Status": m["status"],
                "Source": m.get("source_file") or "—",
                "Page": m.get("source_page") or "—",
            })

        df = pd.DataFrame(metrics_rows)
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Confidence": st.column_config.ProgressColumn(
                    "Confidence",
                    help="Extraction confidence (0-100%)",
                    min_value=0.0,
                    max_value=1.0,
                    format="%.0%%",
                ),
                "Status": st.column_config.TextColumn("Status"),
            },
        )

        # ── Evidence viewer ───────────────────────────────────────────
        st.subheader("Evidence Viewer")
        st.markdown("Select a metric to see the extracted evidence passage.")

        metric_labels = [f"{m['gri_code']} — {m['label']}" for m in metrics]
        selected_metric_label = st.selectbox("Select metric", metric_labels)

        if selected_metric_label:
            idx = metric_labels.index(selected_metric_label)
            m = metrics[idx]

            evidence_col, detail_col = st.columns([2, 1])

            with evidence_col:
                evidence = m.get("evidence_chunk")
                if evidence:
                    st.markdown("**Evidence passage:**")
                    st.text_area(
                        "Evidence",
                        value=evidence,
                        height=200,
                        disabled=True,
                        label_visibility="collapsed",
                    )
                else:
                    st.info("No evidence passage recorded for this metric.")

            with detail_col:
                st.markdown("**Details:**")
                st.write(f"**Value:** {m.get('value') or 'N/A'} {m.get('unit') or ''}")
                st.write(f"**Original:** {m.get('original_value') or 'N/A'} {m.get('original_unit') or ''}")
                st.write(f"**Confidence:** {m['confidence']:.0%}")
                st.write(f"**Status:** {m['status']}")
                st.write(f"**Source:** {m.get('source_file') or 'N/A'}, page {m.get('source_page') or 'N/A'}")
                if m.get("note"):
                    st.write(f"**Note:** {m['note']}")

        # ── Gap analysis (from pipeline result) ───────────────────────
        pipeline_result = st.session_state.get("pipeline_result")
        if pipeline_result and pipeline_result.get("gaps"):
            st.subheader("Gap Analysis")
            st.markdown("Indicators that are missing, ambiguous, or below the confidence threshold:")

            gaps = pipeline_result["gaps"]
            for gap in gaps:
                with st.expander(f"{gap['code']} — {gap['name']} ({gap['status']})"):
                    st.markdown(f"**Status:** {gap['status']}")
                    st.markdown(f"**Recommendation:** {gap['recommendation']}")

    elif metrics_resp.status_code == 404:
        st.info("No metrics found yet. Run the extraction pipeline first.")
    else:
        st.error(f"Error fetching results: {metrics_resp.text}")


# ═══════════════════════════════════════════════════════════════════════════
# TAB 4: Export Report
# ═══════════════════════════════════════════════════════════════════════════
with tab_export:
    st.header("Export Report")

    report_id = st.session_state.get("current_report_id")
    if not report_id:
        st.info("Run an extraction first to have results to export.")
        st.stop()

    report_resp = api_get(f"/reports/{report_id}")
    if report_resp.status_code != 200:
        st.warning("Report not found.")
        st.stop()

    report = report_resp.json()
    st.write(f"**Report:** {report['title']}")
    st.write(f"**Year:** {report['reporting_year']}")
    st.write(f"**Status:** {report['status']}")

    if report.get("total_score") is not None:
        st.write(f"**Total Score:** {report['total_score']:.1f}/100")

    st.divider()

    # JSON export
    st.subheader("Download Full Report")
    st.markdown("Download the complete report with all metrics, scores, and evidence as JSON.")

    export_resp = api_get(f"/reports/export/{report_id}")
    if export_resp.status_code == 200:
        export_data = export_resp.json()
        json_str = json.dumps(export_data, indent=2, ensure_ascii=False)

        st.download_button(
            label="Download JSON Report",
            data=json_str,
            file_name=f"esg_report_{report['reporting_year']}.json",
            mime="application/json",
            type="primary",
        )

        # Preview
        with st.expander("Preview export data"):
            st.json(export_data)
    else:
        st.error("Failed to generate export.")

    # CSV export of metrics
    st.subheader("Download Metrics as CSV")
    metrics_resp = api_get(f"/extraction/results/{report_id}")
    if metrics_resp.status_code == 200:
        metrics = metrics_resp.json()
        df = pd.DataFrame(metrics)
        csv = df.to_csv(index=False)
        st.download_button(
            label="Download Metrics CSV",
            data=csv,
            file_name=f"esg_metrics_{report['reporting_year']}.csv",
            mime="text/csv",
        )
    else:
        st.info("No metrics available for CSV export.")
