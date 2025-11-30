# topics_app.py
# Streamlit app: Topic Submission using Google Sheets backend
# Requirements: streamlit, pandas, gspread, gspread-dataframe, oauth2client

import streamlit as st
import pandas as pd
import re
import json
from datetime import datetime
from difflib import SequenceMatcher
import gspread
from gspread_dataframe import set_with_dataframe

# ================= CONFIG =================
SIMILARITY_THRESHOLD = 0.5
REG_PREFIX = "23130910831"
REG_MAX_LAST = 48
FORBIDDEN_ROLL_SUFFIX = {"08", "29", "13"}
WORKSHEET_NAME = "Submissions"  # sheet tab name in Google Sheets
# ==========================================

st.set_page_config(page_title="Topic Submission", page_icon="📝", layout="centered")
st.title("Topic Submission Form")
st.caption("Fill your details and choose a topic. Submissions are saved to a Google Sheet.")

# ---------------- Helpers -----------------
def is_similar(a: str, b: str, threshold=SIMILARITY_THRESHOLD) -> bool:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio() >= threshold

def gspread_client_from_secrets():
    """
    Create a gspread client using the JSON in st.secrets['gcp_service_account_key'].
    The secret should contain the full JSON (as an object or string).
    """
    raw = st.secrets["gcp_service_account_key"]
    # If secret value is a string (the JSON text) parse it, otherwise assume it's already a dict
    if isinstance(raw, str):
        sa_info = json.loads(raw)
    else:
        sa_info = raw
    return gspread.service_account_from_dict(sa_info)

def load_sheet_df():
    """Return DataFrame from the Google Sheet (worksheet WORKSHEET_NAME) or None."""
    try:
        gc = gspread_client_from_secrets()
        sh = gc.open_by_key(st.secrets["sheet_id"])
        try:
            ws = sh.worksheet(WORKSHEET_NAME)
        except gspread.WorksheetNotFound:
            # create worksheet if not exists (empty)
            ws = sh.add_worksheet(title=WORKSHEET_NAME, rows=1000, cols=20)
            return None
        data = ws.get_all_records()
        if not data:
            return None
        df = pd.DataFrame(data)
        # prefer consistent column name "Topic"
        if "Topic Title" in df.columns and "Topic" not in df.columns:
            df = df.rename(columns={"Topic Title": "Topic"})
        if "Register Number" in df.columns:
            df["Register Number"] = df["Register Number"].astype(str)
        return df
    except Exception as e:
        st.error("Error reading Google Sheet: " + str(e))
        return None

def save_df_to_sheet(df: pd.DataFrame) -> bool:
    """Overwrite the worksheet with df (header + rows). Returns True on success."""
    try:
        gc = gspread_client_from_secrets()
        sh = gc.open_by_key(st.secrets["sheet_id"])
        try:
            ws = sh.worksheet(WORKSHEET_NAME)
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title=WORKSHEET_NAME, rows=1000, cols=20)
        # Ensure Register Number column is string to avoid formatting issues
        if "Register Number" in df.columns:
            df["Register Number"] = df["Register Number"].astype(str)
        set_with_dataframe(ws, df)  # writes header + data
        return True
    except Exception as e:
        st.error("Error saving to Google Sheet: " + str(e))
        return False

def validate_regno(r: str):
    if not re.fullmatch(r"\d{13}", r):
        return False, "Register number must be exactly 13 digits."
    if not r.startswith(REG_PREFIX):
        return False, f"Register must start with {REG_PREFIX}."
    try:
        last = int(r[-2:])
    except Exception:
        return False, "Last two characters must be digits."
    if not (1 <= last <= REG_MAX_LAST):
        return False, f"Last two digits must be between 01 and {REG_MAX_LAST}."
    return True, ""

def validate_rollno(r: str):
    # case-insensitive on 'd' (accept D or d)
    m = re.fullmatch(r"^23d12(\d{2})$", r, re.I)
    if not m:
        return False, "Roll format must start with 23d12 (d or D) followed by two digits (e.g. 23d1201)."
    suffix = m.group(1)
    if suffix in FORBIDDEN_ROLL_SUFFIX:
        return False, f"Roll suffix {suffix} is reserved (TC students). Choose another suffix."
    return True, ""

def show_submission_count():
    df = load_sheet_df()
    total = len(df) if df is not None else 0
    st.sidebar.info(f"📊 Total submissions: {total}")

# ---------------- Session-state UI flow ----------------
# initialize session state
if "step" not in st.session_state:
    st.session_state.step = "details"   # values: 'details', 'topic', 'confirm', 'done'
if "name" not in st.session_state:
    st.session_state.name = ""
if "regno" not in st.session_state:
    st.session_state.regno = ""
if "rollno" not in st.session_state:
    st.session_state.rollno = ""
if "topic" not in st.session_state:
    st.session_state.topic = ""

def goto_topic():
    st.session_state.step = "topic"
    st.rerun()

def back_to_details():
    st.session_state.step = "details"
    st.rerun()

def goto_confirm():
    st.session_state.step = "confirm"
    st.rerun()

def finish_and_reset():
    st.session_state.step = "details"
    st.session_state.name = ""
    st.session_state.regno = ""
    st.session_state.rollno = ""
    st.session_state.topic = ""
    st.rerun()

# ---------- DETAILS STEP ----------
if st.session_state.step == "details":
    with st.form("details_form", clear_on_submit=False):
        st.subheader("Enter your details")
        name = st.text_input("Name", value=st.session_state.name, help="Your full name")
        regno = st.text_input(f"Register Number (must start with {REG_PREFIX}, last two digits 01–{REG_MAX_LAST})",
                              value=st.session_state.regno,
                              help=f"Example: {REG_PREFIX}01")
        rollno = st.text_input("Roll Number (must start with 23d12; forbidden suffixes: 08,29,13)",
                               value=st.session_state.rollno,
                               help="Example: 23d1201")
        submitted_basic = st.form_submit_button("Continue →")

    if submitted_basic:
        # Basic validations
        if any(v.strip().lower() in ("exit", "quit") for v in (name, regno, rollno)):
            st.warning("Exit requested. Nothing saved.")
            st.stop()

        ok = True
        if not name.strip():
            st.error("Name cannot be empty.")
            ok = False
        v_reg, msg_reg = validate_regno(regno.strip())
        if not v_reg:
            st.error(msg_reg)
            ok = False
        v_roll, msg_roll = validate_rollno(rollno.strip())
        if not v_roll:
            st.error(msg_roll)
            ok = False
        if not ok:
            st.info("Fix the fields and press Continue → again.")
            st.stop()

        # persist and go to topic
        st.session_state.name = name.strip()
        st.session_state.regno = regno.strip()
        st.session_state.rollno = rollno.strip()
        goto_topic()

# ---------- TOPIC STEP ----------
elif st.session_state.step == "topic":
    # show existing submission info (if any)
    df_existing = load_sheet_df()
    reg_exists = False
    existing_topic = None
    if df_existing is not None and "Register Number" in df_existing.columns:
        matches = df_existing[df_existing["Register Number"] == st.session_state.regno]
        if not matches.empty:
            reg_exists = True
            existing_topic = matches.iloc[-1].get("Topic", None)

    if reg_exists:
        st.warning(f"A submission already exists for Register Number {st.session_state.regno}.")
        if existing_topic:
            st.write("Previously submitted Topic:")
            st.write(f"> {existing_topic}")
        edit_choice = st.radio("Do you want to edit the Topic for this Register Number?", ("No — keep as is", "Yes — edit topic"))
        if edit_choice == "No — keep as is":
            show_submission_count()
            st.success("No changes made.")
            st.stop()

    with st.form("topic_form", clear_on_submit=False):
        st.subheader("Enter Topic")
        topic = st.text_input("Topic", value=st.session_state.topic, help="Example: Basic Fabrication steps - Photolithography, Etching")
        topic_submit = st.form_submit_button("Check & Continue")
        back = st.form_submit_button("Back")

    if back:
        back_to_details()

    if topic_submit:
        if not topic.strip():
            st.error("Topic cannot be empty.")
            st.stop()

        # check similarity excluding same reg no
        topics_to_check = []
        df_check = load_sheet_df()
        if df_check is not None and "Topic" in df_check.columns:
            if "Register Number" in df_check.columns:
                df_check["Register Number"] = df_check["Register Number"].astype(str)
                topics_to_check = df_check[df_check["Register Number"] != st.session_state.regno]["Topic"].astype(str).tolist()
            else:
                topics_to_check = df_check["Topic"].astype(str).tolist()

        similar_list = []
        for t in topics_to_check:
            if (t.lower() == topic.lower() or topic.lower() in t.lower() or t.lower() in topic.lower() or is_similar(topic, t)):
                similar_list.append(t)

        if similar_list:
            st.warning("⚠️ Your Topic is similar to existing Topics:")
            for s in similar_list:
                st.write(" •", s)
            change_choice = st.radio("Do you want to change the Topic?", ("Yes — change topic", "No — keep this topic"))
            if change_choice == "Yes — change topic":
                st.info("Please edit the Topic above and press Check & Continue again.")
                st.stop()

        st.session_state.topic = topic.strip()
        goto_confirm()

# ---------- CONFIRM STEP ----------
elif st.session_state.step == "confirm":
    st.subheader("Final confirmation")
    st.write("**Name:**", st.session_state.name)
    st.write("**Register Number:**", st.session_state.regno)
    st.write("**Roll Number:**", st.session_state.rollno)
    st.write("**Topic:**", st.session_state.topic)

    save = st.button("Save to list ✅")
    edit_final = st.button("Edit fields ❌")
    back_btn = st.button("Back")

    if back_btn:
        st.session_state.step = "topic"
        st.rerun()

    if edit_final:
        st.session_state.step = "details"
        st.rerun()

    if save:
        timestamp = datetime.now().isoformat(sep=" ", timespec="seconds")
        data = {
            "Name": [st.session_state.name],
            "Register Number": [st.session_state.regno],
            "Roll Number": [st.session_state.rollno],
            "Topic": [st.session_state.topic],
            "Timestamp": [timestamp]
        }
        df_new = pd.DataFrame(data)

        # load existing and merge (remove existing RegNo if present)
        existing = load_sheet_df()
        if existing is not None:
            # normalize previous column name differences
            if "Topic Title" in existing.columns and "Topic" not in existing.columns:
                existing = existing.rename(columns={"Topic Title": "Topic"})
            if "Register Number" in existing.columns:
                existing["Register Number"] = existing["Register Number"].astype(str)
                if (existing["Register Number"] == st.session_state.regno).any():
                    existing = existing[existing["Register Number"] != st.session_state.regno]
            if "Timestamp" not in existing.columns:
                existing["Timestamp"] = pd.NA
            df_final = pd.concat([existing, df_new], ignore_index=True)
        else:
            df_final = df_new

        success = save_df_to_sheet(df_final)
        if success:
            st.success("✔️ Your response has been saved successfully!")
            st.info(f"📊 Total students submitted: {len(df_final)}")
            finish_and_reset()
        else:
            st.error("Failed to save. Please tell the admin.")

# ---------- DONE (post-save) ----------
elif st.session_state.step == "done":
    st.success("Thank you — submission complete.")
    if st.button("New submission"):
        finish_and_reset()

# sidebar status
show_submission_count()
