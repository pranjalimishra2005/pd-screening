import os
import re
import io
import streamlit as st
import requests
import pandas as pd

BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

# ── Page config ───────────────────────────────────────────
st.set_page_config(
    page_title="NeuroScreen — PD Screening",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Session state init ────────────────────────────────────
DEFAULTS = [
    ("token", None),
    ("username", None),
    ("page", "auth"),
    ("auth_view", "signup"),
    ("scores", {"speech": None, "hw": None, "eeg": None}),
    ("patient_name", ""),
    ("patient_id", None),
    ("screening_mode", None),          # "single" or "cross"
    ("selected_modalities", []),       # ["speech", "handwriting", "eeg"]
    ("last_result", None),
    ("history_cache", None),
    ("history_exists", False),
]

for key, default in DEFAULTS:
    if key not in st.session_state:
        st.session_state[key] = default


# ── Helpers ───────────────────────────────────────────────
def auth_header():
    return {"Authorization": f"Bearer {st.session_state.token}"}


def go(page):
    st.session_state.page = page
    st.rerun()


def is_valid_email(email: str) -> bool:
    email = (email or "").strip()
    pattern = r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"
    return re.match(pattern, email) is not None


def password_error(password: str, check_min: bool = True):
    if password is None:
        return "Password is required."
    size = len(password.encode("utf-8"))
    if check_min and size < 8:
        return "Password must be at least 8 characters long."
    if size > 72:
        return "Password cannot be longer than 72 characters."
    return None


def safe_error_response(res, fallback):
    try:
        detail = res.json().get("detail", fallback)
        if isinstance(detail, str):
            return detail
        return fallback
    except Exception:
        return fallback


def login_success(data):
    st.session_state.token = data["token"]
    st.session_state.username = data.get("username", "User")
    st.session_state.page = "patient_start"
    st.session_state.auth_view = "signup"
    st.session_state.history_cache = None
    refresh_history_exists()
    st.rerun()


def refresh_history_exists():
    if not st.session_state.token:
        st.session_state.history_exists = False
        return

    try:
        res = requests.get(
            f"{BASE_URL}/history/all/mine",
            headers=auth_header(),
            timeout=10
        )
        if res.status_code == 200:
            records = res.json()
            st.session_state.history_cache = records
            st.session_state.history_exists = bool(records)
        else:
            st.session_state.history_exists = False
    except Exception:
        st.session_state.history_exists = False


def reset_patient_session(clear_last_result=True):
    st.session_state.patient_name = ""
    st.session_state.patient_id = None
    st.session_state.screening_mode = None
    st.session_state.selected_modalities = []
    st.session_state.scores = {"speech": None, "hw": None, "eeg": None}
    if clear_last_result:
        st.session_state.last_result = None


def modality_label(key):
    return {
        "speech": "Speech",
        "handwriting": "Handwriting",
        "eeg": "EEG",
    }.get(key, key)


def modality_icon(key):
    return {
        "speech": "🎙️",
        "handwriting": "✍️",
        "eeg": "🧠",
    }.get(key, "•")


def score_key_for_modality(modality):
    return {"speech": "speech", "handwriting": "hw", "eeg": "eeg"}[modality]


def next_uncompleted_modality():
    for modality in st.session_state.selected_modalities:
        skey = score_key_for_modality(modality)
        if st.session_state.scores.get(skey) is None:
            return modality
    return None


def completed_selected_count():
    count = 0
    for modality in st.session_state.selected_modalities:
        skey = score_key_for_modality(modality)
        if st.session_state.scores.get(skey) is not None:
            count += 1
    return count


def selected_tests_complete():
    selected = st.session_state.selected_modalities
    if not selected:
        return False
    return completed_selected_count() == len(selected)


def route_after_test_success():
    nxt = next_uncompleted_modality()
    if nxt:
        if st.button(
            f"Continue to {modality_icon(nxt)} {modality_label(nxt)} →",
            type="primary",
            use_container_width=True,
            key=f"continue_to_{nxt}"
        ):
            go(nxt)
    else:
        if st.button(
            ("View final result →" if st.session_state.screening_mode == "single" else "View fused assessment →"),
            type="primary",
            use_container_width=True,
            key="continue_to_fuse"
        ):
            go("fuse")


def render_saved_score_continue(current_modality):
    """Shows the next action after a modality score has already been saved."""
    skey = score_key_for_modality(current_modality)
    if st.session_state.scores.get(skey) is None:
        return

    pending = next_uncompleted_modality()
    if pending:
        if pending != current_modality:
            st.markdown("<div style='height:0.75rem'></div>", unsafe_allow_html=True)
            if st.button(
                f"Continue to {modality_icon(pending)} {modality_label(pending)} →",
                type="primary",
                use_container_width=True,
                key=f"saved_continue_to_{pending}"
            ):
                go(pending)
    else:
        st.markdown("<div style='height:0.75rem'></div>", unsafe_allow_html=True)
        label = "View final result →" if st.session_state.screening_mode == "single" else "View fused assessment →"
        if st.button(
            label,
            type="primary",
            use_container_width=True,
            key=f"saved_continue_to_fuse_from_{current_modality}"
        ):
            go("fuse")


# ── Global CSS ────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600;700&family=DM+Mono:wght@400;500&display=swap');

*, *::before, *::after { box-sizing: border-box; }

html, body, [data-testid="stApp"] {
    font-family: 'DM Sans', sans-serif;
    background: #F4F7FB;
    color: #1A2340;
}

#MainMenu, footer, header { visibility: hidden; }
[data-testid="stToolbar"] { display: none; }
.block-container { padding-top: 1.5rem !important; padding-bottom: 2rem !important; }

[data-testid="stSidebar"] {
    background: #0B1E3D !important;
    border-right: 1px solid #1E3A6E;
}
[data-testid="stSidebar"] * { color: #CBD5E8 !important; }
[data-testid="stSidebarContent"] { padding: 0 !important; }

.ns-card {
    background: #FFFFFF;
    border-radius: 16px;
    border: 1px solid #E2E8F4;
    padding: 1.75rem;
    box-shadow: 0 2px 12px rgba(11,30,61,0.06);
    margin-bottom: 1rem;
    transition: box-shadow 0.2s;
}
.ns-card:hover { box-shadow: 0 4px 24px rgba(11,30,61,0.1); }

.stat-card {
    background: #FFFFFF;
    border-radius: 14px;
    border: 1px solid #E2E8F4;
    padding: 1.25rem 1.5rem;
    text-align: center;
    box-shadow: 0 2px 8px rgba(11,30,61,0.05);
}
.stat-num {
    font-size: 2rem;
    font-weight: 700;
    color: #1151A6;
    line-height: 1;
    margin-bottom: 0.25rem;
}
.stat-label {
    font-size: 0.78rem;
    font-weight: 500;
    color: #6B7A99;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}

.modality-card {
    background: #FFFFFF;
    border-radius: 18px;
    border: 2px solid #E2E8F4;
    padding: 2rem 1.5rem;
    text-align: center;
    cursor: pointer;
    transition: all 0.2s ease;
    position: relative;
    overflow: hidden;
}
.modality-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 4px;
    background: linear-gradient(90deg, #1151A6, #3B82F6);
    opacity: 0;
    transition: opacity 0.2s;
}
.modality-card:hover {
    border-color: #1151A6;
    transform: translateY(-2px);
    box-shadow: 0 8px 24px rgba(17,81,166,0.12);
}
.modality-card:hover::before { opacity: 1; }
.modality-icon { font-size: 2.5rem; margin-bottom: 0.75rem; }
.modality-title { font-size: 1.05rem; font-weight: 600; color: #1A2340; margin-bottom: 0.4rem; }
.modality-desc { font-size: 0.82rem; color: #6B7A99; line-height: 1.5; }
.modality-badge {
    display: inline-block;
    margin-top: 0.75rem;
    padding: 0.2rem 0.65rem;
    border-radius: 20px;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.04em;
}
.badge-done { background: #D1FAE5; color: #065F46; }
.badge-pending { background: #FEF3C7; color: #92400E; }

.choice-card {
    background: #FFFFFF;
    border-radius: 22px;
    border: 2px solid #D8E4F8;
    padding: 2rem;
    min-height: 190px;
    text-align: center;
    box-shadow: 0 8px 30px rgba(11,30,61,0.06);
}
.choice-icon { font-size: 2.4rem; margin-bottom: 0.7rem; }
.choice-title { font-size: 1.25rem; font-weight: 700; color: #1A2340; margin-bottom: 0.45rem; }
.choice-desc { font-size: 0.9rem; color: #6B7A99; line-height: 1.5; }

.risk-high { background: #FEE2E2; color: #991B1B; border: 1px solid #FECACA; border-radius: 8px; padding: 0.75rem 1rem; font-weight: 600; }
.risk-moderate { background: #FEF3C7; color: #92400E; border: 1px solid #FDE68A; border-radius: 8px; padding: 0.75rem 1rem; font-weight: 600; }
.risk-low { background: #D1FAE5; color: #065F46; border: 1px solid #A7F3D0; border-radius: 8px; padding: 0.75rem 1rem; font-weight: 600; }

.score-pill {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    background: #EFF6FF;
    border: 1px solid #BFDBFE;
    border-radius: 999px;
    padding: 0.35rem 0.9rem;
    font-size: 0.82rem;
    font-weight: 500;
    color: #1D4ED8;
    font-family: 'DM Mono', monospace;
}

.page-header {
    display: flex;
    align-items: center;
    gap: 1rem;
    margin-bottom: 1.75rem;
    padding-bottom: 1rem;
    border-bottom: 1px solid #E2E8F4;
}
.page-header-icon {
    width: 44px; height: 44px;
    background: #EFF6FF;
    border-radius: 12px;
    display: flex; align-items: center; justify-content: center;
    font-size: 1.4rem;
    border: 1px solid #BFDBFE;
}
.page-header h1 {
    font-size: 1.5rem !important;
    font-weight: 700 !important;
    color: #1A2340 !important;
    margin: 0 !important;
    padding: 0 !important;
}
.page-header p {
    font-size: 0.85rem;
    color: #6B7A99;
    margin: 0.15rem 0 0 0;
}

.topbar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: #FFFFFF;
    border-radius: 14px;
    border: 1px solid #E2E8F4;
    padding: 0.75rem 1.5rem;
    margin-bottom: 1.5rem;
    box-shadow: 0 1px 6px rgba(11,30,61,0.05);
}
.topbar-left { display: flex; align-items: center; gap: 0.75rem; }
.topbar-breadcrumb { font-size: 0.8rem; color: #6B7A99; }
.topbar-page { font-size: 0.95rem; font-weight: 600; color: #1A2340; }
.topbar-right { display:flex; align-items:center; gap:0.75rem; }
.user-chip {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    background: #F1F5FD;
    border: 1px solid #DBEAFE;
    border-radius: 999px;
    padding: 0.35rem 0.9rem 0.35rem 0.35rem;
}
.user-avatar {
    width: 30px; height: 30px;
    background: linear-gradient(135deg, #1151A6, #3B82F6);
    border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 0.75rem;
    font-weight: 700;
    color: white;
}
.user-name { font-size: 0.82rem; font-weight: 600; color: #1A2340; }

.progress-tracker {
    display: flex;
    align-items: center;
    background: #FFFFFF;
    border-radius: 14px;
    border: 1px solid #E2E8F4;
    padding: 1rem 1.5rem;
    margin-bottom: 1.5rem;
    gap: 0;
}
.pt-step { display: flex; align-items: center; flex: 1; }
.pt-dot {
    width: 32px; height: 32px;
    border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 0.75rem;
    font-weight: 700;
    flex-shrink: 0;
}
.pt-dot-done { background: #D1FAE5; color: #065F46; border: 2px solid #6EE7B7; }
.pt-dot-active { background: #1151A6; color: white; border: 2px solid #1151A6; box-shadow: 0 0 0 4px rgba(17,81,166,0.15); }
.pt-dot-pending { background: #F1F5FD; color: #9CA3AF; border: 2px solid #E2E8F4; }
.pt-label { font-size: 0.75rem; font-weight: 500; margin-left: 0.5rem; }
.pt-label-done { color: #065F46; }
.pt-label-active { color: #1151A6; font-weight: 600; }
.pt-label-pending { color: #9CA3AF; }
.pt-line { flex: 1; height: 2px; background: #E2E8F4; margin: 0 0.5rem; }
.pt-line-done { background: #6EE7B7; }

.sb-logo {
    padding: 1.5rem 1.25rem 1rem;
    border-bottom: 1px solid #1E3A6E;
    margin-bottom: 0.5rem;
}
.sb-logo-text {
    font-size: 1.2rem;
    font-weight: 700;
    color: #FFFFFF !important;
    letter-spacing: -0.02em;
}
.sb-logo-sub {
    font-size: 0.7rem;
    color: #64748B !important;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin-top: 0.1rem;
}
.sb-section-label {
    font-size: 0.65rem !important;
    font-weight: 600 !important;
    color: #4A5568 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.1em !important;
    padding: 0.75rem 1.25rem 0.25rem !important;
}
.sb-patient-card {
    margin: 0.75rem 1rem;
    background: #132847;
    border-radius: 12px;
    border: 1px solid #1E3A6E;
    padding: 1rem;
}
.sb-patient-name {
    font-size: 0.9rem !important;
    font-weight: 600 !important;
    color: #E2E8F0 !important;
    margin-bottom: 0.75rem;
}
.sb-score-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.35rem 0;
    border-bottom: 1px solid #1E3A6E;
}
.sb-score-label { font-size: 0.75rem !important; color: #94A3B8 !important; }
.sb-score-val { font-size: 0.78rem !important; font-weight: 600 !important; font-family: 'DM Mono', monospace !important; }
.sb-score-done { color: #34D399 !important; }
.sb-score-pending { color: #4B5563 !important; }

.stTextInput > div > div > input,
.stNumberInput > div > div > input {
    border-radius: 10px !important;
    border: 1.5px solid #E2E8F4 !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.9rem !important;
    padding: 0.5rem 0.75rem !important;
    transition: border-color 0.15s !important;
}
.stTextInput > div > div > input:focus,
.stNumberInput > div > div > input:focus {
    border-color: #1151A6 !important;
    box-shadow: 0 0 0 3px rgba(17,81,166,0.1) !important;
}

.stButton > button {
    border-radius: 10px !important;
    font-family: 'DM Sans', sans-serif !important;
    font-weight: 600 !important;
    font-size: 0.88rem !important;
    padding: 0.55rem 1.25rem !important;
    transition: all 0.15s ease !important;
    border: 1.5px solid transparent !important;
}
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #1151A6, #2563EB) !important;
    color: white !important;
    box-shadow: 0 2px 8px rgba(17,81,166,0.3) !important;
}
.stButton > button[kind="primary"]:hover {
    box-shadow: 0 4px 16px rgba(17,81,166,0.4) !important;
    transform: translateY(-1px) !important;
}
.stButton > button[kind="secondary"] {
    background: white !important;
    color: #1151A6 !important;
    border-color: #BFDBFE !important;
}

[data-testid="stFileUploader"] {
    border-radius: 14px !important;
    border: 2px dashed #BFDBFE !important;
    background: #F8FAFF !important;
    padding: 1rem !important;
}

.streamlit-expanderHeader {
    background: #F8FAFF !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
    font-size: 0.9rem !important;
    color: #1A2340 !important;
}

.stTabs [data-baseweb="tab-list"] {
    gap: 0.5rem;
    background: #F1F5FD;
    border-radius: 10px;
    padding: 0.25rem;
    border: none;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 8px !important;
    font-family: 'DM Sans', sans-serif !important;
    font-weight: 500 !important;
    font-size: 0.88rem !important;
    color: #6B7A99 !important;
    padding: 0.45rem 1rem !important;
}
.stTabs [aria-selected="true"] {
    background: white !important;
    color: #1151A6 !important;
    font-weight: 600 !important;
    box-shadow: 0 1px 4px rgba(11,30,61,0.1) !important;
}

hr { border-color: #E2E8F4 !important; margin: 1.25rem 0 !important; }

.login-wrap { max-width: 500px; margin: 2rem auto; }
.login-header { text-align: center; margin-bottom: 2rem; }
.login-logo { font-size: 3rem; margin-bottom: 0.5rem; }
.login-title { font-size: 1.75rem; font-weight: 700; color: #1A2340; margin: 0; }
.login-sub { font-size: 0.9rem; color: #6B7A99; margin-top: 0.35rem; }
.auth-switch {
    text-align:center;
    margin-top:1.3rem;
    padding-top:1rem;
    border-top:1px solid #E2E8F4;
    color:#6B7A99;
    font-size:0.9rem;
}

.result-wrap { text-align: center; padding: 1.5rem; }
.result-score-big {
    font-size: 3.5rem;
    font-weight: 700;
    font-family: 'DM Mono', monospace;
    line-height: 1;
    margin-bottom: 0.5rem;
}
.result-score-high { color: #DC2626; }
.result-score-moderate { color: #D97706; }
.result-score-low { color: #059669; }

.info-box {
    background: #EFF6FF;
    border: 1px solid #BFDBFE;
    border-left: 4px solid #1151A6;
    border-radius: 10px;
    padding: 0.85rem 1rem;
    font-size: 0.85rem;
    color: #1E40AF;
    margin-bottom: 1rem;
}

[data-testid="stAlert"] { border-radius: 10px !important; }
</style>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════
def render_sidebar():
    with st.sidebar:
        st.markdown("""
        <div class="sb-logo">
            <div class="sb-logo-text">🧠 NeuroScreen</div>
            <div class="sb-logo-sub">Parkinson's Screening</div>
        </div>
        """, unsafe_allow_html=True)

        if st.session_state.token is None:
            st.markdown('<div class="sb-section-label">Welcome</div>', unsafe_allow_html=True)
            st.markdown("Create an account or sign in to continue.")
            return

        uname = st.session_state.username or "User"
        initials = uname[:2].upper()
        st.markdown(f"""
        <div style="padding: 0.5rem 1rem 0.75rem; display:flex; align-items:center; gap:0.75rem; border-bottom:1px solid #1E3A6E; margin-bottom:0.5rem;">
            <div style="width:36px;height:36px;background:linear-gradient(135deg,#1151A6,#3B82F6);border-radius:50%;
                        display:flex;align-items:center;justify-content:center;font-size:0.8rem;font-weight:700;color:white;flex-shrink:0;">
                {initials}
            </div>
            <div>
                <div style="font-size:0.88rem;font-weight:600;color:#E2E8F0;">{uname}</div>
                <div style="font-size:0.72rem;color:#64748B;">Signed in</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown('<div class="sb-section-label">Main Menu</div>', unsafe_allow_html=True)

        if st.button("🏁  New Screening", key="nav_new_screening", use_container_width=True):
            reset_patient_session(clear_last_result=True)
            go("patient_start")

        nav_items = [
            ("👤", "Patient", "patient_start"),
            ("🧪", "Screening Type", "mode_select"),
            ("✅", "Selected Tests", "modality_select"),
        ]

        for icon, label, page in nav_items:
            if st.button(f"{icon}  {label}", key=f"nav_{page}", use_container_width=True):
                go(page)

        if st.session_state.selected_modalities:
            st.markdown('<div class="sb-section-label">Tests</div>', unsafe_allow_html=True)
            for modality in st.session_state.selected_modalities:
                if st.button(f"{modality_icon(modality)}  {modality_label(modality)}", key=f"nav_test_{modality}", use_container_width=True):
                    go(modality)

        done = completed_selected_count()
        total = len(st.session_state.selected_modalities)
        if total > 0:
            if st.button("⚡  Fused Assessment", key="nav_fuse", use_container_width=True):
                go("fuse")

        if st.session_state.history_exists:
            if st.button("📋  Patient History", key="nav_history", use_container_width=True):
                go("history")

        st.markdown('<div class="sb-section-label" style="margin-top:0.5rem;">Current Session</div>', unsafe_allow_html=True)
        scores = st.session_state.scores
        pname = st.session_state.patient_name or "No patient selected"

        def score_html(key, label, icon):
            v = scores.get(key)
            if v is not None:
                return f"""
                <div class="sb-score-row">
                    <span class="sb-score-label">{icon} {label}</span>
                    <span class="sb-score-val sb-score-done">{v:.3f} ✓</span>
                </div>"""
            return f"""
                <div class="sb-score-row">
                    <span class="sb-score-label">{icon} {label}</span>
                    <span class="sb-score-val sb-score-pending">—</span>
                </div>"""

        mode_label = {
            "single": "Singular model",
            "cross": "Cross-modal"
        }.get(st.session_state.screening_mode, "Not selected")

        st.markdown(f"""
        <div class="sb-patient-card">
            <div class="sb-patient-name">👤 {pname}</div>
            <div style="font-size:0.76rem;color:#94A3B8;margin-bottom:0.65rem;">{mode_label}</div>
            {score_html("speech", "Speech", "🎙️")}
            {score_html("hw", "Handwriting", "✍️")}
            {score_html("eeg", "EEG", "🧠")}
        </div>
        """, unsafe_allow_html=True)

        if total > 0:
            st.markdown(f"""
            <div style="margin:0 1rem 0.5rem;padding:0.65rem 0.9rem;background:#132847;border-radius:10px;
                        border:1px solid #1E3A6E;display:flex;justify-content:space-between;align-items:center;">
                <span style="font-size:0.78rem;color:#94A3B8;">Selected tests complete</span>
                <span style="font-size:0.85rem;font-weight:700;color:#34D399;">{done}/{total}</span>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("---")
        if st.button("🚪  Logout", use_container_width=True, key="nav_logout"):
            for k, default in DEFAULTS:
                st.session_state[k] = default
            st.rerun()


# ═══════════════════════════════════════════════════════════
# TOPBAR
# ═══════════════════════════════════════════════════════════
PAGE_META = {
    "patient_start":   ("Patient Details", "Start a new screening"),
    "mode_select":     ("Screening Type", "Choose singular or cross-modal screening"),
    "modality_select": ("Select Modalities", "Choose the available test data"),
    "speech":          ("Speech Analysis", "Voice biomarker screening"),
    "handwriting":     ("Handwriting Analysis", "Motor control screening"),
    "eeg":             ("EEG Analysis", "Brainwave pattern screening"),
    "fuse":            ("Final Assessment", "Risk evaluation"),
    "history":         ("Patient History", "Past screening records"),
}


def render_topbar():
    page = st.session_state.page
    title, sub = PAGE_META.get(page, ("NeuroScreen", ""))
    uname = st.session_state.username or ""
    initials = uname[:2].upper()

    left_html = f"""
    <div class="topbar-left">
        <span class="topbar-breadcrumb">NeuroScreen /</span>
        <span class="topbar-page">{title}</span>
    </div>
    """
    right_html = f"""
    <div class="topbar-right">
        <div class="user-chip">
            <div class="user-avatar">{initials}</div>
            <span class="user-name">{uname}</span>
        </div>
    </div>
    """

    col1, col2 = st.columns([5, 2])
    with col1:
        st.markdown(f'<div class="topbar">{left_html}<div></div></div>', unsafe_allow_html=True)
    with col2:
        hcol, ucol = st.columns([1, 1.25])
        with hcol:
            if st.session_state.history_exists:
                if st.button("📋 History", key=f"top_history_{page}", use_container_width=True):
                    go("history")
        with ucol:
            st.markdown(f"""
            <div style="display:flex;justify-content:flex-end;margin-top:0.1rem;">
                <div class="user-chip" title="Signed-in account">
                    <div class="user-avatar">{initials}</div>
                    <span class="user-name">Account: {uname}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════
# PROGRESS TRACKER
# ═══════════════════════════════════════════════════════════
def render_progress():
    selected = st.session_state.selected_modalities
    if not selected:
        return

    steps = []
    for modality in selected:
        steps.append((score_key_for_modality(modality), modality_label(modality), modality_icon(modality), modality))
    steps.append(("fuse", "Fused Result", "⚡", "fuse"))

    page = st.session_state.page
    active_idx = -1
    for i, (_, _, _, page_key) in enumerate(steps):
        if page == page_key:
            active_idx = i

    parts = []
    for i, (skey, label, icon, page_key) in enumerate(steps):
        is_done = (skey != "fuse" and st.session_state.scores.get(skey) is not None) or (
            skey == "fuse" and st.session_state.last_result is not None
        )
        is_active = i == active_idx

        if is_done:
            dot_cls = "pt-dot-done"; lbl_cls = "pt-label-done"; dot_content = "✓"
        elif is_active:
            dot_cls = "pt-dot-active"; lbl_cls = "pt-label-active"; dot_content = str(i + 1)
        else:
            dot_cls = "pt-dot-pending"; lbl_cls = "pt-label-pending"; dot_content = str(i + 1)

        parts.append(f"""
        <div class="pt-step">
            <div class="pt-dot {dot_cls}">{dot_content}</div>
            <span class="pt-label {lbl_cls}">{icon} {label}</span>
        </div>""")

        if i < len(steps) - 1:
            line_cls = "pt-line-done" if is_done else "pt-line"
            parts.append(f'<div class="pt-line {line_cls}"></div>')

    st.markdown(f'<div class="progress-tracker">{"".join(parts)}</div>', unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════
# RISK DISPLAY helper
# ═══════════════════════════════════════════════════════════
def render_risk_result(p_pd, risk, label="PD Probability"):
    score_cls = {
        "High Risk": "result-score-high",
        "Moderate Risk": "result-score-moderate",
        "Low Risk": "result-score-low",
    }.get(risk, "result-score-low")

    risk_cls = {
        "High Risk": "risk-high",
        "Moderate Risk": "risk-moderate",
        "Low Risk": "risk-low",
    }.get(risk, "risk-low")

    icon = {"High Risk": "⚠️", "Moderate Risk": "⚡", "Low Risk": "✅"}.get(risk, "")

    st.markdown(f"""
    <div class="ns-card" style="text-align:center;padding:2rem;">
        <div style="font-size:0.8rem;font-weight:500;color:#6B7A99;text-transform:uppercase;
                    letter-spacing:0.08em;margin-bottom:0.5rem;">{label}</div>
        <div class="result-score-big {score_cls}">{p_pd:.1%}</div>
        <div class="{risk_cls}" style="margin-top:1rem;display:inline-block;">
            {icon} {risk}
        </div>
    </div>
    """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════
# AUTH PAGE
# ═══════════════════════════════════════════════════════════
def show_auth():
    col_l, col_c, col_r = st.columns([1, 1.25, 1])
    with col_c:
        st.markdown("""
        <div class="login-header">
            <div class="login-logo">🧠</div>
            <h1 class="login-title">NeuroScreen</h1>
            <p class="login-sub">Parkinson's Disease Cross-Modal Screening</p>
        </div>
        """, unsafe_allow_html=True)

        if st.session_state.auth_view == "signup":
            st.markdown("### Create Account")
            username = st.text_input("Full name", placeholder="Enter your full name", key="reg_user")
            email = st.text_input("Email address", placeholder="you@example.com", key="reg_email")
            password = st.text_input("Password", type="password", placeholder="Minimum 8 characters", key="reg_pass")

            if st.button("Create Account →", use_container_width=True, type="primary", key="reg_btn"):
                username = username.strip()
                email = email.strip().lower()

                if not username or not email or not password:
                    st.error("Please fill in all fields.")
                elif not is_valid_email(email):
                    st.error("Invalid email or password.")
                elif password_error(password, check_min=True):
                    st.error(password_error(password, check_min=True))
                else:
                    with st.spinner("Creating account…"):
                        try:
                            res = requests.post(
                                f"{BASE_URL}/auth/register",
                                json={"username": username, "email": email, "password": password},
                                timeout=20
                            )

                            if res.status_code == 200:
                                login_res = requests.post(
                                    f"{BASE_URL}/auth/login",
                                    json={"email": email, "password": password},
                                    timeout=20
                                )
                                if login_res.status_code == 200:
                                    login_success(login_res.json())
                                else:
                                    st.success("Account created. Please sign in.")
                                    st.session_state.auth_view = "login"
                                    st.rerun()

                            elif res.status_code == 409:
                                st.error("An account with this email already exists. Please sign in instead.")
                            else:
                                detail = safe_error_response(res, f"Registration failed ({res.status_code})")
                                if "password cannot be longer" in detail.lower():
                                    st.error("Password cannot be longer than 72 characters.")
                                elif "already" in detail.lower() or "duplicate" in detail.lower():
                                    st.error("An account with this email already exists. Please sign in instead.")
                                else:
                                    st.error(detail)

                        except requests.exceptions.ConnectionError:
                            st.error("Could not connect to the backend. Please make sure the backend is running.")
                        except requests.exceptions.Timeout:
                            st.error("The backend took too long to respond. Please try again.")
                        except Exception as e:
                            st.error(f"Something went wrong: {e}")

            st.markdown('<div class="auth-switch">Already have an account?</div>', unsafe_allow_html=True)
            if st.button("Sign In", use_container_width=True, key="switch_to_login"):
                st.session_state.auth_view = "login"
                st.rerun()

        else:
            st.markdown("### Sign In")
            email = st.text_input("Email address", placeholder="you@example.com", key="li_email")
            password = st.text_input("Password", type="password", placeholder="Enter your password", key="li_pass")

            if st.button("Sign In →", use_container_width=True, type="primary", key="li_btn"):
                email = email.strip().lower()

                if not email or not password:
                    st.error("Invalid email or password.")
                elif not is_valid_email(email):
                    st.error("Invalid email or password.")
                elif password_error(password, check_min=False):
                    st.error("Invalid email or password.")
                else:
                    with st.spinner("Signing in…"):
                        try:
                            res = requests.post(
                                f"{BASE_URL}/auth/login",
                                json={"email": email, "password": password},
                                timeout=20
                            )

                            if res.status_code == 200:
                                login_success(res.json())
                            else:
                                st.error("Invalid email or password.")

                        except requests.exceptions.ConnectionError:
                            st.error("Could not connect to the backend. Please make sure the backend is running.")
                        except requests.exceptions.Timeout:
                            st.error("The backend took too long to respond. Please try again.")
                        except Exception as e:
                            st.error(f"Something went wrong: {e}")

            st.markdown('<div class="auth-switch">Do not have an account?</div>', unsafe_allow_html=True)
            if st.button("Create Account", use_container_width=True, key="switch_to_signup"):
                st.session_state.auth_view = "signup"
                st.rerun()

        st.markdown("""
        <div style="text-align:center;margin-top:2rem;font-size:0.78rem;color:#9CA3AF;">
            NeuroScreen v1.0 · For screening assistance only
        </div>
        """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════
# PATIENT START
# ═══════════════════════════════════════════════════════════
def show_patient_start():
    render_topbar()

    col_l, col_c, col_r = st.columns([1, 1.3, 1])
    with col_c:
        st.markdown("""
        <div class="ns-card" style="text-align:center;padding:2.5rem;">
            <div style="font-size:2.8rem;margin-bottom:0.5rem;">👤</div>
            <h2 style="margin-bottom:0.3rem;">Enter Patient Name</h2>
            <p style="color:#6B7A99;margin-bottom:1.5rem;">
                This name will be used to save the screening result in your account history.
            </p>
        </div>
        """, unsafe_allow_html=True)

        pname = st.text_input(
            "Patient Name",
            value=st.session_state.patient_name,
            placeholder="Enter patient name",
            key="patient_name_input"
        )

        if st.button("Continue →", type="primary", use_container_width=True, key="patient_continue"):
            pname = pname.strip()
            if not pname:
                st.error("Please enter the patient name.")
            else:
                st.session_state.patient_name = pname
                st.session_state.scores = {"speech": None, "hw": None, "eeg": None}
                st.session_state.selected_modalities = []
                st.session_state.screening_mode = None
                st.session_state.last_result = None
                go("mode_select")


# ═══════════════════════════════════════════════════════════
# MODE SELECTION
# ═══════════════════════════════════════════════════════════
def show_mode_select():
    render_topbar()

    st.markdown("""
    <div class="page-header">
        <div class="page-header-icon">🧪</div>
        <div>
            <h1>Choose Screening Type</h1>
            <p>Select based on the test data available for the patient</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("""
        <div class="choice-card">
            <div class="choice-icon">🔹</div>
            <div class="choice-title">Singular Model</div>
            <div class="choice-desc">
                Choose this when you have test data for only one modality.
            </div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Select Singular Model →", use_container_width=True, type="primary", key="choose_single"):
            st.session_state.screening_mode = "single"
            st.session_state.selected_modalities = []
            st.session_state.scores = {"speech": None, "hw": None, "eeg": None}
            go("modality_select")

    with c2:
        st.markdown("""
        <div class="choice-card">
            <div class="choice-icon">🔀</div>
            <div class="choice-title">Cross Modalities</div>
            <div class="choice-desc">
                Choose this when you have test data for more than one modality.
            </div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Select Cross Modalities →", use_container_width=True, type="primary", key="choose_cross"):
            st.session_state.screening_mode = "cross"
            st.session_state.selected_modalities = []
            st.session_state.scores = {"speech": None, "hw": None, "eeg": None}
            go("modality_select")

    st.markdown("---")
    if st.button("← Back to Patient Name", key="mode_back"):
        go("patient_start")


# ═══════════════════════════════════════════════════════════
# MODALITY SELECTION
# ═══════════════════════════════════════════════════════════
def show_modality_select():
    render_topbar()

    mode = st.session_state.screening_mode
    if mode not in ["single", "cross"]:
        st.warning("Please choose a screening type first.")
        if st.button("Go to Screening Type"):
            go("mode_select")
        return

    st.markdown("""
    <div class="page-header">
        <div class="page-header-icon">✅</div>
        <div>
            <h1>Select Available Test Data</h1>
            <p>Only the selected modalities will be shown for testing</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

    modalities = [
        ("speech", "🎙️", "Speech Analysis", "CSV voice features"),
        ("handwriting", "✍️", "Handwriting Analysis", "Spiral/wave image"),
        ("eeg", "🧠", "EEG Analysis", "BIDS ZIP with .set file"),
    ]

    if mode == "single":
        selected = st.radio(
            "Select one modality",
            options=["speech", "handwriting", "eeg"],
            format_func=lambda x: f"{modality_icon(x)} {modality_label(x)}",
            horizontal=True,
            key="single_modality_radio"
        )

        c1, c2, c3 = st.columns(3)
        for col, (key, icon, title, desc) in zip([c1, c2, c3], modalities):
            with col:
                st.markdown(f"""
                <div class="modality-card">
                    <div class="modality-icon">{icon}</div>
                    <div class="modality-title">{title}</div>
                    <div class="modality-desc">{desc}</div>
                    <span class="modality-badge {'badge-done' if selected == key else 'badge-pending'}">
                        {'Selected' if selected == key else 'Available'}
                    </span>
                </div>
                """, unsafe_allow_html=True)

        if st.button("Start Testing →", type="primary", use_container_width=True, key="start_single"):
            st.session_state.selected_modalities = [selected]
            st.session_state.scores = {"speech": None, "hw": None, "eeg": None}
            go(selected)

    else:
        st.markdown("""
        <div class="info-box">
            Select at least two modalities for cross-modal screening.
        </div>
        """, unsafe_allow_html=True)

        c1, c2, c3 = st.columns(3)
        chosen = []
        for col, (key, icon, title, desc) in zip([c1, c2, c3], modalities):
            with col:
                checked = st.checkbox(f"{icon} {title}", key=f"cross_check_{key}")
                st.markdown(f"""
                <div class="modality-card">
                    <div class="modality-icon">{icon}</div>
                    <div class="modality-title">{title}</div>
                    <div class="modality-desc">{desc}</div>
                    <span class="modality-badge {'badge-done' if checked else 'badge-pending'}">
                        {'Selected' if checked else 'Not selected'}
                    </span>
                </div>
                """, unsafe_allow_html=True)
                if checked:
                    chosen.append(key)

        if st.button("Start Selected Tests →", type="primary", use_container_width=True, key="start_cross"):
            if len(chosen) < 2:
                st.error("Please select at least two modalities for cross-modal screening.")
            else:
                st.session_state.selected_modalities = chosen
                st.session_state.scores = {"speech": None, "hw": None, "eeg": None}
                go(chosen[0])

    st.markdown("---")
    if st.button("← Back to Screening Type", key="select_back"):
        go("mode_select")


# ═══════════════════════════════════════════════════════════
# SPEECH
# ═══════════════════════════════════════════════════════════
def show_speech():
    render_topbar()
    render_progress()

    st.markdown("""
    <div class="page-header">
        <div class="page-header-icon">🎙️</div>
        <div>
            <h1>Speech Analysis</h1>
            <p>Upload voice feature CSV or enter values manually</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if "speech" not in st.session_state.selected_modalities:
        st.warning("Speech was not selected for this screening session.")
        if st.button("Back to selected tests"):
            go("modality_select")
        return

    tab1, tab2 = st.tabs(["  📁 Upload CSV  ", "  ✏️ Enter Manually  "])

    with tab1:
        st.markdown("""
        <div class="info-box">
            Upload a CSV with 22 voice feature columns. The file should have a single data row
            with headers matching the standard Parkinson's voice dataset features.
        </div>
        """, unsafe_allow_html=True)

        uploaded = st.file_uploader("Drop CSV here or click to browse", type=["csv"], key="sp_csv")
        if uploaded:
            df = pd.read_csv(io.BytesIO(uploaded.getvalue()))
            row = df.iloc[0].to_dict()
            st.markdown(f"""
            <div style="background:#F0FDF4;border:1px solid #A7F3D0;border-radius:10px;
                        padding:0.75rem 1rem;font-size:0.83rem;color:#065F46;margin-bottom:1rem;">
                ✓ File loaded — <b>{uploaded.name}</b> · {len(df.columns)} columns detected
            </div>
            """, unsafe_allow_html=True)

            with st.expander("Preview feature values"):
                preview_df = pd.DataFrame([row]).T.reset_index()
                preview_df.columns = ["Feature", "Value"]
                st.dataframe(preview_df, use_container_width=True, height=300)

            if st.button("Run Speech Analysis →", type="primary", key="sp_csv_btn"):
                with st.spinner("Analysing…"):
                    res = requests.post(f"{BASE_URL}/analyze/speech", json=row, headers=auth_header())
                if res.status_code == 200:
                    d = res.json()
                    st.session_state.scores["speech"] = d["p_pd"]
                    render_risk_result(d["p_pd"], d["risk"], "Speech — PD Probability")
                    st.success("Speech score saved for this session.")
                else:
                    st.error(f"Analysis failed: {res.text}")

    with tab2:
        st.markdown("""
        <div class="info-box">
            Enter all 22 acoustic feature values below. Use precise decimal values
            from your voice analysis software.
        </div>
        """, unsafe_allow_html=True)

        features = [
            "MDVP:Fo(Hz)", "MDVP:Fhi(Hz)", "MDVP:Flo(Hz)", "MDVP:Jitter(%)",
            "MDVP:Jitter(Abs)", "MDVP:RAP", "MDVP:PPQ", "Jitter:DDP",
            "MDVP:Shimmer", "MDVP:Shimmer(dB)", "Shimmer:APQ3", "Shimmer:APQ5",
            "MDVP:APQ", "Shimmer:DDA", "NHR", "HNR", "RPDE", "DFA",
            "spread1", "spread2", "D2", "PPE"
        ]
        vals = {}
        cols = st.columns(3)
        for i, f in enumerate(features):
            with cols[i % 3]:
                vals[f] = st.number_input(f, value=0.0, format="%.6f", key=f"sp_man_{f}")

        if st.button("Run Speech Analysis →", type="primary", key="sp_man_btn"):
            with st.spinner("Analysing…"):
                res = requests.post(f"{BASE_URL}/analyze/speech", json=vals, headers=auth_header())
            if res.status_code == 200:
                d = res.json()
                st.session_state.scores["speech"] = d["p_pd"]
                render_risk_result(d["p_pd"], d["risk"], "Speech — PD Probability")
                st.success("Speech score saved for this session.")
            else:
                st.error(f"Analysis failed: {res.text}")

    render_saved_score_continue("speech")

    st.markdown("---")
    if st.button("← Back to Selected Tests", key="sp_back"):
        go("modality_select")


# ═══════════════════════════════════════════════════════════
# HANDWRITING
# ═══════════════════════════════════════════════════════════
def show_handwriting():
    render_topbar()
    render_progress()

    st.markdown("""
    <div class="page-header">
        <div class="page-header-icon">✍️</div>
        <div>
            <h1>Handwriting Analysis</h1>
            <p>Upload a spiral or wave drawing image for motor assessment</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if "handwriting" not in st.session_state.selected_modalities:
        st.warning("Handwriting was not selected for this screening session.")
        if st.button("Back to selected tests"):
            go("modality_select")
        return

    st.markdown("""
    <div class="info-box">
        Upload a JPG or PNG of the patient's handwriting sample (spiral/wave test).
        The image will be resized automatically before analysis.
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns([1.4, 1])
    with col1:
        uploaded = st.file_uploader("Drop image here or click to browse", type=["jpg", "jpeg", "png"], key="hw_img")
    with col2:
        if uploaded:
            st.image(uploaded, caption="Uploaded image", use_container_width=True)

    if uploaded:
        if st.button("Run Handwriting Analysis →", type="primary", key="hw_btn"):
            with st.spinner("Analysing image…"):
                res = requests.post(
                    f"{BASE_URL}/analyze/handwriting",
                    files={"image": (uploaded.name, uploaded.getvalue(), uploaded.type)},
                    headers=auth_header()
                )
            if res.status_code == 200:
                d = res.json()
                st.session_state.scores["hw"] = d["p_pd"]
                render_risk_result(d["p_pd"], d["risk"], "Handwriting — PD Probability")
                st.success("Handwriting score saved for this session.")
            else:
                st.error(f"Analysis failed: {res.text}")

    render_saved_score_continue("handwriting")

    st.markdown("---")
    if st.button("← Back to Selected Tests", key="hw_back"):
        go("modality_select")


# ═══════════════════════════════════════════════════════════
# EEG
# ═══════════════════════════════════════════════════════════
def show_eeg():
    render_topbar()
    render_progress()

    st.markdown("""
    <div class="page-header">
        <div class="page-header-icon">🧠</div>
        <div>
            <h1>EEG Analysis</h1>
            <p>Upload a BIDS-format ZIP containing an EEGLAB .set file</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if "eeg" not in st.session_state.selected_modalities:
        st.warning("EEG was not selected for this screening session.")
        if st.button("Back to selected tests"):
            go("modality_select")
        return

    st.markdown("""
    <div class="info-box">
        Upload a ZIP file containing the EEG recording in EEGLAB format (.set file inside).
        Resting-state recordings are preferred. The system will preprocess and extract features automatically.
    </div>
    """, unsafe_allow_html=True)

    uploaded = st.file_uploader("Drop ZIP here or click to browse", type=["zip"], key="eeg_zip")
    if uploaded:
        st.markdown(f"""
        <div style="background:#F0FDF4;border:1px solid #A7F3D0;border-radius:10px;
                    padding:0.75rem 1rem;font-size:0.83rem;color:#065F46;margin-bottom:1rem;">
            ✓ File loaded — <b>{uploaded.name}</b> · {len(uploaded.getvalue())//1024} KB
        </div>
        """, unsafe_allow_html=True)

        if st.button("Run EEG Analysis →", type="primary", key="eeg_btn"):
            with st.spinner("Processing EEG data… this may take a moment"):
                res = requests.post(
                    f"{BASE_URL}/analyze/eeg",
                    files={"eeg_zip": (uploaded.name, uploaded.getvalue(), "application/zip")},
                    headers=auth_header()
                )
            if res.status_code == 200:
                d = res.json()
                st.session_state.scores["eeg"] = d["p_pd"]
                render_risk_result(d["p_pd"], d["risk"], "EEG — PD Probability")
                if d.get("n_segs"):
                    st.markdown(f"""
                    <div style="text-align:center;font-size:0.8rem;color:#6B7A99;margin-top:0.5rem;">
                        Analysed across {d['n_segs']} EEG segments · Model: {d.get('model','—')}
                    </div>
                    """, unsafe_allow_html=True)
                st.success("EEG score saved for this session.")
            else:
                st.error(f"Analysis failed: {res.text}")

    render_saved_score_continue("eeg")

    st.markdown("---")
    if st.button("← Back to Selected Tests", key="eeg_back"):
        go("modality_select")


# ═══════════════════════════════════════════════════════════
# FUSE
# ═══════════════════════════════════════════════════════════
def show_fuse():
    render_topbar()
    render_progress()

    assessment_title = "Final Risk Assessment" if st.session_state.screening_mode == "single" else "Fused Risk Assessment"
    assessment_subtitle = "Final result using the selected modality score" if st.session_state.screening_mode == "single" else "Combined risk evaluation using selected available modality scores"

    st.markdown(f"""
    <div class="page-header">
        <div class="page-header-icon">⚡</div>
        <div>
            <h1>{assessment_title}</h1>
            <p>{assessment_subtitle}</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

    WEIGHTS = {"speech": 0.30, "hw": 0.25, "eeg": 0.45}

    def local_fuse(sc):
        available = {k: v for k, v in sc.items() if v is not None}
        if not available:
            return None, None
        total_w = sum(WEIGHTS[k] for k in available)
        fused = sum(WEIGHTS[k] * v for k, v in available.items()) / total_w
        if fused >= 0.65:
            risk = "High Risk"
        elif fused >= 0.40:
            risk = "Moderate Risk"
        else:
            risk = "Low Risk"
        return fused, risk

    if st.session_state.last_result:
        d = st.session_state.last_result
        fused = d.get("fused_score")
        risk = d.get("risk")
        saved_scores = d.get("used_scores", {})

        show_score_summary(saved_scores, WEIGHTS)
        render_risk_result(fused, risk, "Final Risk Score" if st.session_state.screening_mode == "single" else "Fused Risk Score")
        st.markdown(f"""
        <div style="text-align:center;font-size:0.82rem;color:#6B7A99;margin-top:0.5rem;">
            Results saved · Patient: <b>{d.get('patient_name','—')}</b> · ID: {d.get('patient_id','—') or '—'}
        </div>
        """, unsafe_allow_html=True)

        st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("🔄 Start New Screening", use_container_width=True, key="fuse_new"):
                reset_patient_session(clear_last_result=True)
                go("patient_start")
        with col_b:
            if st.session_state.history_exists:
                if st.button("📋 View History", use_container_width=True, key="fuse_hist"):
                    st.session_state.last_result = None
                    go("history")
        return

    selected = st.session_state.selected_modalities
    if not selected:
        st.warning("No modalities selected. Please select the available test data first.")
        if st.button("Go to modality selection"):
            go("modality_select")
        return

    scores = st.session_state.scores
    selected_score_keys = [score_key_for_modality(m) for m in selected]
    available_selected = {k: scores.get(k) for k in selected_score_keys if scores.get(k) is not None}

    if not available_selected:
        st.warning("No test scores available. Please run at least one selected screening test first.")
        if st.button("Back to Selected Tests"):
            go("modality_select")
        return

    if not selected_tests_complete():
        st.info("Some selected tests are still pending. You can still preview the available result, but complete all selected tests before saving.")
        nxt = next_uncompleted_modality()
        if nxt and st.button(f"Continue pending test: {modality_icon(nxt)} {modality_label(nxt)}", type="primary"):
            go(nxt)

    show_score_summary(scores, WEIGHTS)

    fused_preview, risk_preview = local_fuse({k: scores.get(k) for k in selected_score_keys})
    if fused_preview is not None:
        preview_label = "Preview — Final Score" if st.session_state.screening_mode == "single" else "Preview — Fused Score"
        render_risk_result(fused_preview, risk_preview, preview_label)

    st.markdown(f"""
    <div style="background:#EFF6FF;border:1px solid #BFDBFE;border-radius:10px;
                padding:0.75rem 1rem;font-size:0.88rem;color:#1E40AF;margin-bottom:1rem;">
        👤 Patient: <b>{st.session_state.patient_name}</b>
    </div>
    """, unsafe_allow_html=True)

    col_l, col_m, col_r = st.columns([1, 2, 1])
    with col_m:
        if st.button("💾 Save the results →", use_container_width=True, type="primary", key="fuse_btn"):
            if not selected_tests_complete():
                st.error("Please complete all selected modalities before saving the results.")
            elif not st.session_state.patient_name:
                st.error("Patient name is missing.")
            else:
                snapshot_scores = {
                    "speech": scores.get("speech") if "speech" in selected_score_keys else None,
                    "hw": scores.get("hw") if "hw" in selected_score_keys else None,
                    "eeg": scores.get("eeg") if "eeg" in selected_score_keys else None,
                }
                snapshot_pname = st.session_state.patient_name
                fused_val, risk_val = local_fuse({k: v for k, v in snapshot_scores.items() if v is not None})

                saved_pid = None
                try:
                    with st.spinner("Saving the results…"):
                        res = requests.post(
                            f"{BASE_URL}/analyze/fuse",
                            json={"patient_name": snapshot_pname, "scores": snapshot_scores},
                            headers=auth_header(),
                            timeout=15
                        )
                    if res.status_code == 200:
                        d = res.json()
                        saved_pid = d.get("patient_id")
                        fused_val = d.get("fused_score", fused_val)
                        risk_val = d.get("risk", risk_val)
                    else:
                        st.error(f"Could not save the results: {res.text}")
                        return
                except Exception as e:
                    st.error(f"Could not save the results: {e}")
                    return

                st.session_state.last_result = {
                    "fused_score": fused_val,
                    "risk": risk_val,
                    "patient_name": snapshot_pname,
                    "patient_id": saved_pid,
                    "used_scores": snapshot_scores,
                }
                st.session_state.history_cache = None
                refresh_history_exists()
                st.rerun()

    st.markdown("---")
    if st.button("← Back to Selected Tests", key="fuse_back"):
        go("modality_select")


def show_score_summary(scores, weights):
    selected = st.session_state.selected_modalities
    selected_keys = [score_key_for_modality(m) for m in selected]
    available_keys = [k for k in selected_keys if scores.get(k) is not None]
    raw_total = sum(weights[k] for k in available_keys) if available_keys else 1

    col1, col2, col3 = st.columns(3)
    modal_info = [
        (col1, "speech", "🎙️", "Speech"),
        (col2, "hw", "✍️", "Handwriting"),
        (col3, "eeg", "🧠", "EEG"),
    ]

    for col, key, icon, label in modal_info:
        with col:
            val = scores.get(key)
            base_w = int(weights[key] * 100)
            eff_w = int(weights[key] / raw_total * 100) if key in available_keys else 0
            selected_display = key in selected_keys

            if selected_display and val is not None:
                colour = "#DC2626" if val >= 0.65 else "#D97706" if val >= 0.40 else "#059669"
                wlabel = f"Effective weight: {eff_w}%" if len(available_keys) < 3 else f"Weight: {base_w}%"
                st.markdown(f"""
                <div class="ns-card" style="text-align:center;">
                    <div style="font-size:1.5rem">{icon}</div>
                    <div style="font-size:0.78rem;color:#6B7A99;font-weight:500;
                                text-transform:uppercase;letter-spacing:0.06em;margin:0.4rem 0;">{label}</div>
                    <div style="font-size:1.75rem;font-weight:700;font-family:'DM Mono',monospace;color:{colour};">{val:.3f}</div>
                    <div style="font-size:0.72rem;color:#9CA3AF;margin-top:0.25rem;">{wlabel}</div>
                </div>
                """, unsafe_allow_html=True)
            elif selected_display:
                st.markdown(f"""
                <div class="ns-card" style="text-align:center;opacity:0.55;">
                    <div style="font-size:1.5rem">{icon}</div>
                    <div style="font-size:0.78rem;color:#6B7A99;font-weight:500;
                                text-transform:uppercase;letter-spacing:0.06em;margin:0.4rem 0;">{label}</div>
                    <div style="font-size:1.1rem;color:#9CA3AF;">Pending</div>
                    <div style="font-size:0.72rem;color:#9CA3AF;margin-top:0.25rem;">Selected</div>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div class="ns-card" style="text-align:center;opacity:0.35;">
                    <div style="font-size:1.5rem">{icon}</div>
                    <div style="font-size:0.78rem;color:#6B7A99;font-weight:500;
                                text-transform:uppercase;letter-spacing:0.06em;margin:0.4rem 0;">{label}</div>
                    <div style="font-size:1.1rem;color:#9CA3AF;">Not selected</div>
                    <div style="font-size:0.72rem;color:#9CA3AF;margin-top:0.25rem;">Skipped</div>
                </div>
                """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════
# HISTORY
# ═══════════════════════════════════════════════════════════
def show_history():
    render_topbar()

    st.markdown("""
    <div class="page-header">
        <div class="page-header-icon">📋</div>
        <div>
            <h1>Patient History</h1>
            <p>All screening records saved under your account</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if st.session_state.history_cache is None:
        with st.spinner("Loading records…"):
            res = requests.get(f"{BASE_URL}/history/all/mine", headers=auth_header())
        if res.status_code == 200:
            st.session_state.history_cache = res.json()
            st.session_state.history_exists = bool(st.session_state.history_cache)
        else:
            st.error("Could not fetch history.")
            if st.button("← Back to New Screening"):
                go("patient_start")
            return

    records = st.session_state.history_cache

    if not records:
        st.markdown("""
        <div class="ns-card" style="text-align:center;padding:3rem;color:#6B7A99;">
            <div style="font-size:2.5rem;margin-bottom:1rem;">📭</div>
            <div style="font-weight:600;font-size:1rem;">No records yet</div>
            <div style="font-size:0.85rem;margin-top:0.5rem;">
                Complete a screening and save the results to see them here.
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        total = len(records)
        all_results = [r for rec in records for r in rec.get("screening_results", [])]
        high = sum(1 for r in all_results if r.get("risk_label") == "High Risk")
        mod = sum(1 for r in all_results if r.get("risk_label") == "Moderate Risk")
        low = sum(1 for r in all_results if r.get("risk_label") == "Low Risk")

        c1, c2, c3, c4 = st.columns(4)
        for col, num, label in [
            (c1, total, "Total Patients"),
            (c2, high, "High Risk"),
            (c3, mod, "Moderate Risk"),
            (c4, low, "Low Risk"),
        ]:
            with col:
                st.markdown(f"""
                <div class="stat-card">
                    <div class="stat-num">{num}</div>
                    <div class="stat-label">{label}</div>
                </div>
                """, unsafe_allow_html=True)

        st.markdown("<div style='height:1.25rem'></div>", unsafe_allow_html=True)

        search = st.text_input("🔍 Search by patient name", placeholder="Type to filter…", key="hist_search")
        filtered = [r for r in records if search.lower() in r.get("patient_name", "").lower()]

        if not filtered:
            st.info("No records match your search.")
        else:
            for rec in filtered:
                pname = rec.get("patient_name", "Unknown")
                date = rec.get("created_at", "")[:10] if rec.get("created_at") else "—"
                results = rec.get("screening_results", [])

                with st.expander(f"👤  {pname}   ·   {date}   ·   {len(results)} result(s)"):
                    if not results:
                        st.write("No results recorded.")
                    for i, r in enumerate(results):
                        fused = r.get("fused_score")
                        risk = r.get("risk_label", "—")
                        risk_cls = {
                            "High Risk": "risk-high",
                            "Moderate Risk": "risk-moderate",
                            "Low Risk": "risk-low"
                        }.get(risk, "")

                        col1, col2, col3 = st.columns([2, 2, 1])
                        with col1:
                            eeg = r.get("eeg_score")
                            sp = r.get("speech_score")
                            hw = r.get("hw_score")
                            st.markdown(f"""
                            <div style="font-size:0.83rem;">
                                <span class="score-pill">🧠 EEG: {f"{eeg:.3f}" if eeg is not None else "—"}</span>&nbsp;
                                <span class="score-pill">🎙️ Speech: {f"{sp:.3f}" if sp is not None else "—"}</span>&nbsp;
                                <span class="score-pill">✍️ HW: {f"{hw:.3f}" if hw is not None else "—"}</span>
                            </div>
                            """, unsafe_allow_html=True)
                        with col2:
                            if fused is not None:
                                st.markdown(f"""
                                <div style="font-size:0.83rem;">
                                    Final score:&nbsp;
                                    <span style="font-family:'DM Mono',monospace;font-weight:700;">
                                        {fused:.4f}
                                    </span>
                                </div>
                                """, unsafe_allow_html=True)
                        with col3:
                            st.markdown(f'<div class="{risk_cls}" style="font-size:0.78rem;">{risk}</div>', unsafe_allow_html=True)

                        if i < len(results) - 1:
                            st.divider()

    st.markdown("---")
    if st.button("← Start New Screening", key="hist_back"):
        reset_patient_session(clear_last_result=True)
        go("patient_start")


# ═══════════════════════════════════════════════════════════
# ROUTER
# ═══════════════════════════════════════════════════════════
render_sidebar()

if st.session_state.token is None:
    show_auth()
else:
    page = st.session_state.page
    if page in ["auth", "login"]:
        go("patient_start")
    elif page == "patient_start":
        show_patient_start()
    elif page == "mode_select":
        show_mode_select()
    elif page == "modality_select":
        show_modality_select()
    elif page == "speech":
        show_speech()
    elif page == "handwriting":
        show_handwriting()
    elif page == "eeg":
        show_eeg()
    elif page == "fuse":
        show_fuse()
    elif page == "history":
        show_history()
    else:
        show_patient_start()
