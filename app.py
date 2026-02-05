import streamlit as st
import pandas as pd
import requests
import time
import altair as alt
import os

# ================================
# CONFIG – ENVIRONMENT VARIABLES
# ================================
UPLOAD_URL = os.getenv("UPLOAD_URL")
CLASSIFY_URL = os.getenv("CLASSIFY_URL")
FEEDBACK_URL = os.getenv("FEEDBACK_URL")
APPROVE_URL = os.getenv("APPROVE_URL")

if not all([UPLOAD_URL, CLASSIFY_URL, FEEDBACK_URL, APPROVE_URL]):
    st.error("❌ Missing environment variables. Please configure Streamlit Secrets.")
    st.stop()

# ================================
# PAGE SETUP
# ================================
st.set_page_config(
    page_title="SAF AI Ticket Intelligence Platform",
    layout="wide"
)

st.title("🤖 SAF AI Ticket Intelligence Platform")
st.caption("Enterprise AI • Human-in-the-Loop • UiPath Queue (POC Mode)")

# ================================
# SESSION STATE
# ================================
for key in ["job_id", "file_uploaded", "results_df"]:
    if key not in st.session_state:
        st.session_state[key] = None

# ================================
# HELPERS
# ================================
def confidence_band(conf):
    if conf < 70:
        return "LOW"
    if conf < 85:
        return "MEDIUM"
    if conf < 95:
        return "HIGH"
    return "VERY_HIGH"


def bot_badge(bot):
    if "CancelGWSSCases" in bot:
        return "🟦 " + bot
    if "RMS_India_Mendix" in bot:
        return "🟩 " + bot
    return "🟥 " + bot

# ================================
# UPLOAD
# ================================
st.subheader("📤 Upload Ticket Excel")
uploaded = st.file_uploader("Choose Excel file", type=["xlsx"])

if uploaded and not st.session_state.file_uploaded:
    with st.spinner("Uploading Excel..."):
        r = requests.post(UPLOAD_URL, files={"file": uploaded})

    st.session_state.job_id = r.json().get("job_id")
    st.session_state.file_uploaded = True
    st.success(f"📁 Job Created → `{st.session_state.job_id}`")

# ================================
# CLASSIFY
# ================================
if st.session_state.job_id and st.button("🚀 Run AI Classification"):
    with st.spinner("Running AI engine..."):
        r = requests.get(CLASSIFY_URL, params={"job_id": st.session_state.job_id})
        df = pd.DataFrame(r.json().get("results", []))

    if df.empty:
        st.warning("No results returned from AI service.")
    else:
        df["confidence"] = df.get("confidence", 80)
        df["confidence_band"] = df["confidence"].apply(confidence_band)
        df["ticket_id"] = df.get(
            "ticket_id", [f"TKT-{i+1}" for i in range(len(df))]
        )
        df["bot"] = df.get("bot", "ManualReview").replace({
            "Pega Bot": "CancelGWSSCases",
            "Mendix Bot": "RMS_India_Mendix"
        })

        st.session_state.results_df = df

# ================================
# KPI DASHBOARD
# ================================
if st.session_state.results_df is not None:
    df = st.session_state.results_df

    st.subheader("📊 Executive KPIs")
    c1, c2, c3, c4 = st.columns(4)

    c1.metric("🎫 Total Tickets", len(df))
    c2.metric("🟢 High Confidence", len(df[df.confidence >= 90]))
    c3.metric(
        "🤖 Automation %",
        f"{int(len(df[df.bot != 'ManualReview']) / len(df) * 100)}%"
    )
    c4.metric("🧑 Manual Review", len(df[df.bot == "ManualReview"]))

    st.divider()

    # ================================
    # ANALYTICS GRAPHS
    # ================================
    st.subheader("📈 AI Decision Analytics")

    g1, g2 = st.columns(2)

    with g1:
        st.markdown("**Bot Distribution**")
        st.altair_chart(
            alt.Chart(df)
            .mark_bar()
            .encode(x="bot", y="count()", color="bot"),
            use_container_width=True
        )

    with g2:
        st.markdown("**Confidence Band Distribution**")
        st.altair_chart(
            alt.Chart(df)
            .mark_bar()
            .encode(
                x="confidence_band",
                y="count()",
                color="confidence_band"
            ),
            use_container_width=True
        )

    st.markdown("**Confidence Trend**")
    st.altair_chart(
        alt.Chart(df.reset_index())
        .mark_line(point=True)
        .encode(x="index", y="confidence", color="bot"),
        use_container_width=True
    )

# ================================
# RESULTS + BOT TRIGGER
# ================================
if st.session_state.results_df is not None:
    st.subheader("📋 Ticket Review & Approval")

    for i, row in df.iterrows():
        with st.expander(
            f"{row.ticket_id} | {bot_badge(row.bot)} | {row.confidence}%"
        ):
            st.write("**Predicted Category:**", row.get("predicted_category", "N/A"))
            st.write("**Reasoning:**", row.get("reasoning", "N/A"))

            col1, col2 = st.columns(2)

            if col1.button("✅ Approve", key=f"approve_{i}"):
                with st.spinner("🤖 Triggering UiPath Bot..."):
                    time.sleep(0.5)
                    requests.post(
                        APPROVE_URL,
                        json={
                            "ticketId": row.ticket_id,
                            "botName": row.bot,
                            "approvedBy": "HITL_User"
                        }
                    )
                st.success("🎉 Bot Successfully Triggered!")
                st.toast("UiPath job submitted 🚀", icon="🤖")

            with col2:
                new_cat = st.text_input(
                    "Correct Category", key=f"cat_{i}"
                )
                new_bot = st.selectbox(
                    "Correct Bot",
                    ["CancelGWSSCases", "RMS_India_Mendix", "Others"],
                    key=f"bot_{i}"
                )

                if st.button("Reject", key=f"rej_{i}"):
                    requests.post(
                        FEEDBACK_URL,
                        json={
                            "ticket_id": row.ticket_id,
                            "correct_category": new_cat,
                            "keywords": new_cat.split(),
                            "bot_name": new_bot
                        }
                    )
                    st.warning("Feedback submitted & model updated 🧠")
