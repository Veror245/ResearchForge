import streamlit as st
import requests
import time

API_URL = "http://localhost:8000"

st.set_page_config(page_title="ResearchForge", layout="wide")
st.title("🔬 ResearchForge")
st.caption("Autonomous multi‑agent research platform — ask a question, watch the agents work, get a report with confidence score.")

# --- Sidebar (unchanged) ---
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

    # Placeholders
    log_area = st.empty()
    report_placeholder = st.empty()
    pdf_placeholder = st.empty()

    max_checks = 180
    report_ready = False
    all_logs = []

    for _ in range(max_checks):
        # Fetch logs
        try:
            logs_resp = requests.get(f"{API_URL}/job/{job_id}/logs?count=50")
            if logs_resp.status_code == 200:
                new_logs = logs_resp.json().get("logs", [])
                if new_logs and (not all_logs or new_logs[-1] != all_logs[-1]):
                    all_logs = new_logs
        except Exception:
            pass

        # Build a clean, vertical log display with bold agent names
        if all_logs:
            log_lines = []
            for log in all_logs:
                agent = log.get("agent", "unknown")
                msg = log.get("message", "")
                # Map agent names to icons (optional)
                icon = {
                    "planner": "🧠",
                    "research": "🌐",
                    "claim_extractor": "📝",
                    "critic": "🔍",
                    "debate": "⚖️",
                    "report_writer": "📄"
                }.get(agent, "▪️")
                # Bold agent name with icon, slightly larger font via h5
                log_lines.append(f"**{icon} {agent.replace('_', ' ').title()}**  \n{msg}")
            log_area.markdown("### ⚡ Live Agent Activity\n" + "\n\n".join(log_lines))
        else:
            log_area.markdown("### ⚡ Live Agent Activity\n⏳ Waiting for first steps...")

        # Check if report ready
        try:
            report_resp = requests.get(f"{API_URL}/job/{job_id}/report/markdown")
            if report_resp.status_code == 200:
                report_ready = True
                break
        except Exception:
            pass

        time.sleep(5)

    if not report_ready:
        st.warning("Report did not complete within the time limit. The job may still be running.")
        st.stop()

    # 3. Final log update
    try:
        logs_resp = requests.get(f"{API_URL}/job/{job_id}/logs?count=100")
        if logs_resp.status_code == 200:
            final_logs = logs_resp.json().get("logs", [])
            if final_logs:
                log_lines = []
                for log in final_logs:
                    agent = log.get("agent", "unknown")
                    msg = log.get("message", "")
                    icon = {
                        "planner": "🧠",
                        "research": "🌐",
                        "claim_extractor": "📝",
                        "critic": "🔍",
                        "debate": "⚖️",
                        "report_writer": "📄"
                    }.get(agent, "▪️")
                    log_lines.append(f"**{icon} {agent.replace('_', ' ').title()}**  \n{msg}")
                log_area.markdown("### ⚡ Final Agent Activity\n" + "\n\n".join(log_lines))
    except Exception:
        pass

    # 4. Display report
    report_md = requests.get(f"{API_URL}/job/{job_id}/report/markdown").json()["markdown"]
    report_placeholder.markdown("---")
    report_placeholder.header("📄 Research Report")
    report_placeholder.markdown(report_md)

    # 5. PDF Download
    pdf_resp = requests.get(f"{API_URL}/job/{job_id}/report/pdf")
    if pdf_resp.status_code == 200:
        pdf_placeholder.download_button(
            label="📥 Download PDF Report",
            data=pdf_resp.content,
            file_name=f"report_{job_id}.pdf",
            mime="application/pdf",
        )
    else:
        pdf_placeholder.warning("PDF generation failed. You can still view the Markdown above.")

    st.balloons()