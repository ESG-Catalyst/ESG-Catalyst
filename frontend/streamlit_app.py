"""ESG Catalyst — minimal Streamlit UI for Iteration 1.

Five linear flows backed entirely by the FastAPI ``/api/v1/...`` endpoints:

    1. Upload   → POST   /api/v1/documents/upload
    2. Run      → POST   /api/v1/pipeline/run        + poll /pipeline/status/{job_id}
    3. Review   → GET    /api/v1/metrics/{document_id}  + PATCH /api/v1/metrics/{metric_id}
    4. Generate → POST   /api/v1/reports/generate    + poll /reports/{report_id}?job_id=...
    5. Download → GET    /api/v1/reports/{report_id}/pdf

The app deliberately does NOT import anything from ``backend.app.core.*`` —
all data is exchanged through HTTP only.

Run:
    cd frontend && streamlit run streamlit_app.py
"""

from __future__ import annotations

import time
from typing import Any

import pandas as pd
import requests
import streamlit as st

API_BASE_URL = "http://localhost:8000"
POLL_INTERVAL_SECONDS = 2
PIPELINE_TERMINAL_STAGES = {"complete", "failed"}
REPORT_TERMINAL_STATES = {"ready", "failed"}


# ── HTTP helpers ──────────────────────────────────────────────────────────
def _url(path: str) -> str:
    return f"{API_BASE_URL}{path}"


def _detail(resp: requests.Response) -> str:
    try:
        body = resp.json()
        if isinstance(body, dict) and "detail" in body:
            return str(body["detail"])
        return str(body)
    except ValueError:
        return resp.text or f"HTTP {resp.status_code}"


def upload_document(file_bytes: bytes, filename: str) -> dict[str, Any]:
    files = {"file": (filename, file_bytes, "application/pdf")}
    resp = requests.post(_url("/api/v1/documents/upload"), files=files, timeout=120)
    resp.raise_for_status()
    return resp.json()


def run_pipeline(document_id: str) -> dict[str, Any]:
    resp = requests.post(
        _url("/api/v1/pipeline/run"),
        json={"document_id": document_id},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def get_pipeline_status(job_id: str) -> dict[str, Any]:
    resp = requests.get(_url(f"/api/v1/pipeline/status/{job_id}"), timeout=15)
    resp.raise_for_status()
    return resp.json()


def list_metrics(document_id: str) -> list[dict[str, Any]]:
    resp = requests.get(_url(f"/api/v1/metrics/{document_id}"), timeout=30)
    resp.raise_for_status()
    return resp.json()


def review_metric(metric_id: str, status_value: str) -> dict[str, Any]:
    resp = requests.patch(
        _url(f"/api/v1/metrics/{metric_id}"),
        json={"status": status_value},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def generate_report(document_id: str) -> dict[str, Any]:
    resp = requests.post(
        _url("/api/v1/reports/generate"),
        json={"document_id": document_id},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def get_report_status(report_id: str, job_id: str | None = None) -> dict[str, Any]:
    params = {"job_id": job_id} if job_id else None
    resp = requests.get(_url(f"/api/v1/reports/{report_id}"), params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def download_pdf(report_id: str) -> bytes:
    resp = requests.get(_url(f"/api/v1/reports/{report_id}/pdf"), timeout=60)
    resp.raise_for_status()
    return resp.content


# ── Session state ────────────────────────────────────────────────────────
def _init_state() -> None:
    defaults = {
        "document_id": None,
        "document_filename": None,
        "pipeline_job_id": None,
        "pipeline_done": False,
        "report_id": None,
        "report_job_id": None,
        "report_ready": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _reset_session() -> None:
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    _init_state()


# ── UI ───────────────────────────────────────────────────────────────────
st.set_page_config(page_title="ESG Catalyst", page_icon="🌱", layout="wide")
_init_state()

st.title("ESG Catalyst")
st.caption("Upload → Extract → Review → Generate → Download")

with st.sidebar:
    st.header("Session")
    st.write(f"**API:** `{API_BASE_URL}`")
    st.write(f"**Document:** `{st.session_state.document_id or '—'}`")
    st.write(f"**Report:** `{st.session_state.report_id or '—'}`")
    if st.button("Reset session"):
        _reset_session()
        st.rerun()


# ── Step 1 — Upload ───────────────────────────────────────────────────────
st.subheader("1. Upload PDF")
uploaded = st.file_uploader("Select a PDF document", type=["pdf"])

if uploaded is not None and st.button("Upload", type="primary"):
    try:
        result = upload_document(uploaded.getvalue(), uploaded.name)
        st.session_state.document_id = result["document_id"]
        st.session_state.document_filename = result["filename"]
        st.session_state.pipeline_job_id = None
        st.session_state.pipeline_done = False
        st.session_state.report_id = None
        st.session_state.report_job_id = None
        st.session_state.report_ready = False
        st.success(f"Uploaded `{result['filename']}` (status: {result['status']})")
    except requests.HTTPError as exc:
        st.error(f"Upload failed: {_detail(exc.response)}")
    except requests.RequestException as exc:
        st.error(f"Cannot reach API: {exc}")


# ── Step 2 — Run pipeline ─────────────────────────────────────────────────
st.subheader("2. Run extraction pipeline")

if st.session_state.document_id is None:
    st.info("Upload a document first.")
else:
    run_disabled = st.session_state.pipeline_done
    if st.button("Run pipeline", type="primary", disabled=run_disabled):
        try:
            run_resp = run_pipeline(st.session_state.document_id)
            st.session_state.pipeline_job_id = run_resp["job_id"]
            st.session_state.report_id = run_resp["report_id"]
            st.session_state.pipeline_done = False
        except requests.HTTPError as exc:
            st.error(f"Pipeline run failed: {_detail(exc.response)}")
        except requests.RequestException as exc:
            st.error(f"Cannot reach API: {exc}")

    if st.session_state.pipeline_job_id and not st.session_state.pipeline_done:
        st.caption(f"Job: `{st.session_state.pipeline_job_id}`")
        progress_bar = st.progress(0, text="queued")
        status_slot = st.empty()
        while True:
            try:
                status = get_pipeline_status(st.session_state.pipeline_job_id)
            except requests.RequestException as exc:
                status_slot.error(f"Status poll failed: {exc}")
                break

            stage = status.get("stage", "queued")
            pct = int(status.get("progress", 0))
            progress_bar.progress(min(max(pct, 0), 100), text=f"{stage} — {pct}%")

            if stage in PIPELINE_TERMINAL_STAGES:
                if stage == "complete":
                    st.session_state.pipeline_done = True
                    status_slot.success("Pipeline complete.")
                else:
                    err = status.get("error") or "Pipeline failed"
                    status_slot.error(f"Pipeline failed: {err}")
                break
            time.sleep(POLL_INTERVAL_SECONDS)


# ── Step 3 — Review metrics ───────────────────────────────────────────────
st.subheader("3. Review extracted metrics")

if not st.session_state.pipeline_done:
    st.info("Run the pipeline first.")
else:
    try:
        metrics = list_metrics(st.session_state.document_id)
    except requests.HTTPError as exc:
        st.error(f"Failed to load metrics: {_detail(exc.response)}")
        metrics = []
    except requests.RequestException as exc:
        st.error(f"Cannot reach API: {exc}")
        metrics = []

    if not metrics:
        st.warning("No metrics were extracted for this document yet.")
    else:
        df = pd.DataFrame(
            [
                {
                    "gri_code": m.get("gri_code"),
                    "value": m.get("value"),
                    "unit": m.get("unit"),
                    "confidence": m.get("confidence"),
                    "status": m.get("status"),
                }
                for m in metrics
            ]
        )
        st.dataframe(df, use_container_width=True, hide_index=True)

        st.markdown("**Approve or reject individual metrics**")
        for m in metrics:
            metric_id = m["id"]
            label = f"{m.get('gri_code')} · {m.get('value')} {m.get('unit') or ''} · conf={m.get('confidence'):.2f} · {m.get('status')}"
            cols = st.columns([6, 1, 1])
            cols[0].write(label)
            if cols[1].button("Approve", key=f"approve-{metric_id}"):
                try:
                    review_metric(metric_id, "approved")
                    st.rerun()
                except requests.HTTPError as exc:
                    st.error(f"Approve failed: {_detail(exc.response)}")
            if cols[2].button("Reject", key=f"reject-{metric_id}"):
                try:
                    review_metric(metric_id, "rejected")
                    st.rerun()
                except requests.HTTPError as exc:
                    st.error(f"Reject failed: {_detail(exc.response)}")


# ── Step 4 — Generate report ──────────────────────────────────────────────
st.subheader("4. Generate report")

if not st.session_state.pipeline_done:
    st.info("Run the pipeline first.")
else:
    if st.button("Generate report", type="primary", disabled=st.session_state.report_ready):
        try:
            gen_resp = generate_report(st.session_state.document_id)
            st.session_state.report_id = gen_resp["report_id"]
            st.session_state.report_job_id = gen_resp["job_id"]
            st.session_state.report_ready = False
        except requests.HTTPError as exc:
            st.error(f"Report generation failed: {_detail(exc.response)}")
        except requests.RequestException as exc:
            st.error(f"Cannot reach API: {exc}")

    if (
        st.session_state.report_id
        and st.session_state.report_job_id
        and not st.session_state.report_ready
    ):
        st.caption(f"Report job: `{st.session_state.report_job_id}`")
        report_progress = st.progress(0, text="queued")
        report_slot = st.empty()
        # Indeterminate phases mapped to coarse percentages
        phase_pct = {"queued": 10, "generating": 60, "ready": 100, "failed": 100}
        while True:
            try:
                rep = get_report_status(
                    st.session_state.report_id,
                    job_id=st.session_state.report_job_id,
                )
            except requests.RequestException as exc:
                report_slot.error(f"Report status poll failed: {exc}")
                break

            job_state = rep.get("job_state") or "queued"
            report_progress.progress(phase_pct.get(job_state, 30), text=job_state)

            if job_state in REPORT_TERMINAL_STATES:
                if job_state == "ready":
                    st.session_state.report_ready = True
                    report_slot.success("Report ready.")
                else:
                    report_slot.error("Report generation failed.")
                break
            time.sleep(POLL_INTERVAL_SECONDS)


# ── Step 5 — Download PDF ─────────────────────────────────────────────────
st.subheader("5. Download PDF")

if not st.session_state.report_ready or not st.session_state.report_id:
    st.info("Generate the report first.")
else:
    try:
        pdf_bytes = download_pdf(st.session_state.report_id)
        st.download_button(
            label="Download report PDF",
            data=pdf_bytes,
            file_name=f"esg_report_{st.session_state.report_id}.pdf",
            mime="application/pdf",
            type="primary",
        )
    except requests.HTTPError as exc:
        st.error(f"PDF download failed: {_detail(exc.response)}")
    except requests.RequestException as exc:
        st.error(f"Cannot reach API: {exc}")