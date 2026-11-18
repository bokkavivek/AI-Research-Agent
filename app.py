"""Streamlit frontend for the AI Research Agent."""
import re

import streamlit as st

from agents import ResearchError, run_research
from db import (DatabaseError, create_user, get_user_reports, init_db,
                save_report, verify_user)

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

# ---------- Database setup ----------
try:
    init_db()
    db_ready = True
except DatabaseError as e:
    db_ready = False
    st.error(str(e))
    st.stop()


# ---------- Login / sign-up ----------
def login_screen():
    st.title("🔎 AI Research Agent By Vivek")
    st.write("Log in or create an account to run research. Your reports are private to you.")

    tab_login, tab_signup = st.tabs(["Log in", "Sign up"])

    with tab_login:
        with st.form("login_form"):
            u = st.text_input("Username", key="login_user", max_chars=50)
            p = st.text_input("Password", type="password", key="login_pass")
            if st.form_submit_button("Log in", type="primary"):
                try:
                    user_id = verify_user(u.strip().lower(), p)
                except DatabaseError as e:
                    st.error(str(e))
                    user_id = None
                if user_id:
                    st.session_state.user_id = user_id
                    st.session_state.username = u.strip().lower()
                    st.rerun()
                elif u and p:
                    st.error("Incorrect username or password.")

    with tab_signup:
        with st.form("signup_form"):
            u = st.text_input("Choose a username", key="signup_user", max_chars=50,
                              help="Letters, numbers, and underscores, 3-50 characters.")
            p = st.text_input("Choose a password", type="password", key="signup_pass",
                              help="At least 8 characters.")
            p2 = st.text_input("Confirm password", type="password", key="signup_pass2")
            if st.form_submit_button("Create account"):
                name = u.strip().lower()
                if not re.fullmatch(r"[a-z0-9_]{3,50}", name):
                    st.error("Username must be 3-50 characters: letters, numbers, or underscores.")
                elif len(p) < 8:
                    st.error("Password must be at least 8 characters.")
                elif p != p2:
                    st.error("Passwords do not match.")
                else:
                    try:
                        create_user(name, p)
                        st.session_state.user_id = verify_user(name, p)
                        st.session_state.username = name
                        st.rerun()
                    except DatabaseError as e:
                        st.error(str(e))


if "user_id" not in st.session_state:
    login_screen()
    st.stop()

user_id = st.session_state.user_id


# ---------- Logged-in app ----------
if "topic_input" not in st.session_state:
    st.session_state.topic_input = ""

with st.sidebar:
    st.header("Account")
    st.write(f"Logged in as **{st.session_state.username}**")
    if st.button("Log out"):
        for key in ["user_id", "username", "report", "report_topic"]:
            st.session_state.pop(key, None)
        st.rerun()

    st.divider()
    st.header("About")
    st.write("A multi-agent system built with **CrewAI** and **Groq**. "
             "Three agents work in sequence to turn a topic into a report.")
    st.subheader("Agents")
    st.markdown("1. **Researcher**: searches the web\n"
                "2. **Analyst**: extracts key insights\n"
                "3. **Report Writer**: writes the report")
    st.caption("Reports are AI-generated from web search snippets. "
               "Verify important facts using the listed sources.")

st.title("🔎 AI Research Agent By Vivek")
st.write("Enter a topic and three specialised AI agents will research it, "
         "analyse the findings and write a structured report.")

EXAMPLES_COLS = st.columns(len(EXAMPLES))
for col, ex in zip(EXAMPLES_COLS, EXAMPLES):
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
            try:
                save_report(user_id, topic.strip(), report)
                st.toast("Report saved to your history.")
            except Exception:
                st.warning("The report was generated but could not be saved.")
        except ResearchError as e:
            render_steps(box, done, failed=True)
            st.error(str(e))
        except Exception as e:
            render_steps(box, done, failed=True)
            st.error(f"Something went wrong ({type(e).__name__}). Please try again.")

if st.session_state.get("report"):
    st.divider()
    st.subheader("Research report")
    st.markdown(st.session_state.report)
    slug = re.sub(r"[^a-z0-9]+", "_", st.session_state.get("report_topic", "report").lower()).strip("_")
    st.download_button("Download report (.md)", data=st.session_state.report,
                       file_name=f"{slug[:50] or 'report'}.md", mime="text/markdown")

with st.sidebar:
    st.divider()
    st.subheader("Your past reports")
    try:
        history = get_user_reports(user_id)  # filtered by this user's ID only
    except Exception:
        history = []
        st.error("Could not load your history.")
    if not history:
        st.caption("No reports yet.")
    for row in history:
        with st.expander(row["topic"][:60]):
            st.markdown(row["report"])
            st.caption(f"{row['created_at']:%d %b %Y, %H:%M}")