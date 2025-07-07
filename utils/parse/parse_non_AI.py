import pandas as pd
from datetime import datetime

from datetime import datetime
import pandas as pd

def get_employee_names_and_caps(radiologist_df: pd.DataFrame, start_date: datetime.date, end_date: datetime.date):
    """
    Extracts:
    - employee_names: List[str]
    - monthly_caps: Dict[(employee_index, YYYY-MM), int]

    Each radiologist is assumed available for the entire schedule span unless otherwise specified.
    """
    employee_names = list(radiologist_df["Radiologist_ID"])
    monthly_caps = {}

    # Generate YYYY-MM strings from start_date to end_date
    month_set = pd.date_range(start=start_date, end=end_date, freq='MS').strftime("%Y-%m").tolist()

    for i, row in radiologist_df.iterrows():
        for ym in month_set:
            monthly_caps[(i, ym)] = int(row["Maximum_Shifts_Per_Month"])

    return employee_names, monthly_caps

def get_schedule_entries(schedule_df: pd.DataFrame):
    """
    Converts scheduling CSV into a list of {date, shift} dicts.

    Expected columns: "Date", "Shift"
    """
    schedule_entries = []

    for _, row in schedule_df.iterrows():
        entry = {
            "date": datetime.strptime(row["Date"], "%Y-%m-%d").date(),
            "shift": row["Shift"]
        }
        schedule_entries.append(entry)

    return schedule_entries