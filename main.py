import streamlit as st
import random
from collections import defaultdict
import calendar
import pandas as pd
from datetime import datetime, date

# Set page title and configuration
st.set_page_config(
    page_title="Employee Scheduler",
    page_icon="📅",
    layout="wide"
)

# Class definition for employees
class Employee:
    def __init__(self, name, unavailable_dates=None, mandatory_dates=None):
        self.name = name
        self.unavailable_dates = unavailable_dates if unavailable_dates else []  # [(date, shift), ...]
        self.mandatory_dates = mandatory_dates if mandatory_dates else []  # [(date, shift), ...]
        self.assigned_shifts = []

    def is_available(self, date_obj, shift):
        """Check if employee is available on a specific date and shift"""
        # Check if this specific date and shift combination is marked as unavailable
        if (date_obj, shift) in self.unavailable_dates:
            return False
        return True

    def must_work(self, date_obj, shift):
        """Check if employee must work on a specific date and shift"""
        return (date_obj, shift) in self.mandatory_dates

# Function to create schedule
def create_schedule(employees, shifts_per_day, people_per_shift, month, year, week=None):
    days_in_month = calendar.monthrange(year, month)[1]

    # Filter days based on selected week if specified
    if week is not None:
        # Get all days in month
        month_cal = calendar.monthcalendar(year, month)
        # Filter only days in the selected week (0-indexed)
        days_to_schedule = [day for day in month_cal[week] if day != 0]
    else:
        # Schedule the entire month
        days_to_schedule = list(range(1, days_in_month + 1))

    schedule = defaultdict(dict)

    # First, identify mandatory work days for each employee
    mandatory_assignments = defaultdict(list)  # {(day_num, shift): [employee1, employee2, ...]}

    for day_num in days_to_schedule:
        current_date = date(year, month, day_num)
        
        for shift in shifts_per_day:
            for emp in employees:
                # Check if employee MUST work this specific date and shift
                if emp.must_work(current_date, shift):
                    # Add to mandatory assignments
                    mandatory_assignments[(day_num, shift)].append(emp)

    # Now schedule all days, prioritizing:
    # 1. Mandatory assignments first
    # 2. Balance shift counts among remaining employees

    for day_num in days_to_schedule:
        current_date = date(year, month, day_num)

        for shift in shifts_per_day:
            # Start with any mandatory employees for this day/shift
            mandatory_emps = mandatory_assignments.get((day_num, shift), [])

            # First schedule mandatory employees (up to people_per_shift)
            if len(mandatory_emps) >= people_per_shift:
                # If we have more mandatory employees than needed, prioritize those with fewer shifts
                mandatory_emps.sort(key=lambda e: len(e.assigned_shifts))
                selected_employees = mandatory_emps[:people_per_shift]
            else:
                # Use all mandatory employees plus balance with other available employees
                selected_employees = mandatory_emps.copy()

                # How many more employees do we need?
                remaining_spots = people_per_shift - len(selected_employees)

                if remaining_spots > 0:
                    # Find available employees who are not already scheduled for this day
                    available_employees = [
                        e for e in employees 
                        if e.is_available(current_date, shift) and 
                        (day_num not in [s[0] for s in e.assigned_shifts]) and
                        e not in selected_employees
                    ]

                    # Sort by number of assigned shifts (ascending) to balance workload
                    available_employees.sort(key=lambda e: len(e.assigned_shifts))

                    # Select employees with fewest shifts 
                    selected_employees.extend(available_employees[:remaining_spots])

            if not selected_employees:
                schedule[day_num][shift] = ["No Available Employee"]
                continue

            schedule[day_num][shift] = [emp.name for emp in selected_employees]
            for emp in selected_employees:
                emp.assigned_shifts.append((day_num, shift))

    return schedule

# Function to display schedule in a calendar format
def display_schedule(schedule, month, year, week=None):
    # Create a calendar for the month
    cal = calendar.monthcalendar(year, month)
    month_name = calendar.month_name[month]

    # Determine title based on whether a specific week is selected
    if week is not None:
        # Get week days for display
        week_days = [day for day in cal[week] if day != 0]
        if week_days:
            start_day = min(week_days)
            end_day = max(week_days)
            st.subheader(f"📅 Generated Schedule for Week {week+1} ({start_day}-{end_day} {month_name} {year})")
            # Filter calendar to just show the selected week
            cal = [cal[week]]
    else:
        st.subheader(f"📅 Generated Schedule for {month_name} {year}")

    # Display calendar in a visual format
    st.write("### Calendar View")

    # Calendar header
    header_cols = st.columns(7)
    for i, day_name in enumerate([calendar.day_abbr[i] for i in range(7)]):
        with header_cols[i]:
            st.markdown(f"**{day_name}**", help=calendar.day_name[i])

    # Calendar body
    for week_num, week_days in enumerate(cal):
        cols = st.columns(7)
        for i, day in enumerate(week_days):
            with cols[i]:
                if day == 0:  # Day belongs to previous/next month
                    st.write("")
                else:
                    # Create a container for this day
                    day_date = date(year, month, day)
                    st.markdown(f"**{day}**")

                    # Check if this day has shifts scheduled
                    if day in schedule:
                        for shift, employees in schedule[day].items():
                            employee_str = ", ".join(employees) if isinstance(employees, list) else employees
                            st.markdown(f"*{shift}:* {employee_str}", help=f"Shift: {shift}\nEmployees: {employee_str}")

    # Also show the data in a table for easier reference
    st.write("### Tabular View")
    df_data = []
    for day in sorted(schedule.keys()):
        day_name = calendar.day_name[calendar.weekday(year, month, day)]
        for shift, employees in schedule[day].items():
            employee_names = ', '.join(employees) if isinstance(employees, list) else employees
            df_data.append({
                "Day": f"{day} ({day_name})",
                "Shift": shift,
                "Employees": employee_names
            })

    if df_data:
        df = pd.DataFrame(df_data)
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.warning("No schedule generated.")

# Main function
def main():
    st.title("👥 Employee Scheduler 📆")
    st.write("Generate work schedules that respect employee availability restrictions")

    # Sidebar for inputs
    with st.sidebar:
        st.header("Schedule Configuration")

        # Month and year selection
        today = datetime.today()
        month = st.selectbox("Select Month", 
                            options=range(1, 13),
                            format_func=lambda x: calendar.month_name[x],
                            index=today.month-1)

        year = st.number_input("Select Year", 
                              min_value=2023, 
                              max_value=2030,
                              value=today.year)

        # Week selection options
        month_calendar = calendar.monthcalendar(year, month)
        num_weeks = len(month_calendar)

        # Create week options for display
        week_options = ["All Weeks"]
        for i, week in enumerate(month_calendar):
            # Filter out zeros (days that belong to other months)
            week_days = [day for day in week if day != 0]
            if week_days:  # Skip empty weeks
                start_day = min(week_days)
                end_day = max(week_days)
                week_options.append(f"Week {i+1} ({start_day}-{end_day})")

        selected_week_option = st.selectbox("Select Week", options=week_options)

        # Convert selected week option to week index (0-based)
        if selected_week_option == "All Weeks":
            selected_week = None
        else:
            # Extract week number from option (e.g., "Week 2 (8-14)" -> 1)
            selected_week = int(selected_week_option.split()[1]) - 1

        # Shift configuration
        st.subheader("Shift Setup")
        shifts_text = st.text_area("Enter shifts (one per line):", 
                                  "Morning\nAfternoon\nEvening")
        shifts_per_day = [shift.strip() for shift in shifts_text.split('\n') if shift.strip()]

        people_per_shift = st.number_input("People needed per shift:", 
                                         min_value=1, 
                                         max_value=10,
                                         value=1)

    # Employee input section
    st.header("Employee Information")

    # Initialize session state variables
    if 'unavailable_dates' not in st.session_state:
        st.session_state.unavailable_dates = {}  # {employee: [(date, shift), ...]}
    if 'mandatory_dates' not in st.session_state:
        st.session_state.mandatory_dates = {}    # {employee: [(date, shift), ...]}
    if 'temp_employee_name' not in st.session_state:
        st.session_state.temp_employee_name = ""

    # Get shifts from sidebar
    shifts_list = [shift.strip() for shift in shifts_text.split('\n') if shift.strip()]

    # Initialize session state for employee being added
    if 'temp_employee' not in st.session_state:
        st.session_state.temp_employee = {"name": "", "unavailable_dates": [], "mandatory_dates": []}
    
    # Employee Management Section
    st.subheader("Add New Employee")
    
    # Step 1: Employee Name
    st.write("Step 1: Enter Employee Name")
    new_employee_name = st.text_input("Employee Name", key="new_emp_name")
    if new_employee_name:
        st.session_state.temp_employee["name"] = new_employee_name
        
        # Step 2: Unavailable Dates
        st.write("Step 2: Select Unavailable Dates")
        col1, col2 = st.columns(2)
        with col1:
            selected_date = st.date_input(
                "Select date employee CANNOT work:",
                value=date(year, month, 1),
                min_value=date(year, month, 1),
                max_value=date(year, month, calendar.monthrange(year, month)[1]),
                key="unavail_date"
            )
        with col2:
            selected_shifts = st.multiselect(
                "Select shifts employee cannot work:",
                options=shifts_per_day,
                key="unavail_shifts"
            )
            
        if st.button("Add Unavailable Date"):
            for shift in selected_shifts:
                new_entry = (selected_date, shift)
                if new_entry not in st.session_state.temp_employee["unavailable_dates"]:
                    st.session_state.temp_employee["unavailable_dates"].append(new_entry)
                    
        # Display current unavailable dates
        if st.session_state.temp_employee["unavailable_dates"]:
            st.write("Current unavailable dates:")
            for date_obj, shift in sorted(st.session_state.temp_employee["unavailable_dates"]):
                st.write(f"- {date_obj.strftime('%Y-%m-%d')} ({calendar.day_name[date_obj.weekday()]}) - {shift}")
                
        # Step 3: Mandatory Dates
        st.write("Step 3: Select Mandatory Dates")
        col1, col2 = st.columns(2)
        with col1:
            mand_date = st.date_input(
                "Select date employee MUST work:",
                value=date(year, month, 1),
                min_value=date(year, month, 1),
                max_value=date(year, month, calendar.monthrange(year, month)[1]),
                key="mand_date"
            )
        with col2:
            mand_shifts = st.multiselect(
                "Select shifts employee must work:",
                options=shifts_per_day,
                key="mand_shifts"
            )
            
        if st.button("Add Mandatory Date"):
            for shift in mand_shifts:
                new_entry = (mand_date, shift)
                if new_entry not in st.session_state.temp_employee["mandatory_dates"]:
                    st.session_state.temp_employee["mandatory_dates"].append(new_entry)
                    
        # Display current mandatory dates
        if st.session_state.temp_employee["mandatory_dates"]:
            st.write("Current mandatory dates:")
            for date_obj, shift in sorted(st.session_state.temp_employee["mandatory_dates"]):
                st.write(f"- {date_obj.strftime('%Y-%m-%d')} ({calendar.day_name[date_obj.weekday()]}) - {shift}")
                
        # Step 4: Add Employee Button
        if st.button("Add Employee"):
            if new_employee_name:
                employee = Employee(new_employee_name)
                employee.unavailable_dates = st.session_state.temp_employee["unavailable_dates"]
                employee.mandatory_dates = st.session_state.temp_employee["mandatory_dates"]
                
                if not any(e.name == new_employee_name for e in st.session_state.employees):
                    if 'employees' not in st.session_state:
                        st.session_state.employees = []
                    st.session_state.employees.append(employee)
                    st.success(f"Added {new_employee_name} to the employee list.")
                    # Reset temp employee
                    st.session_state.temp_employee = {"name": "", "unavailable_dates": [], "mandatory_dates": []}
                    st.rerun()
                else:
                    st.warning(f"Employee {new_employee_name} already exists!")
    
    st.markdown("---")
    
    # Initialize employees in session state if not present
    if 'employees' not in st.session_state:
        st.session_state.employees = []

    # Display current employees
    if st.session_state.employees:
        st.subheader("Current Employees")
        employee_data = []
        for emp in st.session_state.employees:
            # Format unavailable dates
            unavailable_dates_str = []
            for date_obj, shift in emp.unavailable_dates:
                unavailable_dates_str.append(f"{date_obj.strftime('%Y-%m-%d')} ({shift})")
                
            # Format mandatory dates
            mandatory_dates_str = []
            for date_obj, shift in emp.mandatory_dates:
                mandatory_dates_str.append(f"{date_obj.strftime('%Y-%m-%d')} ({shift})")

            employee_data.append({
                "Name": emp.name,
                "Cannot Work On": ", ".join(unavailable_dates_str) if unavailable_dates_str else "None",
                "Must Work On": ", ".join(mandatory_dates_str) if mandatory_dates_str else "None"
            })

        employee_df = pd.DataFrame(employee_data)
        st.dataframe(employee_df, use_container_width=True, hide_index=True)

    # No additional employee form needed as we have the improved section above

    # Generate schedule button
    if st.session_state.employees and shifts_per_day:
        if st.button("Generate Schedule"):
            if len(st.session_state.employees) < people_per_shift:
                st.error(f"Not enough employees! You need at least {people_per_shift} employees to meet the requirement of {people_per_shift} people per shift.")
            else:
                with st.spinner("Generating schedule..."):
                    # Clone employees to avoid modifying the original list
                    employees_copy = []
                    for emp in st.session_state.employees:
                        # Create a new employee with the same properties
                        new_emp = Employee(emp.name, emp.unavailable_dates.copy(), 
                                          emp.mandatory_dates.copy() if hasattr(emp, 'mandatory_dates') else [])
                        employees_copy.append(new_emp)

                    # Create schedule with the selected week (if any)
                    schedule = create_schedule(
                        employees_copy, 
                        shifts_per_day, 
                        people_per_shift, 
                        month, 
                        year,
                        selected_week
                    )

                    # Store schedule and related info in session state
                    st.session_state.schedule = schedule
                    st.session_state.schedule_month = month
                    st.session_state.schedule_year = year
                    st.session_state.schedule_week = selected_week

                    # Track shift distribution for balance analysis
                    st.session_state.shift_distribution = {}

                    # Count shifts per employee
                    for day, shifts in schedule.items():
                        for shift, emps in shifts.items():
                            if isinstance(emps, list):
                                for emp in emps:
                                    if emp not in st.session_state.shift_distribution:
                                        st.session_state.shift_distribution[emp] = 0
                                    st.session_state.shift_distribution[emp] += 1

    # Display generated schedule
    if 'schedule' in st.session_state:
        display_schedule(
            st.session_state.schedule, 
            st.session_state.schedule_month, 
            st.session_state.schedule_year,
            st.session_state.get('schedule_week')  # Pass the selected week if it exists
        )

        # Option to download the schedule as CSV
        schedule_data = []
        for day in sorted(st.session_state.schedule.keys()):
            day_name = calendar.day_name[calendar.weekday(st.session_state.schedule_year, st.session_state.schedule_month, day)]
            for shift, employees in st.session_state.schedule[day].items():
                employee_names = ', '.join(employees) if isinstance(employees, list) else employees
                schedule_data.append({
                    "Day": day,
                    "Day Name": day_name,
                    "Shift": shift,
                    "Employees": employee_names
                })

        if schedule_data:
            schedule_df = pd.DataFrame(schedule_data)
            csv = schedule_df.to_csv(index=False)
            month_name = calendar.month_name[st.session_state.schedule_month]

            st.download_button(
                label="Download Schedule as CSV",
                data=csv,
                file_name=f"employee_schedule_{month_name}_{st.session_state.schedule_year}.csv",
                mime='text/csv',
            )

        # Display shift distribution analysis
        if hasattr(st.session_state, 'shift_distribution') and st.session_state.shift_distribution:
            st.write("### 📊 Shift Distribution Analysis")
            st.write("This analysis shows how shifts are distributed among employees:")

            # Display shift counts per employee
            shift_data = []
            for emp_name, count in st.session_state.shift_distribution.items():
                if emp_name != "No Available Employee":
                    shift_data.append({"Employee": emp_name, "Number of Shifts": count})

            if shift_data:
                # Sort by shift count
                shift_data.sort(key=lambda x: x["Number of Shifts"], reverse=True)

                # Create DataFrame
                shift_df = pd.DataFrame(shift_data)

                # Calculate statistics
                min_shifts = min(d["Number of Shifts"] for d in shift_data)
                max_shifts = max(d["Number of Shifts"] for d in shift_data)
                avg_shifts = sum(d["Number of Shifts"] for d in shift_data) / len(shift_data)

                # Display summary
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Minimum Shifts", min_shifts)
                with col2:
                    st.metric("Maximum Shifts", max_shifts)
                with col3:
                    st.metric("Average Shifts", f"{avg_shifts:.1f}")

                # Display balance indicator
                if max_shifts - min_shifts <= 1:
                    st.success("✅ Excellent balance! All employees have a similar number of shifts.")
                elif max_shifts - min_shifts <= 2:
                    st.info("ℹ️ Good balance. The difference between most and least shifts is 2 or less.")
                else:
                    st.warning(f"⚠️ There is some imbalance. The difference between most and least shifts is {max_shifts - min_shifts}.")

                # Display the distribution table
                st.dataframe(shift_df, use_container_width=True, hide_index=True)

# Run the app
if __name__ == "__main__":
    main()
