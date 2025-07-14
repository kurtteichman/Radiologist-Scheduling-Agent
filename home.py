from collections import defaultdict
import streamlit as st
import pandas as pd
from datetime import date, datetime
from utils.parse.parse_non_AI import (
    get_employee_names_and_caps,
    get_schedule_entries,
)
from utils.parse.parse_AI import extract_availability_matrix
from utils.schedule.scheduler import schedule_with_fallback_days_only
from utils.parse.parse_requests import process_note_against_schedule
import asyncio
import calendar
from io import StringIO  # ✅ for in-memory CSV
import pickle
import os

saving_values = False
using_preset = True

if not saving_values and using_preset:
    if "final_schedule" not in st.session_state and os.path.exists("preload_state.pkl"):
        with open("preload_state.pkl", "rb") as f:
            preload = pickle.load(f)
            for k, v in preload.items():
                st.session_state[k] = v


def render_calendar():
    st.subheader("Generated Calendar")
    for html in st.session_state.get("calendar_html_blocks", []):
        st.components.v1.html(html, height=600, scrolling=False)

    st.subheader("Color Legend")
    for name, color in st.session_state.get("color_map", {}).items():
        st.markdown(
            f"<span style='background-color: {color}; padding: 4px 8px; border-radius: 4px;'>{name}</span>",
            unsafe_allow_html=True
        )

def generate_unique_colors(names):
    n = len(names)
    color_map = {}
    for i, name in enumerate(sorted(names)):
        hue = int(360 * i / n)
        color_map[name] = f"hsl({hue}, 70%, 85%)"
    return color_map


def generate_calendar_html(schedule_entries, final_schedule):
    unique_radiologists = sorted(set(x for x in final_schedule if isinstance(x, str) and x != "N/A"))
    color_map = generate_unique_colors(unique_radiologists)

    assignments_by_month = defaultdict(list)
    for entry, person in zip(schedule_entries, final_schedule):
        d = entry["date"]
        assignments_by_month[(d.year, d.month)].append((d.day, person, entry["shift"]))

    html_blocks = []

    for (year, month), assignments in sorted(assignments_by_month.items()):
        first_day = date(year, month, 1)
        start_weekday = first_day.weekday()
        days_in_month = calendar.monthrange(year, month)[1]

        daily_shift_map = defaultdict(list)
        for day, person, shift in assignments:
            if person != "N/A":
                daily_shift_map[day].append((shift, person))

        html = f"<h2 style='margin-top: 2em'>{first_day.strftime('%B %Y')}</h2>"
        html += "<table style='border-collapse: collapse; width: 100%; table-layout: fixed;'>"
        html += "<tr>" + "".join(
            f"<th style='border: 1px solid #ccc; padding: 6px; background: #f0f0f0;'>{day}</th>"
            for day in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        ) + "</tr><tr>"

        for _ in range(start_weekday):
            html += "<td style='border: 1px solid #ccc; padding: 6px; height: 80px;'></td>"

        day_counter = 1
        while day_counter <= days_in_month:
            weekday = (start_weekday + day_counter - 1) % 7
            assignments_today = daily_shift_map.get(day_counter, [])
            content = f"<strong>{day_counter}</strong><br>"
            for shift, name in sorted(assignments_today):
                bg_color = color_map.get(name, "#ffffff")
                content += (
                    f"<div style='background-color: {bg_color}; border-radius: 4px; padding: 2px 4px; "
                    f"margin: 2px 0; font-size: 12px;'>{shift}: {name}</div>"
                )

            html += (
                f"<td style='border: 1px solid #ccc; padding: 6px; height: 80px; vertical-align: top;'>"
                f"{content}</td>"
            )

            if weekday == 6 and day_counter != days_in_month:
                html += "</tr><tr>"

            day_counter += 1

        remaining = (7 - ((start_weekday + days_in_month) % 7)) % 7
        for _ in range(remaining):
            html += "<td style='border: 1px solid #ccc; padding: 6px; height: 80px;'></td>"

        html += "</tr></table>"
        html_blocks.append(html)

    return html_blocks, color_map


# App Config
st.set_page_config(page_title="Radiologist Shift Scheduler", layout="wide")
st.title("Radiologist Shift Scheduling App")

# Step 1 Header
st.header("Step 1: Upload Files")

# File Upload
scheduling_csv = st.file_uploader("Upload Scheduling CSV", type=["csv"], key="schedule_csv")
radiologist_csv = st.file_uploader("Upload Radiologist Profile CSV", type=["csv"], key="radiologist_csv")

if scheduling_csv:
    st.success("Scheduling CSV uploaded successfully.")
if radiologist_csv:
    st.success("Radiologist profile CSV uploaded successfully.")

if scheduling_csv and radiologist_csv:
    if st.button("Create Schedule"):
        schedule_df = pd.read_csv(scheduling_csv)
        radiologist_df = pd.read_csv(radiologist_csv)

        start_date = datetime.strptime(schedule_df["Date"].iloc[0], "%Y-%m-%d").date()
        end_date = datetime.strptime(schedule_df["Date"].iloc[-1], "%Y-%m-%d").date()

        schedule_entries = get_schedule_entries(schedule_df)
        employee_names, monthly_caps = get_employee_names_and_caps(radiologist_df, start_date, end_date)

        with st.spinner("Extracting availability and requests..."):
            availability_matrix, requested_shift_map = asyncio.run(
                extract_availability_matrix(radiologist_df, start_date, end_date)
            )

        with st.spinner("Running scheduler..."):
            final_schedule, assignments_by_emp, uncovered = schedule_with_fallback_days_only(
                employee_names,
                schedule_entries,
                availability_matrix,
                monthly_caps,
                requested_shift_map=requested_shift_map,
            )

        calendar_html_blocks, color_map = generate_calendar_html(schedule_entries, final_schedule)

        # ✅ Save in session state to persist across reruns
        st.session_state["calendar_html_blocks"] = calendar_html_blocks
        st.session_state["color_map"] = color_map
        st.session_state["assignments_by_emp"] = assignments_by_emp
        st.session_state["final_schedule"] = final_schedule
        st.session_state["schedule_entries"] = schedule_entries
        st.session_state["employee_names"] = employee_names
        st.session_state["monthly_caps"] = monthly_caps
        st.session_state["availability_matrix"] = availability_matrix
        st.session_state["requested_shift_map"] = requested_shift_map
        st.session_state["start_date"] = start_date

        if uncovered:
            uncovered_df = schedule_df[
                schedule_df.apply(lambda row: any(
                    row["Date"] == s["date"].strftime("%Y-%m-%d") and row["Shift"] == s["shift"]
                    for s in uncovered
                ), axis=1)
            ]
            csv_buffer = StringIO()
            uncovered_df.to_csv(csv_buffer, index=False)
            st.session_state["moon_csv"] = csv_buffer.getvalue()
            st.session_state["moon_ready"] = True
        else:
            st.session_state["moon_ready"] = False
        if saving_values:
            snapshot = {
                "calendar_html_blocks": st.session_state["calendar_html_blocks"],
                "color_map": st.session_state["color_map"],
                "assignments_by_emp": st.session_state["assignments_by_emp"],
                "final_schedule": st.session_state["final_schedule"],
                "schedule_entries": st.session_state["schedule_entries"],
                "employee_names": st.session_state["employee_names"],
                "monthly_caps": st.session_state["monthly_caps"],
                "availability_matrix": st.session_state["availability_matrix"],
                "requested_shift_map": st.session_state["requested_shift_map"],
                "start_date": st.session_state["start_date"],
                "moon_ready": st.session_state["moon_ready"],
                "moon_csv": st.session_state["moon_csv"]
            }

            with open("preload_state.pkl", "wb") as f:
                pickle.dump(snapshot, f)
        

# 🔁 Re-render saved output after rerun (e.g. after clicking download)
if "calendar_html_blocks" in st.session_state:
    render_calendar()

    if st.session_state.get("moon_ready"):
        st.subheader("Moonlighting Shifts Export")
        download_success = st.download_button(
            label="📥 Download Moonlighting Shifts CSV",
            data=st.session_state["moon_csv"],
            file_name="moonlighting_shifts.csv",
            mime="text/csv",
            key="moon_download_btn"
        )
        if download_success:
            st.session_state["download_success"] = True
        if st.session_state.get("download_success"):
            st.success("✅ Download successful!")
    else:
        st.info("✅ All shifts covered. No Moonlighting CSV generated.")

    st.markdown("---")
    st.header("Step 2: Make Final Edits")
    name_input = st.text_input("Requestor Name", key="edit_name")
    note_input = st.text_area("Natural Language Request", key="edit_request", height=150)

    if name_input.strip() and note_input.strip() and st.button("Submit"):
        with st.spinner("Processing request..."):
            result = asyncio.run(
                process_note_against_schedule(
                    note_input,
                    name_input,
                    st.session_state["start_date"],
                    st.session_state["availability_matrix"],
                    st.session_state["assignments_by_emp"],
                    st.session_state["requested_shift_map"],
                    st.session_state["monthly_caps"],
                    st.session_state["schedule_entries"],
                    st.session_state["final_schedule"]
                )
            )
            (
                new_final,
                new_by_emp,
                _,
                new_availability,
                new_requested_map,
                new_caps,
                new_names,
            ) = result

            st.session_state["final_schedule"] = new_final
            st.session_state["assignments_by_emp"] = new_by_emp
            st.session_state["availability_matrix"] = new_availability
            st.session_state["requested_shift_map"] = new_requested_map
            st.session_state["monthly_caps"] = new_caps
            st.session_state["employee_names"] = new_names

            st.session_state["schedule_entries"] = st.session_state["schedule_entries"]  # already exists, but good for completeness
            st.session_state["start_date"] = st.session_state["start_date"]  # same here

            st.session_state["calendar_html_blocks"], st.session_state["color_map"] = generate_calendar_html(
                st.session_state["schedule_entries"], new_final
            )
            st.success("✅ Update successful. Schedule refreshed.")
            st.rerun()  # 🚀 Force a clean refresh of the interface