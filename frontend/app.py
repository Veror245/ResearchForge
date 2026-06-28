import streamlit as st
import requests
import time

API_URL = "http://localhost:8000"

st.set_page_config(page_title="ResearchForge", layout="wide", initial_sidebar_state="expanded")

# === Custom CSS ===
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Merriweather:ital,wght@0,300;0,400;0,700;1,300;1,400&display=swap');

    /* Global */
    html, body, [class*="css-"] {
        font-family: 'Inter', sans-serif;
    }
    .main .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }

    /* Sidebar step cards */
    .step-card {
        background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%);
        border-radius: 14px;
        padding: 14px 16px;
        margin-bottom: 10px;
        color: #ffffff;
        box-shadow: 0 4px 12px rgba(79, 70, 229, 0.25);
        transition: all 0.25s ease;
        position: relative;
        overflow: hidden;
    }
    .step-card::before {
        content: "";
        position: absolute;
        top: 0; left: 0; right: 0; height: 3px;
        background: rgba(255,255,255,0.4);
    }
    .step-card:hover {
        transform: translateX(6px);
        box-shadow: 0 6px 20px rgba(79, 70, 229, 0.35);
    }
    .step-icon {
        font-size: 22px;
        margin-bottom: 6px;
        display: block;
    }
    .step-title {
        font-size: 13px;
        font-weight: 700;
        letter-spacing: 0.3px;
        margin-bottom: 3px;
        text-transform: uppercase;
    }
    .step-desc {
        font-size: 11.5px;
        opacity: 0.85;
        line-height: 1.45;
        font-weight: 400;
    }
    .step-number-badge {
        position: absolute;
        top: 10px;
        right: 12px;
        background: rgba(255,255,255,0.2);
        border-radius: 50%;
        width: 24px;
        height: 24px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 11px;
        font-weight: 700;
    }

    /* Agent log cards */
    .agent-log-container {
        background: #ffffff;
        border-radius: 12px;
        padding: 14px 18px;
        margin-bottom: 10px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        border-left: 4px solid;
        transition: transform 0.15s ease;
    }
    .agent-log-container:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.08);
    }
    .agent-planner      { border-left-color: #8b5cf6; background: linear-gradient(to right, #faf5ff, #ffffff); }
    .agent-research     { border-left-color: #3b82f6; background: linear-gradient(to right, #eff6ff, #ffffff); }
    .agent-claim_extractor { border-left-color: #10b981; background: linear-gradient(to right, #ecfdf5, #ffffff); }
    .agent-critic       { border-left-color: #f59e0b; background: linear-gradient(to right, #fffbeb, #ffffff); }
    .agent-debate       { border-left-color: #ef4444; background: linear-gradient(to right, #fef2f2, #ffffff); }
    .agent-report_writer { border-left-color: #6366f1; background: linear-gradient(to right, #eef2ff, #ffffff); }
    .agent-unknown      { border-left-color: #9ca3af; background: #ffffff; }

    .agent-header {
        font-weight: 700;
        font-size: 12.5px;
        margin-bottom: 6px;
        display: flex;
        align-items: center;
        gap: 8px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .agent-planner .agent-header      { color: #7c3aed; }
    .agent-research .agent-header     { color: #2563eb; }
    .agent-claim_extractor .agent-header { color: #059669; }
    .agent-critic .agent-header       { color: #d97706; }
    .agent-debate .agent-header       { color: #dc2626; }
    .agent-report_writer .agent-header { color: #4f46e5; }
    .agent-unknown .agent-header      { color: #6b7280; }

    .agent-badge {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 6px;
        font-size: 10px;
        font-weight: 700;
        color: white;
        margin-left: auto;
    }
    .agent-planner .agent-badge      { background: #8b5cf6; }
    .agent-research .agent-badge     { background: #3b82f6; }
    .agent-claim_extractor .agent-badge { background: #10b981; }
    .agent-critic .agent-badge       { background: #f59e0b; }
    .agent-debate .agent-badge       { background: #ef4444; }
    .agent-report_writer .agent-badge { background: #6366f1; }
    .agent-unknown .agent-badge      { background: #9ca3af; }

    .agent-message {
        font-size: 13.5px;
        color: #374151;
        line-height: 1.6;
        font-weight: 400;
    }

    /* Live activity panel */
    .live-panel {
        background: #f8fafc;
        border-radius: 16px;
        padding: 20px;
        border: 1px solid #e2e8f0;
    }
    .live-header {
        display: flex;
        align-items: center;
        gap: 10px;
        margin-bottom: 16px;
        padding-bottom: 12px;
        border-bottom: 1px solid #e2e8f0;
    }
    .live-dot {
        width: 10px;
        height: 10px;
        background: #10b981;
        border-radius: 50%;
        animation: pulse 2s infinite;
        box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7);
    }
    @keyframes pulse {
        0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }
        70% { transform: scale(1); box-shadow: 0 0 0 10px rgba(16, 185, 129, 0); }
        100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
    }
    .live-title {
        font-size: 16px;
        font-weight: 700;
        color: #1e293b;
        margin: 0;
    }
    .live-subtitle {
        font-size: 12px;
        color: #64748b;
        margin-left: auto;
    }

    /* Report Document */
    .report-wrapper {
        background: #f1f5f9;
        border-radius: 20px;
        padding: 32px;
        margin-top: 24px;
    }
    .report-document {
        background: #ffffff;
        border-radius: 12px;
        box-shadow: 0 25px 50px -12px rgba(0,0,0,0.15);
        padding: 56px 64px;
        max-width: 850px;
        margin: 0 auto;
        border: 1px solid #e2e8f0;
        position: relative;
    }
    .report-document::before {
        content: "";
        position: absolute;
        top: 0; left: 0; right: 0;
        height: 6px;
        background: linear-gradient(90deg, #4f46e5, #7c3aed, #ec4899);
        border-radius: 12px 12px 0 0;
    }
    .report-header {
        text-align: center;
        padding-bottom: 28px;
        margin-bottom: 32px;
        border-bottom: 2px solid #1e293b;
    }
    .report-title {
        font-family: 'Merriweather', serif;
        font-size: 30px;
        font-weight: 700;
        color: #0f172a;
        margin-bottom: 10px;
        line-height: 1.3;
    }
    .report-meta {
        font-size: 11px;
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 2px;
        font-weight: 600;
    }
    .report-seal {
        display: inline-block;
        margin-top: 16px;
        padding: 6px 16px;
        background: #f0fdf4;
        color: #15803d;
        border-radius: 20px;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 1px;
        border: 1px solid #bbf7d0;
    }
    .report-body {
        font-family: 'Merriweather', serif;
        font-size: 15px;
        line-height: 1.85;
        color: #334155;
    }
    .report-body h1, .report-body h2, .report-body h3, .report-body h4 {
        font-family: 'Inter', sans-serif;
        font-weight: 700;
        color: #0f172a;
        margin-top: 36px;
        margin-bottom: 16px;
        line-height: 1.3;
    }
    .report-body h1 { font-size: 26px; border-bottom: 2px solid #e2e8f0; padding-bottom: 10px; }
    .report-body h2 { font-size: 21px; color: #1e293b; }
    .report-body h3 { font-size: 17px; color: #334155; }
    .report-body h4 { font-size: 15px; color: #475569; }
    .report-body p { margin-bottom: 18px; }
    .report-body strong { color: #0f172a; font-weight: 700; }
    .report-body blockquote {
        border-left: 4px solid #cbd5e1;
        padding: 12px 20px;
        margin: 20px 0;
        color: #475569;
        font-style: italic;
        background: #f8fafc;
        border-radius: 0 8px 8px 0;
    }
    .report-body code {
        background: #f1f5f9;
        padding: 3px 8px;
        border-radius: 6px;
        font-size: 13px;
        color: #475569;
        font-family: 'Menlo', monospace;
        border: 1px solid #e2e8f0;
    }
    .report-body pre {
        background: #f8fafc;
        padding: 16px;
        border-radius: 10px;
        overflow-x: auto;
        border: 1px solid #e2e8f0;
    }
    .report-body ul, .report-body ol {
        margin-left: 24px;
        margin-bottom: 18px;
        padding-left: 8px;
    }
    .report-body li { margin-bottom: 6px; }
    .report-body hr {
        border: none;
        border-top: 1px solid #e2e8f0;
        margin: 28px 0;
    }
    .report-body table {
        width: 100%;
        border-collapse: collapse;
        margin: 20px 0;
        font-size: 14px;
    }
    .report-body th {
        background: #f8fafc;
        font-weight: 600;
        text-align: left;
        padding: 10px 12px;
        border-bottom: 2px solid #e2e8f0;
    }
    .report-body td {
        padding: 10px 12px;
        border-bottom: 1px solid #e2e8f0;
    }

    /* Input area */
    .stTextInput > div > div > input {
        border-radius: 10px !important;
        border: 2px solid #e2e8f0 !important;
        padding: 14px 18px !important;
        font-size: 15px !important;
        transition: all 0.2s !important;
    }
    .stTextInput > div > div > input:focus {
        border-color: #4f46e5 !important;
        box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.1) !important;
    }
    .stButton > button {
        border-radius: 10px !important;
        padding: 12px 28px !important;
        font-weight: 600 !important;
        letter-spacing: 0.3px !important;
        transition: all 0.2s !important;
    }
    .stButton > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(79, 70, 229, 0.3);
    }

    /* Scrollbar */
    ::-webkit-scrollbar { width: 8px; height: 8px; }
    ::-webkit-scrollbar-track { background: #f1f5f9; }
    ::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 4px; }
    ::-webkit-scrollbar-thumb:hover { background: #94a3b8; }
</style>
""", unsafe_allow_html=True)

# === Header ===
left, right = st.columns([3, 1])
with left:
    st.title("🔬 ResearchForge")
    st.caption("Autonomous multi-agent research platform — ask a question, watch the agents work, get a report with confidence score.")
with right:
    st.markdown("<div style='text-align:right; padding-top:10px;'><span style='background:linear-gradient(90deg,#4f46e5,#7c3aed); color:white; padding:6px 14px; border-radius:20px; font-size:12px; font-weight:600;'>v2.0 · Multi-Agent</span></div>", unsafe_allow_html=True)

st.markdown("---")

# === Sidebar ===
with st.sidebar:
    st.header("How it works")

    steps = [
        ("🧠", "Planner", "Breaks the question into sub-queries and builds a research strategy."),
        ("🌐", "Research Workers", "Search the web and crawl pages to gather raw evidence."),
        ("📝", "Claim Extractor", "Pulls factual claims and statements from the collected text."),
        ("🔍", "Critic", "Challenges claims, checks for bias, and verifies sources."),
        ("⚖️", "Debate", "Generates opposing arguments to stress-test conclusions."),
        ("📄", "Report Writer", "Synthesises everything into a polished final document."),
    ]

    for i, (icon, title, desc) in enumerate(steps, 1):
        st.markdown(f"""
        <div class="step-card">
            <div class="step-number-badge">{i}</div>
            <span class="step-icon">{icon}</span>
            <div class="step-title">{title}</div>
            <div class="step-desc">{desc}</div>
        </div>
        """, unsafe_allow_html=True)

    st.divider()
    st.caption("Built with FastAPI · Redis Streams · LangGraph · Local LLMs")

# === Main Input ===
query = st.text_input("Research question", placeholder="e.g. Will open-source voice cloning surpass commercial providers by 2030?")

if st.button("Start Research", type="primary") and query:
    # 1. Create job
    with st.spinner("🚀 Creating research job..."):
        resp = requests.post(f"{API_URL}/research", params={"query": query})
        if resp.status_code != 200:
            st.error("❌ Failed to create job. Is the API running?")
            st.stop()
        job_id = resp.json()["job_id"]

    st.success(f"✅ Job `{job_id}` created successfully.")
    st.markdown("---")

    # Placeholders
    log_area = st.empty()
    report_placeholder = st.empty()
    pdf_placeholder = st.empty()

    max_checks = 180
    report_ready = False
    all_logs = []

    agent_meta = {
        "planner":        ("🧠", "Planner",       "#8b5cf6"),
        "research":       ("🌐", "Research",      "#3b82f6"),
        "claim_extractor":("📝", "Claim Extractor","#10b981"),
        "critic":         ("🔍", "Critic",        "#f59e0b"),
        "debate":         ("⚖️", "Debate",        "#ef4444"),
        "report_writer":  ("📄", "Report Writer", "#6366f1"),
    }

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

        # Build styled log display
        if all_logs:
            log_html = '<div class="live-panel"><div class="live-header"><div class="live-dot"></div><div class="live-title">⚡ Live Agent Activity</div><div class="live-subtitle">Streaming...</div></div>'
            for log in all_logs:
                agent = log.get("agent", "unknown")
                msg = log.get("message", "")
                icon, label, color = agent_meta.get(agent, ("▪️", "Unknown", "#9ca3af"))
                safe_agent = agent.replace("-", "_").replace(" ", "_")
                log_html += f"""
                <div class="agent-log-container agent-{safe_agent}">
                    <div class="agent-header">
                        <span>{icon}</span>
                        <span>{label}</span>
                        <span class="agent-badge">AGENT</span>
                    </div>
                    <div class="agent-message">{msg}</div>
                </div>
                """
            log_html += '</div>'
            log_area.markdown(log_html, unsafe_allow_html=True)
        else:
            log_area.markdown("""
            <div class="live-panel">
                <div class="live-header">
                    <div class="live-dot"></div>
                    <div class="live-title">⚡ Live Agent Activity</div>
                </div>
                <div style="text-align:center; padding:40px; color:#94a3b8;">
                    <div style="font-size:32px; margin-bottom:12px;">⏳</div>
                    <div style="font-size:14px;">Waiting for first agent steps...</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

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
        st.warning("⏱️ Report did not complete within the time limit. The job may still be running.")
        st.stop()

    # 3. Final log update
    try:
        logs_resp = requests.get(f"{API_URL}/job/{job_id}/logs?count=100")
        if logs_resp.status_code == 200:
            final_logs = logs_resp.json().get("logs", [])
            if final_logs:
                log_html = '<div class="live-panel"><div class="live-header"><div class="live-dot" style="background:#3b82f6; box-shadow:0 0 0 0 rgba(59,130,246,0.7);"></div><div class="live-title">✅ Final Agent Activity</div><div class="live-subtitle">Complete</div></div>'
                for log in final_logs:
                    agent = log.get("agent", "unknown")
                    msg = log.get("message", "")
                    icon, label, color = agent_meta.get(agent, ("▪️", "Unknown", "#9ca3af"))
                    safe_agent = agent.replace("-", "_").replace(" ", "_")
                    log_html += f"""
                    <div class="agent-log-container agent-{safe_agent}">
                        <div class="agent-header">
                            <span>{icon}</span>
                            <span>{label}</span>
                            <span class="agent-badge">DONE</span>
                        </div>
                        <div class="agent-message">{msg}</div>
                    </div>
                    """
                log_html += '</div>'
                log_area.markdown(log_html, unsafe_allow_html=True)
    except Exception:
        pass

    # 4. Display report in document style
    report_md = requests.get(f"{API_URL}/job/{job_id}/report/markdown").json()["markdown"]

    report_placeholder.markdown(f"""
    <div class="report-wrapper">
        <div class="report-document">
            <div class="report-header">
                <div class="report-title">Research Report</div>
                <div class="report-meta">ResearchForge · Autonomous Multi-Agent System</div>
                <div class="report-seal">✓ VERIFIED OUTPUT</div>
            </div>
            <div class="report-body">
                {report_md}
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 5. PDF Download (kept as-is)
    pdf_resp = requests.get(f"{API_URL}/job/{job_id}/report/pdf")
    if pdf_resp.status_code == 200:
        pdf_placeholder.download_button(
            label="📥 Download PDF Report",
            data=pdf_resp.content,
            file_name=f"report_{job_id}.pdf",
            mime="application/pdf",
        )
    else:
        pdf_placeholder.warning("⚠️ PDF generation failed. You can still view the Markdown report above.")

    st.balloons()