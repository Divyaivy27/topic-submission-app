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
with st.form("details_form", clear_on_submit=False):
    st.subheader("Enter your details")
    name = st.text_input("Name", help="Your full name")
    regno = st.text_input(f"Register Number (must start with {REG_PREFIX}, last two digits 01–{REG_MAX_LAST})",
                          help=f"Example: {REG_PREFIX}01")
    rollno = st.text_input("Roll Number (must start with 23d12; forbidden suffixes: 08,29,13)",
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

    # All basic validations passed. Load existing to check regno existence.
    df_existing = load_existing_df()
    reg_exists = False
    existing_topic = None
    if df_existing is not None and "Register Number" in df_existing.columns:
        matches = df_existing[df_existing["Register Number"] == regno.strip()]
        if not matches.empty:
            reg_exists = True
            existing_topic = matches.iloc[-1].get("Topic", None)

    if reg_exists:
        st.warning(f"A submission already exists for Register Number {regno.strip()}.")
        if existing_topic:
            st.write("Previously submitted Topic:")
            st.write(f"> {existing_topic}")
        edit_choice = st.radio("Do you want to edit the Topic for this Register Number?", ("No — keep as is", "Yes — edit topic"))
        if edit_choice == "No — keep as is":
            show_submission_count()
            st.success("No changes made.")
            st.stop()
        # else continue to topic entry with ability to overwrite

    # Topic entry & similarity check form
    with st.form("topic_form", clear_on_submit=False):
        st.subheader("Enter Topic")
        topic = st.text_input("Topic", help="Example: Basic Fabrication steps - Photolithography, Etching")
        topic_submit = st.form_submit_button("Check & Continue")

    if topic_submit:
        if not topic.strip():
            st.error("Topic cannot be empty.")
            st.stop()

        # Build topics to check excluding same RegNo
        topics_to_check = []
        df_check = load_existing_df()
        if df_check is not None and "Topic" in df_check.columns:
            if "Register Number" in df_check.columns:
                df_check["Register Number"] = df_check["Register Number"].astype(str)
                topics_to_check = df_check[df_check["Register Number"] != regno.strip()]["Topic"].astype(str).tolist()
            else:
                topics_to_check = df_check["Topic"].astype(str).tolist()

        similar_list = []
        for t in topics_to_check:
            if (t.lower() == topic.lower()
                or topic.lower() in t.lower()
                or t.lower() in topic.lower()
                or is_similar(topic, t)):
                similar_list.append(t)

        if similar_list:
            st.warning("⚠️ Your Topic is similar to existing Topics:")
            for s in similar_list:
                st.write(" •", s)
            change_choice = st.radio("Do you want to change the Topic?", ("Yes — change topic", "No — keep this topic"))
            if change_choice == "Yes — change topic":
                st.info("Please edit the Topic above and press Check & Continue again.")
                st.stop()
            # else proceed to final confirmation

        # Final confirmation (display details and save)
        st.write("---")
        st.subheader("Final confirmation")
        st.write("**Name:**", name)
        st.write("**Register Number:**", regno)
        st.write("**Roll Number:**", rollno)
        st.write("**Topic:**", topic)

        save = st.button("Save to list ✅")
        edit_final = st.button("Edit fields ❌")

        if edit_final:
            st.info("Please modify Name / Register Number / Roll Number / Topic above using the forms and press the appropriate Continue buttons.")
            st.stop()

        if save:
            timestamp = datetime.now().isoformat(sep=" ", timespec="seconds")
            data = {
                "Name": [name.strip()],
                "Register Number": [regno.strip()],
                "Roll Number": [rollno.strip()],
                "Topic": [topic.strip()],
                "Timestamp": [timestamp]
            }
            df_new = pd.DataFrame(data)

            if os.path.exists(FILE):
                try:
                    df_existing = pd.read_excel(FILE)
                except Exception:
                    st.warning("Could not read existing file; creating a new one.")
                    df_existing = pd.DataFrame(columns=df_new.columns)

                # normalize previous column name differences
                if "Topic Title" in df_existing.columns and "Topic" not in df_existing.columns:
                    df_existing = df_existing.rename(columns={"Topic Title": "Topic"})

                if "Register Number" in df_existing.columns:
                    df_existing["Register Number"] = df_existing["Register Number"].astype(str)

                # remove previous entries for this RegNo
                if "Register Number" in df_existing.columns and (df_existing["Register Number"] == regno.strip()).any():
                    df_existing = df_existing[df_existing["Register Number"] != regno.strip()]

                if "Timestamp" not in df_existing.columns:
                    df_existing["Timestamp"] = pd.NA

                df_final = pd.concat([df_existing, df_new], ignore_index=True)
            else:
                df_final = df_new

            # Save (with backup)
            try:
                save_df(df_final)
                st.success("✔️ Your response has been saved successfully!")
                total = len(df_final)
                st.info(f"📊 Total students submitted so far: {total}")
            except Exception as e:
                st.error("Error saving data. Tell the admin. (" + str(e) + ")")

# show submission count in the sidebar always
st.sidebar.header("Status")
try:
    df_now = load_existing_df()
    total_now = len(df_now) if df_now is not None else 0
    st.sidebar.write(f"Total submissions: {total_now}")
except Exception:
    st.sidebar.write("Total submissions: —")
