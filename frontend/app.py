import streamlit as st
import requests
import time

API_URL = "http://localhost:8000"   # adjust if needed

st.set_page_config(page_title="ResearchForge", layout="wide")
st.title("🔬 ResearchForge")
st.caption("Autonomous multi‑agent research platform — ask a question, watch the agents work, get a report with confidence score.")

# --- Sidebar ---
with st.sidebar:
    st.header("How it works")
    st.markdown("""
    1. **Planner** breaks the question into sub‑queries.
    2. **Research Workers** search the web and crawl pages.
    3. **Claim Extractor** pulls factual claims from the text.
    4. **Critic** challenges those claims.
    5. **Debate** generates opposing arguments.
    6. **Report Writer** synthesises everything into a final document.
    """)
    st.divider()
    st.caption("Built with FastAPI, Redis Streams, LangGraph, and local LLMs.")

# --- Main input ---
query = st.text_input("Research question", placeholder="e.g. Will open‑source voice cloning surpass commercial providers by 2030?")

if st.button("Start Research", type="primary") and query:
    # 1. Create job
    with st.spinner("Creating research job..."):
        resp = requests.post(f"{API_URL}/research", params={"query": query})
        if resp.status_code != 200:
            st.error("Failed to create job. Is the API running?")
            st.stop()
        job_id = resp.json()["job_id"]

    st.success(f"Job `{job_id}` created.")
    st.divider()

    # Placeholders for live logs and final report
    log_area = st.empty()
    report_area = st.empty()
    pdf_area = st.empty()

    # 2. Poll for logs and report readiness
    max_checks = 120   # 10 minutes at 5s intervals
    report_ready = False
    all_logs = []      # accumulate logs to keep them visible

    for _ in range(max_checks):
        # Fetch logs
        try:
            logs_resp = requests.get(f"{API_URL}/job/{job_id}/logs?count=50")
            if logs_resp.status_code == 200:
                new_logs = logs_resp.json().get("logs", [])
                # Avoid duplicates by keeping track of messages (simple: compare last)
                if new_logs and (not all_logs or new_logs[-1] != all_logs[-1]):
                    all_logs = new_logs
        except Exception:
            pass

        # Update log display
        if all_logs:
            log_text = "\n".join([f"`{log['agent']}` : {log['message']}" for log in all_logs])
            log_area.markdown("### ⚡ Live Agent Activity\n" + log_text)
        else:
            log_area.markdown("### ⚡ Live Agent Activity\n⏳ Waiting for first steps...")

        # Check if report is ready
        try:
            report_resp = requests.get(f"{API_URL}/job/{job_id}/report/markdown")
            if report_resp.status_code == 200:
                report_ready = True
                break
        except Exception:
            pass

        time.sleep(5)   # poll every 5 seconds

    if not report_ready:
        st.warning("Report did not complete within the time limit. The job may still be running.")
        st.stop()

    # 3. Display final logs and the report
    # Final log refresh
    try:
        logs_resp = requests.get(f"{API_URL}/job/{job_id}/logs?count=100")
        if logs_resp.status_code == 200:
            final_logs = logs_resp.json().get("logs", [])
            if final_logs:
                log_text = "\n".join([f"`{log['agent']}` : {log['message']}" for log in final_logs])
                log_area.markdown("### ⚡ Final Agent Activity\n" + log_text)
    except Exception:
        pass

    # Display report
    report_md = requests.get(f"{API_URL}/job/{job_id}/report/markdown").json()["markdown"]
    report_area.markdown("---")
    report_area.header("📄 Research Report")
    report_area.markdown(report_md)

    # PDF download
    pdf_resp = requests.get(f"{API_URL}/job/{job_id}/report/pdf")
    if pdf_resp.status_code == 200:
        pdf_area.download_button(
            label="📥 Download PDF Report",
            data=pdf_resp.content,
            file_name=f"report_{job_id}.pdf",
            mime="application/pdf",
        )
    else:
        pdf_area.warning("PDF generation failed. You can still view the Markdown above.")

    st.balloons()