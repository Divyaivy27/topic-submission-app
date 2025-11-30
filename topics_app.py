# topics_app.py
import streamlit as st
import pandas as pd
import os
import re
import sys
from datetime import datetime
from difflib import SequenceMatcher
import shutil

# ---------- CONFIG ----------
DESKTOP_PATH = os.path.join(os.path.expanduser("~"), "Desktop")
FILE = os.path.join(DESKTOP_PATH, "topics.xlsx")   # saved on Desktop (hidden from users)
BACKUP_FOLDER = os.path.join(DESKTOP_PATH, "topic_backups")
SIMILARITY_THRESHOLD = 0.5
REG_PREFIX = "23130910831"
REG_MAX_LAST = 48
FORBIDDEN_ROLL_SUFFIX = {"08", "29", "13"}
# ----------------------------

st.set_page_config(page_title="Topic Submission", page_icon="📝", layout="centered")

st.title("Topic Submission Form")
st.caption("Fill your details and choose a topic. Use the form below. (Type `exit` in a field to stop — not needed in browser.)")

# -------------------------
# Helpers
# -------------------------
def is_similar(a: str, b: str, threshold=SIMILARITY_THRESHOLD) -> bool:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio() >= threshold

def ensure_backup_folder():
    os.makedirs(BACKUP_FOLDER, exist_ok=True)

def backup_file_if_exists():
    """Create a timestamped backup of FILE if it exists."""
    if os.path.exists(FILE):
        ensure_backup_folder()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"topics_backup_{ts}.xlsx"
        backup_path = os.path.join(BACKUP_FOLDER, backup_name)
        shutil.copy2(FILE, backup_path)

def load_existing_df():
    if os.path.exists(FILE):
        try:
            df = pd.read_excel(FILE)
            # normalize column names for safety: prefer "Topic"
            if "Topic Title" in df.columns and "Topic" not in df.columns:
                df = df.rename(columns={"Topic Title": "Topic"})
            # ensure register numbers are strings
            if "Register Number" in df.columns:
                df["Register Number"] = df["Register Number"].astype(str)
            return df
        except Exception:
            st.warning("Warning: Could not read the existing Excel file. Proceeding as if none exist.")
            return None
    return None

def save_df(df: pd.DataFrame):
    # sort by register number numerically if possible
    try:
        df["Register Number"] = df["Register Number"].astype(str)
        df = df.assign(_reg_sort = df["Register Number"].astype(int)).sort_values(by="_reg_sort")
        df = df.drop(columns=["_reg_sort"])
    except Exception:
        df = df.sort_values(by="Register Number")
    # backup before writing
    backup_file_if_exists()
    df.to_excel(FILE, index=False)

def validate_regno(r: str) -> tuple[bool, str]:
    if not re.fullmatch(r"\d{13}", r):
        return False, "Register number must be exactly 13 digits."
    if not r.startswith(REG_PREFIX):
        return False, f"Register must start with {REG_PREFIX}."
    try:
        last = int(r[-2:])
    except ValueError:
        return False, "Last two characters of Register number must be digits."
    if not (1 <= last <= REG_MAX_LAST):
        return False, f"Last two digits must be between 01 and {REG_MAX_LAST}."
    return True, ""

def validate_rollno(r: str) -> tuple[bool, str]:
    m = re.fullmatch(r"^23d12(\d{2})$", r, re.I)
    if not m:
        return False, "Roll format must start with 23d12 followed by two digits (e.g. 23d1201)."
    suffix = m.group(1)
    if suffix in FORBIDDEN_ROLL_SUFFIX:
        return False, f"Roll suffix {suffix} is reserved (TC students) — pick a different roll suffix."
    return True, ""

def show_submission_count():
    df = load_existing_df()
    total = len(df) if df is not None else 0
    st.info(f"📊 Total students submitted so far: {total}")

# -------------------------
# UI form
# -------------------------
# -------------------------
# UI flow with session state (details -> topic -> confirmation)
# -------------------------
# initialize session state
if "step" not in st.session_state:
    st.session_state.step = "details"   # possible values: 'details', 'topic', 'confirm', 'done'
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
    st.experimental_rerun()

def back_to_details():
    st.session_state.step = "details"
    st.experimental_rerun()

def goto_confirm():
    st.session_state.step = "confirm"
    st.experimental_rerun()

def finish_and_reset():
    # optional: clear fields after done
    st.session_state.step = "details"
    st.session_state.name = ""
    st.session_state.regno = ""
    st.session_state.rollno = ""
    st.session_state.topic = ""
    st.experimental_rerun()

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
            st.warning("Exiting by user request.")
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
            st.info("Fix the highlighted fields and press Continue → again.")
            st.stop()

        # store validated values in session_state and move to topic step
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
        edit_choice = st.radio("Do you want to edit the Topic for this Register Number?",
                               ("No — keep as is", "Yes — edit topic"))
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
        # go back to details step (values remain in session_state)
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

        # save topic to session and go to confirm
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
        st.experimental_rerun()

    if edit_final:
        # allow user to go back and edit details
        st.session_state.step = "details"
        st.experimental_rerun()

    if save:
        # prepare df_new
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

        # save to Google Sheets
        success = save_df_to_sheet(df_final)
        if success:
            st.success("✔️ Your response has been saved successfully!")
            st.info(f"📊 Total students submitted: {len(df_final)}")
            # optionally reset or allow another submission
            finish_and_reset()
        else:
            st.error("Failed to save. Please tell the admin.")

# ---------- DONE (post-save) ----------
elif st.session_state.step == "done":
    st.success("Thank you — submission complete.")
    st.write("If you want to submit again, use the form below.")
    # show current values cleared; allow a manual reset button
    if st.button("New submission"):
        finish_and_reset()

# sidebar status
show_submission_count()

# show submission count in the sidebar always
st.sidebar.header("Status")
try:
    df_now = load_existing_df()
    total_now = len(df_now) if df_now is not None else 0
    st.sidebar.write(f"Total submissions: {total_now}")
except Exception:
    st.sidebar.write("Total submissions: —")
