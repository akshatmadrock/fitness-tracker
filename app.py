import streamlit as st
import pandas as pd
from datetime import date
import altair as alt
import sqlite3

# ================== CONFIG ==================
st.set_page_config(
    page_title="Akshat & Ananya – Fitness Tracker",
    page_icon="🔥",
    layout="wide"
)

PEOPLE = ["Akshat", "Ananya"]
DB_FILE = "fitness.db"

# ================== DATABASE ==================
def get_conn():
    return sqlite3.connect(DB_FILE, check_same_thread=False)

def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS daily_log (
        date TEXT,
        person TEXT,
        calories_eaten REAL,
        steps INTEGER,
        walk_met REAL,
        walk_minutes REAL,
        wt_minutes REAL,
        wt_met REAL,
        bmr REAL,
        active_burn REAL,
        total_burn REAL,
        net_calories REAL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS weekly_weight (
        date TEXT,
        person TEXT,
        weight REAL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS goals (
        person TEXT PRIMARY KEY,
        target_weight REAL
    )
    """)

    conn.commit()
    conn.close()

init_db()

# ================== HELPERS ==================
def conservative_bmr(sex, w, h, age):
    base = 10*w + 6.25*h - 5*age + (5 if sex=="Male" else -161)
    return base * 0.80

def activity_excess(met, w, mins):
    return max(0, (met - 1) * w * (mins / 60))

def get_latest_weight(person, fallback):
    conn = get_conn()
    row = conn.execute(
        """
        SELECT weight
        FROM weekly_weight
        WHERE person = ?
        ORDER BY date DESC
        LIMIT 1
        """,
        (person,)
    ).fetchone()
    conn.close()
    return row[0] if row else fallback

# ================== LOAD DATA ==================
conn = get_conn()
df = pd.read_sql("SELECT * FROM daily_log", conn)
weights = pd.read_sql("SELECT * FROM weekly_weight", conn)
goals = pd.read_sql("SELECT * FROM goals", conn)
conn.close()

df.rename(columns={
    "date":"Date","person":"Person","calories_eaten":"Calories Eaten",
    "steps":"Steps","walk_met":"Walk MET","walk_minutes":"Walk Minutes",
    "wt_minutes":"WT Minutes","wt_met":"WT MET",
    "bmr":"BMR","active_burn":"Active Burn",
    "total_burn":"Total Burn","net_calories":"Net Calories"
}, inplace=True)

weights.rename(columns={"date":"Date","person":"Person","weight":"Weight"}, inplace=True)
goals.rename(columns={"person":"Person","target_weight":"Target Weight"}, inplace=True)

# ================== HEADER ==================
st.title("🔥 Fitness Tracker")
person = st.selectbox("Who are you?", PEOPLE)

# ================== PERSONAL INFO ==================
with st.expander("👤 Personal info", expanded=False):
    c1,c2,c3 = st.columns(3)

    with c1:
        height = st.number_input("Height (cm)", 100, 230, 175 if person=="Akshat" else 160)

    with c2:
        age = st.number_input("Age", 13, 120, 24)
        sex = st.selectbox("Sex", ["Male","Female"])

    with c3:
        latest_weight = get_latest_weight(person, 75.0 if person=="Akshat" else 60.0)
        bmr = conservative_bmr(sex, latest_weight, height, age)
        st.metric("Latest weight", f"{latest_weight:.1f} kg")
        st.metric("Conservative BMR", f"{int(bmr)} kcal")

# ================== DAILY LOG ==================
st.subheader("📝 Daily Activity")

with st.form("daily"):
    log_date = st.date_input("Date", value=date.today())

    c1,c2,c3 = st.columns(3)
    with c1:
        eaten = st.number_input("Calories eaten", 0, 5000, 1800)
        steps = st.number_input("Steps", 0, 40000, 8000)
    with c2:
        walk_met = st.selectbox("Walking MET", [2.8,3.5,4.5])
        walk_mins = st.number_input("Walking minutes", 0, 300, 0)
    with c3:
        wt_mins = st.number_input("Weight training minutes", 0, 300, 30)
        wt_met = st.selectbox("Weight training MET", [3.5,5.0,6.0])

    submit = st.form_submit_button("Save daily log")

if submit:
    active = (
        activity_excess(walk_met, latest_weight, walk_mins) +
        activity_excess(wt_met, latest_weight, wt_mins)
    )
    total = bmr + active
    net = eaten - total

    conn = get_conn()
    pd.DataFrame([{
        "date": log_date.isoformat(),
        "person": person,
        "calories_eaten": eaten,
        "steps": steps,
        "walk_met": walk_met,
        "walk_minutes": walk_mins,
        "wt_minutes": wt_mins,
        "wt_met": wt_met,
        "bmr": round(bmr,1),
        "active_burn": round(active,1),
        "total_burn": round(total,1),
        "net_calories": round(net,1)
    }]).to_sql("daily_log", conn, if_exists="append", index=False)
    conn.close()

    st.success("Daily log saved ✅")

# ================== WEEKLY WEIGHT ==================
st.subheader("⚖️ Weekly Weight")

with st.form("weight"):
    weigh_date = st.date_input("Week date", value=date.today())
    w = st.number_input("Weight (kg)", 30.0, 250.0, latest_weight, step=0.1)
    log = st.form_submit_button("Save weight")

if log:
    conn = get_conn()
    pd.DataFrame([{
        "date": weigh_date.isoformat(),
        "person": person,
        "weight": w
    }]).to_sql("weekly_weight", conn, if_exists="append", index=False)
    conn.close()
    st.success("Weight saved ✅")

# ================== GOAL ==================
st.subheader("🎯 Goal")

with st.form("goal"):
    target = st.number_input("Target weight (kg)", 30.0, 250.0, latest_weight-5)
    setg = st.form_submit_button("Save goal")

if setg:
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO goals (person, target_weight) VALUES (?, ?)",
        (person, target)
    )
    conn.commit()
    conn.close()
    st.success("Goal saved ✅")

# ================== PROGRESS & PREDICTION ==================
st.divider()
st.subheader("📊 Actual vs Predicted Weight")

pw = weights[weights.Person == person].copy()
pdaily = df[df.Person == person].copy()

if not pw.empty and not pdaily.empty:
    pw["Date"] = pd.to_datetime(pw["Date"])
    pdaily["Date"] = pd.to_datetime(pdaily["Date"])

    pw = pw.sort_values("Date")
    pdaily = pdaily.sort_values("Date")

    timeline = pd.DataFrame({
        "Date": pd.date_range(
            min(pw.Date.min(), pdaily.Date.min()),
            max(pw.Date.max(), pdaily.Date.max()),
            freq="D"
        )
    })

    actual = timeline.merge(pw[["Date","Weight"]], on="Date", how="left")
    actual["Weight"] = actual["Weight"].ffill()
    start_weight = actual.iloc[0]["Weight"]

    daily = timeline.merge(pdaily[["Date","Net Calories"]], on="Date", how="left").fillna(0)
    predicted = start_weight + (daily["Net Calories"].clip(upper=0).cumsum()*0.75)/7700

    plot_df = pd.concat([
        pd.DataFrame({"Date":timeline.Date,"Weight":actual.Weight,"Type":"Actual"}),
        pd.DataFrame({"Date":timeline.Date,"Weight":predicted,"Type":"Predicted"})
    ])

    chart = alt.Chart(plot_df).mark_line(point=True).encode(
        x="Date:T",
        y=alt.Y("Weight:Q", axis=alt.Axis(format=".1f")),
        color="Type:N"
    ).properties(height=380)

    st.altair_chart(chart, use_container_width=True)
else:
    st.info("Add dated daily logs and weekly weights to see graphs.")

st.markdown("---")
st.caption("Weight = truth. Calories = guidance. Predictions are conservative.")
