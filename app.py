"""Streamlit frontend for the AI Research Agent."""
import re

import streamlit as st

from agents import ResearchError, run_research

STEPS = ["Researcher", "Analyst", "Report Writer"]
EXAMPLES = ["Impact of AI on healthcare", "Electric vehicle adoption in India",
            "Retrieval-Augmented Generation trends"]

st.set_page_config(page_title="AI Research Agent By Vivek", page_icon="🔎", layout="wide")

st.markdown(
    """
    <style>
    .block-container {padding-top: 2rem; max-width: 1000px;}
    .step {padding: .55rem .9rem; border-radius: .5rem; margin-bottom: .4rem;
           border: 1px solid rgba(128,128,128,.35);}
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------- Sidebar ----------
with st.sidebar:
    st.header("About")
    st.write("A multi-agent system built with **CrewAI** and **Groq**. "
             "Three agents work in sequence to turn a topic into a report.")
    st.subheader("Agents")
    st.markdown("1. **Researcher**: searches the web\n"
                "2. **Analyst**: extracts key insights\n"
                "3. **Report Writer**: writes the report")
    st.subheader("How to use")
    st.markdown("1. Enter a topic\n2. Click **Run research**\n"
                "3. Wait 30-90 seconds\n4. Read or download the report")
    st.caption("Reports are AI-generated from web search snippets. "
               "Verify important facts using the listed sources.")

# ---------- Header ----------
st.title("🔎 AI Research Agent By Vivek")
st.write("Enter a topic and three specialised AI agents will research it, "
         "analyse the findings and write a structured report.")

if "topic_input" not in st.session_state:
    st.session_state.topic_input = ""

cols = st.columns(len(EXAMPLES))
for col, ex in zip(cols, EXAMPLES):
    if col.button(ex, use_container_width=True):
        st.session_state.topic_input = ex

topic = st.text_input("Research topic", key="topic_input",
                      placeholder="e.g. Future of renewable energy in India",
                      max_chars=200)
run = st.button("Run research", type="primary")


def render_steps(box, done, failed=False):
    lines = []
    for name in STEPS:
        if name in done:
            icon, state = "✅", "done"
        elif not failed and name == next((s for s in STEPS if s not in done), None):
            icon, state = "⏳", "working..."
        else:
            icon, state = "⚪", "waiting"
        lines.append(f'<div class="step">{icon} <b>{name}</b>: {state}</div>')
    box.markdown("".join(lines), unsafe_allow_html=True)


# ---------- Run ----------
if run:
    st.session_state.pop("report", None)
    if not topic.strip():
        st.warning("Please enter a research topic.")
    else:
        done = set()
        box = st.empty()
        render_steps(box, done)

        def on_step(name):
            done.add(name)
            render_steps(box, done)

        try:
            with st.spinner("Agents are working..."):
                report = run_research(topic, on_step=on_step)
            render_steps(box, set(STEPS))
            st.session_state.report = report
            st.session_state.report_topic = topic.strip()
        except ResearchError as e:
            render_steps(box, done, failed=True)
            st.error(str(e))
        except Exception as e:  # last-resort guard; never show raw details/keys
            render_steps(box, done, failed=True)
            st.error(f"Something went wrong ({type(e).__name__}). Please try again.")

# ---------- Result (kept in session so the download click doesn't erase it) ----------
if st.session_state.get("report"):
    st.divider()
    st.subheader("Research report")
    st.markdown(st.session_state.report)
    slug = re.sub(r"[^a-z0-9]+", "_", st.session_state.get("report_topic", "report").lower()).strip("_")
    st.download_button("Download report (.md)", data=st.session_state.report,
                       file_name=f"{slug[:50] or 'report'}.md", mime="text/markdown")
