import streamlit as st
import pandas as pd
from datetime import date
import os
import altair as alt

# ================== CONFIG ==================
st.set_page_config(
    page_title="Akshat & Ananya – Fitness Tracker",
    page_icon="🔥",
    layout="wide"
)

DATA_FILE = "data.csv"
GOAL_FILE = "goals.csv"
WEIGHT_FILE = "weights.csv"

PEOPLE = ["Akshat", "Ananya"]

# ================== HELPERS ==================
def load_or_create(file, cols):
    if os.path.exists(file):
        return pd.read_csv(file)
    return pd.DataFrame(columns=cols)

def save(df, file):
    df.to_csv(file, index=False)

def conservative_bmr(sex, w, h, age):
    base = 10*w + 6.25*h - 5*age + (5 if sex=="Male" else -161)
    return base * 0.80  # conservative by design

def activity_excess(met, w, mins):
    return max(0, (met - 1) * w * (mins / 60))

# ================== DATA ==================
df = load_or_create(DATA_FILE, [
    "Date","Person","Calories Eaten",
    "Steps","Walk MET","Walk Minutes",
    "WT Minutes","WT MET",
    "BMR","Active Burn","Total Burn","Net Calories"
])

goals = load_or_create(GOAL_FILE, ["Person","Target Weight"])
weights = load_or_create(WEIGHT_FILE, ["Date","Person","Weight"])

# ================== HEADER ==================
st.title("🔥 Fitness Tracker")
person = st.selectbox("Who are you?", PEOPLE)

# ================== PERSONAL INFO ==================
with st.expander("👤 Personal info (used for calculations)", expanded=False):
    c1,c2,c3 = st.columns(3)
    with c1:
        height = st.number_input("Height (cm)", 100, 230, 175 if person=="Akshat" else 160)
        weight_now = st.number_input("Current weight (kg)", 30.0, 250.0, 75.0 if person=="Akshat" else 60.0)
    with c2:
        age = st.number_input("Age", 13, 120, 24)
        sex = st.selectbox("Sex", ["Male","Female"])
    with c3:
        bmr = conservative_bmr(sex, weight_now, height, age)
        st.metric("Conservative Resting Burn", f"{int(bmr)} kcal")

# ================== DAILY LOG ==================
st.subheader("📝 Daily Activity")

with st.form("daily"):
    c1,c2,c3 = st.columns(3)

    with c1:
        eaten = st.number_input("Calories eaten", 0, 5000, 1800)
        steps = st.number_input("Steps", 0, 40000, 8000)

    with c2:
        walk_met = st.selectbox("Walking intensity (MET)", [2.8,3.5,4.5])
        walk_mins = st.number_input("Walking minutes", 0, 300, 0)

    with c3:
        wt_mins = st.number_input("Weight training minutes", 0, 300, 30)
        wt_met = st.selectbox("Weight training intensity (MET)", [3.5,5.0,6.0])

    submit = st.form_submit_button("Save today")

if submit:
    active = activity_excess(walk_met, weight_now, walk_mins) + \
             activity_excess(wt_met, weight_now, wt_mins)
    total = bmr + active
    net = eaten - total

    df = pd.concat([df, pd.DataFrame([{
        "Date": date.today().isoformat(),
        "Person": person,
        "Calories Eaten": eaten,
        "Steps": steps,
        "Walk MET": walk_met,
        "Walk Minutes": walk_mins,
        "WT Minutes": wt_mins,
        "WT MET": wt_met,
        "BMR": round(bmr,1),
        "Active Burn": round(active,1),
        "Total Burn": round(total,1),
        "Net Calories": round(net,1)
    }])])

    save(df, DATA_FILE)
    st.success("Saved ✅")

# ================== WEEKLY WEIGHT ==================
st.subheader("⚖️ Weekly Weight Check-in")

with st.form("weight"):
    w = st.number_input("Enter weight (kg)", 30.0, 250.0, weight_now, step=0.1)
    log = st.form_submit_button("Log weekly weight")

if log:
    weights = pd.concat([weights, pd.DataFrame([{
        "Date": date.today().isoformat(),
        "Person": person,
        "Weight": w
    }])])
    save(weights, WEIGHT_FILE)
    st.success("Weight saved ✅")

# ================== GOAL ==================
st.subheader("🎯 Goal")

with st.form("goal"):
    target = st.number_input("Target weight (kg)", 30.0, 250.0, weight_now-5)
    setg = st.form_submit_button("Save goal")

if setg:
    goals = goals[goals.Person != person]
    goals = pd.concat([goals, pd.DataFrame([{"Person":person,"Target Weight":target}])])
    save(goals, GOAL_FILE)
    st.success("Goal saved")

# ================== PROGRESS & PREDICTION ==================
st.divider()
st.subheader("📊 Actual vs Predicted Progress")

pw = weights[weights.Person == person].copy()
pdaily = df[df.Person == person].copy()
pg = goals[goals.Person == person]

if not pw.empty and not pg.empty and not pdaily.empty:
    pw["Date"] = pd.to_datetime(pw["Date"])
    pdaily["Date"] = pd.to_datetime(pdaily["Date"])

    pw = pw.sort_values("Date")
    pdaily = pdaily.sort_values("Date")

    # ----- unified daily timeline -----
    start_date = min(pw["Date"].min(), pdaily["Date"].min())
    end_date = max(pw["Date"].max(), pdaily["Date"].max())

    timeline = pd.DataFrame({
        "Date": pd.date_range(start_date, end_date, freq="D")
    })

    # ----- actual weight (forward-filled) -----
    actual = timeline.merge(
        pw[["Date", "Weight"]],
        on="Date",
        how="left"
    )
    actual["Weight"] = actual["Weight"].ffill()
    start_weight = actual.iloc[0]["Weight"]

    # ----- predicted weight (daily, anchored) -----
    daily = timeline.merge(
        pdaily[["Date", "Net Calories"]],
        on="Date",
        how="left"
    ).fillna(0)

    cumulative_deficit = daily["Net Calories"].clip(upper=0).cumsum()
    predicted_weight = start_weight + (cumulative_deficit * 0.75) / 7700

    # ----- LONG FORMAT (CRITICAL FIX) -----
    plot_df = pd.concat([
        pd.DataFrame({
            "Date": timeline["Date"],
            "Weight": actual["Weight"],
            "Type": "Actual"
        }),
        pd.DataFrame({
            "Date": timeline["Date"],
            "Weight": predicted_weight,
            "Type": "Predicted"
        })
    ])

    # ----- granular Y-axis -----
    y_min = plot_df["Weight"].min() - 0.2
    y_max = plot_df["Weight"].max() + 0.2

    chart = alt.Chart(plot_df).mark_line(point=True).encode(
        x=alt.X("Date:T", title="Date"),
        y=alt.Y(
            "Weight:Q",
            scale=alt.Scale(domain=[y_min, y_max], zero=False),
            axis=alt.Axis(format=".1f", tickCount=8),
            title="Weight (kg)"
        ),
        color=alt.Color(
            "Type:N",
            scale=alt.Scale(
                domain=["Actual", "Predicted"],
                range=["#2ecc71", "#e67e22"]
            )
        )
    ).properties(
        height=360,
        title="Actual (solid) vs Predicted (dashed) — aligned & granular"
    )

    st.altair_chart(chart, use_container_width=True)

    st.caption(
        "Actual weight = scale measurements (forward-filled). "
        "Predicted weight = calorie-based estimate (75% efficiency). "
        "Shared Y-axis, no zero baseline."
    )

    # ================== PIE CHARTS ==================
    st.subheader("📊 Progress Breakdown")

    pie_cols = st.columns(3)
    progress_vals = []

    for i, p in enumerate(PEOPLE):
        pw_p = weights[weights.Person == p]
        pg_p = goals[goals.Person == p]

        if pw_p.empty or pg_p.empty:
            pie_cols[i].info("No data")
            continue

        pw_p = pw_p.sort_values("Date")
        start = pw_p.iloc[0]["Weight"]
        curr = pw_p.iloc[-1]["Weight"]
        tgt = pg_p.iloc[0]["Target Weight"]

        pct = max(0, min(1, (start - curr) / (start - tgt) if start > tgt else 1))
        progress_vals.append(pct)

        pie_df = pd.DataFrame({
            "State": ["Completed", "Remaining"],
            "Value": [pct, 1 - pct]
        })

        pie = alt.Chart(pie_df).mark_arc(innerRadius=50).encode(
            theta="Value:Q",
            color=alt.Color(
                "State:N",
                scale=alt.Scale(range=["#2ecc71", "#e74c3c"])
            )
        ).properties(title=p)

        pie_cols[i].altair_chart(pie, use_container_width=True)

    if progress_vals:
        avg = sum(progress_vals) / len(progress_vals)
        total_df = pd.DataFrame({
            "State": ["Completed", "Remaining"],
            "Value": [avg, 1 - avg]
        })

        pie_total = alt.Chart(total_df).mark_arc(innerRadius=60).encode(
            theta="Value:Q",
            color=alt.Color(
                "State:N",
                scale=alt.Scale(range=["#3498db", "#bdc3c7"])
            )
        ).properties(title="Together")

        pie_cols[-1].altair_chart(pie_total, use_container_width=True)

else:
    st.info("Add daily logs + weekly weights to see progress.")

# ================== FOOTER ==================
st.markdown("---")
st.caption("Weight is the source of truth. Calories are guidance. Predictions are estimates.")
