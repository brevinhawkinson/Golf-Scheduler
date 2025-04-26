import streamlit as st
# Set page title and configuration - MUST be the first Streamlit command
st.set_page_config(
   page_title="Employee Scheduler",
   page_icon="📅",
   layout="wide"
)
import random
from collections import defaultdict
import calendar
import pandas as pd
from datetime import datetime, date
import io
import base64
import csv
import json
import os
# Import authentication and database modules
from auth import initialize_auth, auth_page, auth_header, require_login, auth_dialog
from db import (
   save_schedule, get_saved_schedules, get_saved_schedule, update_saved_schedule, delete_saved_schedule,
   get_user_by_id
)
from business import business_page
# Initialize authentication
initialize_auth()
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
           if st.session_state.edited_schedule is not None and st.session_state.edited_schedule != st.session_state.current_schedule:
               st.subheader(f"📅 Modified Schedule for Week {week+1} ({start_day}-{end_day} {month_name} {year})")
           else:
               st.subheader(f"📅 Generated Schedule for Week {week+1} ({start_day}-{end_day} {month_name} {year})")
           # Filter calendar to just show the selected week
           cal = [cal[week]]
   else:
       if st.session_state.edited_schedule is not None and st.session_state.edited_schedule != st.session_state.current_schedule:
           st.subheader(f"📅 Modified Schedule for {month_name} {year}")
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
          
           # Check if this is an edited entry vs. original
           is_edited = False
           if st.session_state.current_schedule and day in st.session_state.current_schedule and shift in st.session_state.current_schedule[day]:
               original_employees = st.session_state.current_schedule[day][shift]
               original_emp_str = ', '.join(original_employees) if isinstance(original_employees, list) else original_employees
               if original_emp_str != employee_names:
                   is_edited = True
          
           df_data.append({
               "Day": f"{day} ({day_name})",
               "Shift": shift,
               "Employees": employee_names,
               "Modified": "✓" if is_edited else ""
           })
  
   if df_data:
       df = pd.DataFrame(df_data)
       st.dataframe(df, use_container_width=True, hide_index=True)
   else:
       st.warning("No schedule generated.")
   # Show shift distribution statistics
   if st.session_state.employees:
       st.write("### Shift Distribution")
       shift_counts = {}
      
       # Count shifts per employee
       for day, shifts in schedule.items():
           for shift, employees in shifts.items():
               if isinstance(employees, list):
                   for emp in employees:
                       if emp in shift_counts:
                           shift_counts[emp] += 1
                       else:
                           shift_counts[emp] = 1
      
       # Create dataframe for visualization
       if shift_counts:
           shift_data = []
           for emp_name, count in shift_counts.items():
               if emp_name != "No Available Employee":
                   shift_data.append({
                       "Employee": emp_name,
                       "Total Shifts": count
                   })
          
           if shift_data:
               shift_df = pd.DataFrame(shift_data)
              
               # Calculate some statistics
               avg_shifts = shift_df["Total Shifts"].mean()
               min_shifts = shift_df["Total Shifts"].min()
               max_shifts = shift_df["Total Shifts"].max()
               range_shifts = max_shifts - min_shifts
              
               # Display statistics
               st.write(f"**Shift Balance Statistics:**")
              
               # Create two columns
               col1, col2 = st.columns(2)
              
               with col1:
                   st.metric("Average Shifts", f"{avg_shifts:.1f}")
                   st.metric("Range (Max-Min)", f"{range_shifts}")
              
               with col2:
                   st.metric("Min Shifts", f"{min_shifts}")
                   st.metric("Max Shifts", f"{max_shifts}")
              
               # Sort by shift count and display
               shift_df = shift_df.sort_values("Total Shifts", ascending=False)
              
               # Show as horizontal bar chart
               st.bar_chart(shift_df.set_index("Employee"))
              
               # Also show as a table
               st.dataframe(shift_df, use_container_width=True, hide_index=True)
def generate_html_calendar(schedule, month, year, employees):
   """Generate an HTML calendar for printing"""
   month_name = calendar.month_name[month]
   cal = calendar.monthcalendar(year, month)
  
   # Start building HTML
   html = f"""
   <!DOCTYPE html>
   <html>
   <head>
       <title>Work Schedule - {month_name} {year}</title>
       <style>
           body {{ font-family: Arial, sans-serif; }}
           table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; }}
           th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
           th {{ background-color: #f2f2f2; }}
           .day-number {{ font-weight: bold; font-size: 14px; }}
           .shift-name {{ font-weight: bold; color: #555; margin-top: 5px; }}
           .employees {{ margin-top: 2px; }}
           .no-day {{ background-color: #f9f9f9; }}
           h1, h2 {{ text-align: center; }}
           .employee-list {{ margin-top: 30px; }}
           @media print {{
               body {{ font-size: 12px; }}
               h1 {{ font-size: 18px; }}
               h2 {{ font-size: 16px; }}
               .pagebreak {{ page-break-before: always; }}
           }}
       </style>
   </head>
   <body>
       <h1>Work Schedule - {month_name} {year}</h1>
      
       <table>
           <tr>
               <th>Sunday</th>
               <th>Monday</th>
               <th>Tuesday</th>
               <th>Wednesday</th>
               <th>Thursday</th>
               <th>Friday</th>
               <th>Saturday</th>
           </tr>
   """
  
   # Add weeks
   for week in cal:
       html += "<tr>"
       for day in week:
           if day == 0:
               html += '<td class="no-day"></td>'
           else:
               html += f'<td><div class="day-number">{day}</div>'
               if day in schedule:
                   for shift, emps in schedule[day].items():
                       html += f'<div class="shift-name">{shift}:</div>'
                       if isinstance(emps, list):
                           html += f'<div class="employees">{", ".join(emps)}</div>'
                       else:
                           html += f'<div class="employees">{emps}</div>'
               html += '</td>'
       html += "</tr>"
  
   html += "</table>"
  
   # Add employee information section
   html += """
       <div class="pagebreak"></div>
       <h2>Employee Information</h2>
       <div class="employee-list">
   """
  
   for emp in employees:
       html += f"""
           <h3>{emp.name}</h3>
           <p><strong>Unavailable Dates:</strong><br>
       """
      
       if emp.unavailable_dates:
           for date_obj, shift in emp.unavailable_dates:
               html += f"{date_obj.strftime('%Y-%m-%d')} - {shift}<br>"
       else:
           html += "None<br>"
      
       html += f"""
           </p>
           <p><strong>Mandatory Dates:</strong><br>
       """
      
       if emp.mandatory_dates:
           for date_obj, shift in emp.mandatory_dates:
               html += f"{date_obj.strftime('%Y-%m-%d')} - {shift}<br>"
       else:
           html += "None<br>"
      
       html += "</p>"
  
   html += """
       </div>
   </body>
   </html>
   """
  
   return html
def main():
   # Initialize auth header (if user is logged in)
   auth_header()
  
   # Check if there's an active auth dialog that needs to be shown
   auth_dialog()
  
   # Initialize tabs
   if st.session_state.logged_in:
       tab1, tab2, tab3, tab4 = st.tabs(["Schedule Generator", "Employee Manager", "Saved Schedules", "Business Account"])
   else:
       tab1, tab2 = st.tabs(["Schedule Generator", "Employee Manager"])
  
   # Tab 1: Schedule Generator
   with tab1:
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
                                            value=2)
       # Initialize session state variables for schedule editing
       if 'current_schedule' not in st.session_state:
           st.session_state.current_schedule = None
       if 'edited_schedule' not in st.session_state:
           st.session_state.edited_schedule = None
      
       # Generate schedule button
       if 'employees' in st.session_state and st.session_state.employees and shifts_per_day:
           # Check if we should generate a new schedule or show the current one
           show_current = False
          
           if st.button("Generate Schedule"):
               if len(st.session_state.employees) < people_per_shift:
                   st.error(f"Not enough employees! You need at least {people_per_shift} employees per shift.")
               else:
                   # Create a fresh copy of employees to work with (so we don't modify the originals)
                   working_employees = []
                   for emp in st.session_state.employees:
                       new_emp = Employee(emp.name)
                       new_emp.unavailable_dates = emp.unavailable_dates.copy()
                       new_emp.mandatory_dates = emp.mandatory_dates.copy()
                       working_employees.append(new_emp)
                  
                   # Generate schedule
                   generated_schedule = create_schedule(
                       employees=working_employees,
                       shifts_per_day=shifts_per_day,
                       people_per_shift=people_per_shift,
                       month=month,
                       year=year,
                       week=selected_week
                   )
                  
                   # Store in session state
                   st.session_state.current_schedule = generated_schedule
                   st.session_state.edited_schedule = None
                  
                   show_current = True
           elif st.session_state.edited_schedule is not None:
               # Use the edited schedule if it exists
               show_current = True
           elif st.session_state.current_schedule is not None:
               # Use the last generated schedule if it exists
               show_current = True
              
           # Display the schedule if we should
           if show_current:
               display_schedule = st.session_state.edited_schedule if st.session_state.edited_schedule is not None else st.session_state.current_schedule
              
               # Display the schedule
               display_schedule(
                   schedule=display_schedule,
                   month=month,
                   year=year,
                   week=selected_week
               )
              
               # Add an edit schedule section
               st.markdown("---")
               st.subheader("Edit Schedule")
               st.write("Make adjustments to the generated schedule:")
              
               edit_day = st.number_input("Day", min_value=1, max_value=calendar.monthrange(year, month)[1], value=1)
               edit_shift = st.selectbox("Shift", options=shifts_per_day)
              
               # Get current employees for this shift
               current_emps = []
               if st.session_state.edited_schedule is not None:
                   schedule_to_edit = st.session_state.edited_schedule
               else:
                   schedule_to_edit = st.session_state.current_schedule.copy()
              
               if edit_day in schedule_to_edit and edit_shift in schedule_to_edit[edit_day]:
                   current_emps = schedule_to_edit[edit_day][edit_shift]
                   if isinstance(current_emps, str):
                       current_emps = [current_emps]
              
               # Choose new employees
               new_emps = st.multiselect(
                   "Select Employees",
                   options=[emp.name for emp in st.session_state.employees],
                   default=current_emps
               )
              
               if st.button("Update Schedule"):
                   # If we haven't created an edited schedule yet, create one as a copy
                   if st.session_state.edited_schedule is None:
                       # Deep copy the current schedule
                       edited_schedule = defaultdict(dict)
                       for day, shifts in st.session_state.current_schedule.items():
                           edited_schedule[day] = {}
                           for shift, emps in shifts.items():
                               if isinstance(emps, list):
                                   edited_schedule[day][shift] = emps.copy()
                               else:
                                   edited_schedule[day][shift] = emps
                      
                       st.session_state.edited_schedule = edited_schedule
                  
                   # Update the edited schedule
                   if not new_emps:
                       st.session_state.edited_schedule[edit_day][edit_shift] = ["No Available Employee"]
                   else:
                       st.session_state.edited_schedule[edit_day][edit_shift] = new_emps
                  
                   st.success(f"Updated {edit_shift} shift on day {edit_day}.")
                   st.rerun()
              
               # Add a reset button
               if st.session_state.edited_schedule is not None:
                   if st.button("Reset to Generated Schedule"):
                       st.session_state.edited_schedule = None
                       st.success("Reset to the originally generated schedule.")
                       st.rerun()
              
               # Add export options
               st.markdown("---")
               st.subheader("Export Schedule")
              
               # Choose the schedule to export
               export_schedule = st.session_state.edited_schedule if st.session_state.edited_schedule is not None else st.session_state.current_schedule
              
               # CSV Export
               export_data = []
               for day, shifts in export_schedule.items():
                   for shift, employees in shifts.items():
                       day_name = calendar.day_name[calendar.weekday(year, month, day)]
                       employee_names = ', '.join(employees) if isinstance(employees, list) else employees
                       export_data.append({
                           'Date': f"{year}-{month:02d}-{day:02d}",
                           'Day': day_name,
                           'Shift': shift,
                           'Employees': employee_names
                       })
              
               export_df = pd.DataFrame(export_data)
               csv = export_df.to_csv(index=False)
              
               col1, col2 = st.columns(2)
              
               with col1:
                   st.download_button(
                       label="Download CSV",
                       data=csv,
                       file_name=f"schedule_{month}_{year}.csv",
                       mime="text/csv"
                   )
              
               with col2:
                   # HTML Calendar export
                   html_calendar = generate_html_calendar(
                       schedule=export_schedule,
                       month=month,
                       year=year,
                       employees=st.session_state.employees
                   )
                  
                   st.download_button(
                       label="Download HTML Calendar",
                       data=html_calendar,
                       file_name=f"calendar_{month}_{year}.html",
                       mime="text/html"
                   )
              
               # Save schedule option (for logged in users)
               if st.session_state.logged_in:
                   st.markdown("---")
                   st.subheader("Save Schedule")
                  
                   with st.form("save_schedule_form"):
                       schedule_name = st.text_input("Schedule Name", value=f"{calendar.month_name[month]} {year} Schedule")
                       schedule_description = st.text_area("Description (optional)",
                                                         placeholder="Enter a description for this schedule...")
                      
                       submit = st.form_submit_button("Save to Account")
                      
                       if submit:
                           if not schedule_name:
                               st.error("Please enter a name for the schedule")
                           else:
                               # Prepare employee data for saving
                               employee_data = []
                               for emp in st.session_state.employees:
                                   emp_data = {
                                       'name': emp.name,
                                       'unavailable_dates': [
                                           {'date': d.strftime('%Y-%m-%d'), 'shift': s}
                                           for d, s in emp.unavailable_dates
                                       ],
                                       'mandatory_dates': [
                                           {'date': d.strftime('%Y-%m-%d'), 'shift': s}
                                           for d, s in emp.mandatory_dates
                                       ]
                                   }
                                   employee_data.append(emp_data)
                              
                               # Save to the database
                               success, message = save_schedule(
                                   user_id=st.session_state.user_id,
                                   name=schedule_name,
                                   description=schedule_description,
                                   month=month,
                                   year=year,
                                   schedule=export_schedule,
                                   employees=employee_data
                               )
                              
                               if success:
                                   st.success(f"Schedule '{schedule_name}' saved successfully!")
                               else:
                                   st.error(f"Error saving schedule: {message}")
      
       else:
           st.info("Add employees in the Employee Manager tab to generate a schedule.")
   # Tab 2: Employee Management
   with tab2:
       st.title("Employee Management")
      
       # Initialize session state variables
       if 'employees' not in st.session_state:
           st.session_state.employees = []
       if 'unavailable_dates' not in st.session_state:
           st.session_state.unavailable_dates = {}  # {employee: [(date, shift), ...]}
       if 'mandatory_dates' not in st.session_state:
           st.session_state.mandatory_dates = {}    # {employee: [(date, shift), ...]}
       if 'temp_employee' not in st.session_state:
           st.session_state.temp_employee = {"name": "", "unavailable_dates": [], "mandatory_dates": []}
      
       # Get shifts from sidebar for use in employee management
       shifts_list = [shift.strip() for shift in shifts_text.split('\n') if shift.strip()]
      
       # Employee Management Section
       st.subheader("Add New Employee")
      
       # Create a 3-column card layout for employees
       if st.session_state.employees:
           st.subheader("Current Employees")
          
           # Calculate how many complete rows we need
           num_employees = len(st.session_state.employees)
           employees_per_row = 3
           num_rows = (num_employees + employees_per_row - 1) // employees_per_row
          
           for row in range(num_rows):
               cols = st.columns(employees_per_row)
               for col_idx in range(employees_per_row):
                   emp_idx = row * employees_per_row + col_idx
                   if emp_idx < num_employees:
                       emp = st.session_state.employees[emp_idx]
                       with cols[col_idx]:
                           with st.container(border=True):
                               st.subheader(emp.name)
                              
                               # Unavailable dates
                               with st.expander("Cannot Work On"):
                                   if emp.unavailable_dates:
                                       for date_obj, shift in sorted(emp.unavailable_dates):
                                           day_name = calendar.day_name[date_obj.weekday()]
                                           st.write(f"- {date_obj.strftime('%Y-%m-%d')} ({day_name}) - {shift}")
                                          
                                           # Add button to remove this unavailability
                                           if st.button("Remove", key=f"remove_unavail_{emp.name}_{date_obj}_{shift}"):
                                               emp.unavailable_dates.remove((date_obj, shift))
                                               st.success(f"Removed unavailable date for {emp.name}")
                                               st.rerun()
                                   else:
                                       st.write("No unavailable dates set")
                                  
                                   # Add a new unavailable date
                                   with st.form(key=f"add_unavail_{emp.name}"):
                                       st.write("Add new unavailable date:")
                                       unavail_date = st.date_input(
                                           "Date:",
                                           value=date(year, month, 1),
                                           key=f"unavail_date_{emp.name}"
                                       )
                                       unavail_shift = st.selectbox(
                                           "Shift:",
                                           options=shifts_list,
                                           key=f"unavail_shift_{emp.name}"
                                       )
                                       if st.form_submit_button("Add"):
                                           date_shift = (unavail_date, unavail_shift)
                                           if date_shift not in emp.unavailable_dates:
                                               emp.unavailable_dates.append(date_shift)
                                               st.success(f"Added unavailable date for {emp.name}")
                                               st.rerun()
                                           else:
                                               st.error("This date and shift is already marked as unavailable")
                              
                               # Mandatory dates
                               with st.expander("Must Work On"):
                                   if emp.mandatory_dates:
                                       for date_obj, shift in sorted(emp.mandatory_dates):
                                           day_name = calendar.day_name[date_obj.weekday()]
                                           st.write(f"- {date_obj.strftime('%Y-%m-%d')} ({day_name}) - {shift}")
                                          
                                           # Add button to remove this mandatory date
                                           if st.button("Remove", key=f"remove_mand_{emp.name}_{date_obj}_{shift}"):
                                               emp.mandatory_dates.remove((date_obj, shift))
                                               st.success(f"Removed mandatory date for {emp.name}")
                                               st.rerun()
                                   else:
                                       st.write("No mandatory dates set")
                                  
                                   # Add a new mandatory date
                                   with st.form(key=f"add_mand_{emp.name}"):
                                       st.write("Add new mandatory date:")
                                       mand_date = st.date_input(
                                           "Date:",
                                           value=date(year, month, 1),
                                           key=f"mand_date_{emp.name}"
                                       )
                                       mand_shift = st.selectbox(
                                           "Shift:",
                                           options=shifts_list,
                                           key=f"mand_shift_{emp.name}"
                                       )
                                       if st.form_submit_button("Add"):
                                           date_shift = (mand_date, mand_shift)
                                           if date_shift not in emp.mandatory_dates:
                                               emp.mandatory_dates.append(date_shift)
                                               st.success(f"Added mandatory date for {emp.name}")
                                               st.rerun()
                                           else:
                                               st.error("This date and shift is already marked as mandatory")
                              
                               # Delete employee button
                               if st.button("🗑️ Delete Employee", key=f"delete_{emp.name}"):
                                   st.session_state.employees.remove(emp)
                                   st.success(f"Deleted employee {emp.name}")
                                   st.rerun()
      
       # Form to add a new employee
       with st.form("add_employee_form"):
           st.write("Enter employee details:")
           new_employee_name = st.text_input("Employee Name")
          
           submitted = st.form_submit_button("Add Employee")
          
           if submitted:
               if not new_employee_name:
                   st.error("Please enter an employee name")
               elif any(e.name == new_employee_name for e in st.session_state.employees):
                   st.error(f"Employee {new_employee_name} already exists!")
               else:
                   # Create new employee
                   new_employee = Employee(new_employee_name)
                   st.session_state.employees.append(new_employee)
                   st.success(f"Added {new_employee_name} to the employee list")
                   st.rerun()
      
       # Bulk import/export section
       st.markdown("---")
       with st.expander("Bulk Import/Export"):
           # Export employees to CSV
           if st.session_state.employees:
               st.subheader("Export Employees")
              
               # Prepare data for export
               export_data = []
               for emp in st.session_state.employees:
                   # Format unavailable dates
                   unavailable_dates = []
                   for date_obj, shift in emp.unavailable_dates:
                       unavailable_dates.append(f"{date_obj.strftime('%Y-%m-%d')}|{shift}")
                  
                   # Format mandatory dates
                   mandatory_dates = []
                   for date_obj, shift in emp.mandatory_dates:
                       mandatory_dates.append(f"{date_obj.strftime('%Y-%m-%d')}|{shift}")
                  
                   export_data.append({
                       "Name": emp.name,
                       "Unavailable Dates": ";".join(unavailable_dates),
                       "Mandatory Dates": ";".join(mandatory_dates)
                   })
              
               export_df = pd.DataFrame(export_data)
               csv = export_df.to_csv(index=False)
              
               st.download_button(
                   label="Export Employees CSV",
                   data=csv,
                   file_name="employees.csv",
                   mime="text/csv"
               )
          
           # Import employees from CSV
           st.subheader("Import Employees")
          
           uploaded_file = st.file_uploader("Upload CSV file", type="csv")
          
           if uploaded_file is not None:
               try:
                   import_df = pd.read_csv(uploaded_file)
                  
                   if 'Name' not in import_df.columns:
                       st.error("CSV file must contain a 'Name' column")
                   else:
                       if st.button("Import Employees"):
                           # Process each row
                           imported_count = 0
                           for _, row in import_df.iterrows():
                               emp_name = row['Name']
                              
                               # Skip if employee already exists
                               if any(e.name == emp_name for e in st.session_state.employees):
                                   continue
                              
                               # Create new employee
                               new_emp = Employee(emp_name)
                              
                               # Process unavailable dates
                               if 'Unavailable Dates' in row and pd.notna(row['Unavailable Dates']):
                                   unavail_str = row['Unavailable Dates']
                                   if unavail_str:
                                       for date_shift in unavail_str.split(';'):
                                           if '|' in date_shift:
                                               date_str, shift = date_shift.split('|')
                                               try:
                                                   date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                                                   new_emp.unavailable_dates.append((date_obj, shift))
                                               except:
                                                   pass
                              
                               # Process mandatory dates
                               if 'Mandatory Dates' in row and pd.notna(row['Mandatory Dates']):
                                   mand_str = row['Mandatory Dates']
                                   if mand_str:
                                       for date_shift in mand_str.split(';'):
                                           if '|' in date_shift:
                                               date_str, shift = date_shift.split('|')
                                               try:
                                                   date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                                                   new_emp.mandatory_dates.append((date_obj, shift))
                                               except:
                                                   pass
                              
                               # Add to session state
                               st.session_state.employees.append(new_emp)
                               imported_count += 1
                          
                           st.success(f"Imported {imported_count} new employees")
                           st.rerun()
              
               except Exception as e:
                   st.error(f"Error importing CSV: {str(e)}")
  
   # Saved Schedules Tab (only for logged in users)
   if st.session_state.logged_in and 'tab3' in locals():
       with tab3:
           st.title("Saved Schedules")
          
           # Get user's saved schedules
           saved_schedules = get_saved_schedules(st.session_state.user_id)
          
           if not saved_schedules:
               st.info("You don't have any saved schedules. Create a schedule in the Schedule Generator tab and save it to see it here.")
           else:
               st.write(f"You have {len(saved_schedules)} saved schedule(s).")
              
               for schedule in saved_schedules:
                   with st.container(border=True):
                       # Display schedule info
                       st.subheader(schedule.name)
                      
                       # Format month/year for display
                       month_name = calendar.month_name[schedule.month]
                      
                       col1, col2, col3 = st.columns([3, 2, 1])
                      
                       with col1:
                           st.write(f"**Period:** {month_name} {schedule.year}")
                           if schedule.description:
                               st.write(f"**Description:** {schedule.description}")
                           st.write(f"**Created:** {schedule.created_at.strftime('%Y-%m-%d')}")
                      
                       with col2:
                           # Load the schedule button
                           if st.button("Load Schedule", key=f"load_{schedule.id}"):
                               # Get the full schedule details
                               loaded_schedule = get_saved_schedule(schedule.id, st.session_state.user_id)
                              
                               if loaded_schedule:
                                   # Convert the schedule
                                   schedule_data = loaded_schedule.get_schedule()
                                  
                                   # Convert string day keys to integers
                                   formatted_schedule = defaultdict(dict)
                                   for day_str, shifts in schedule_data.items():
                                       day = int(day_str)
                                       formatted_schedule[day] = shifts
                                  
                                   # Convert the employees
                                   employee_data = loaded_schedule.get_employees()
                                   employees = []
                                  
                                   for emp_data in employee_data:
                                       emp = Employee(emp_data['name'])
                                      
                                       # Convert unavailable dates from string to date objects
                                       for date_info in emp_data.get('unavailable_dates', []):
                                           date_obj = datetime.strptime(date_info['date'], '%Y-%m-%d').date()
                                           shift = date_info['shift']
                                           emp.unavailable_dates.append((date_obj, shift))
                                      
                                       # Convert mandatory dates from string to date objects
                                       for date_info in emp_data.get('mandatory_dates', []):
                                           date_obj = datetime.strptime(date_info['date'], '%Y-%m-%d').date()
                                           shift = date_info['shift']
                                           emp.mandatory_dates.append((date_obj, shift))
                                      
                                       employees.append(emp)
                                  
                                   # Update session state
                                   st.session_state.employees = employees
                                   st.session_state.current_schedule = formatted_schedule
                                   st.session_state.edited_schedule = None
                                  
                                   # Set message and redirect
                                   st.success(f"Loaded schedule '{schedule.name}'")
                                   st.rerun()
                               else:
                                   st.error("Error loading schedule.")
                          
                           # Export options
                           if st.button("Export Options", key=f"export_{schedule.id}"):
                               # Get the full schedule details
                               export_schedule = get_saved_schedule(schedule.id, st.session_state.user_id)
                              
                               if export_schedule:
                                   # Convert the schedule
                                   schedule_data = export_schedule.get_schedule()
                                  
                                   # Convert string day keys to integers
                                   formatted_schedule = defaultdict(dict)
                                   for day_str, shifts in schedule_data.items():
                                       day = int(day_str)
                                       formatted_schedule[day] = shifts
                                  
                                   # Prepare export data
                                   export_data = []
                                   for day, shifts in formatted_schedule.items():
                                       for shift, employees in shifts.items():
                                           day_name = calendar.day_name[calendar.weekday(export_schedule.year, export_schedule.month, day)]
                                           employee_names = ', '.join(employees) if isinstance(employees, list) else employees
                                           export_data.append({
                                               'Date': f"{export_schedule.year}-{export_schedule.month:02d}-{day:02d}",
                                               'Day': day_name,
                                               'Shift': shift,
                                               'Employees': employee_names
                                           })
                              
                               export_df = pd.DataFrame(export_data)
                               csv = export_df.to_csv(index=False)
                               st.download_button(
                                   label="Download",
                                   data=csv,
                                   file_name=f"{schedule.name.replace(' ', '_')}_{month}_{year}.csv",
                                   mime="text/csv",
                                   key=f"dl_{schedule.id}"
                               )
                      
                       with col3:
                           if st.button("Delete", key=f"delete_{schedule.id}"):
                               success, message = delete_saved_schedule(schedule.id, st.session_state.user_id)
                               if success:
                                   st.success(f"Schedule '{schedule.name}' deleted.")
                                   st.rerun()
                               else:
                                   st.error(f"Error deleting schedule: {message}")
                      
           # Add information about session persistence
           st.sidebar.markdown("---")
           st.sidebar.write("### About This App")
           with st.sidebar.expander("Session Information"):
               if st.session_state.logged_in:
                   st.write("""
                   **You are logged in. Your data can be saved to your account.**
                  
                   - Save schedules to your account for permanent storage
                   - Access your saved schedules from any device
                   - Use the "Saved Schedules" tab to manage your schedules
                   """)
               else:
                   st.write("""
                   **You're using a temporary session.**
                  
                   - All data is stored temporarily in your browser
                   - Data is lost when you close your browser
                   - Log in or create an account to save your schedules permanently
                   """)
  
   # Business Account Tab (if it exists)
   if st.session_state.logged_in and 'tab4' in locals():
       with tab4:
           # Display business account management interface
           business_page()
if __name__ == "__main__":
   main()
auth.py
import streamlit as st
import hashlib
import os
import string
import random
import json
from datetime import datetime, timedelta
from streamlit_cookies_manager import CookieManager
# Import database functions
from db import create_user, authenticate_user, get_user_by_id
def initialize_auth():
   """Initialize authentication-related session state variables"""
   # Initialize cookie manager
   if 'cookies' not in st.session_state:
       st.session_state.cookies = CookieManager()
  
   # Check if user is already logged in via session state
   if 'logged_in' not in st.session_state:
       st.session_state.logged_in = False
  
   if 'user_id' not in st.session_state:
       st.session_state.user_id = None
  
   if 'username' not in st.session_state:
       st.session_state.username = None
  
   # Check authentication status from cookies
   if not st.session_state.logged_in and st.session_state.cookies.ready():
       # Try to get auth cookie
       auth_cookie = st.session_state.cookies.get('auth_token')
       if auth_cookie:
           # Validate the auth token
           try:
               auth_data = json.loads(auth_cookie)
               if 'user_id' in auth_data and 'expiry' in auth_data:
                   # Check if token is still valid
                   expiry = datetime.fromisoformat(auth_data['expiry'])
                   if expiry > datetime.now():
                       # Token is valid, log user in
                       user = get_user_by_id(auth_data['user_id'])
                       if user:
                           st.session_state.logged_in = True
                           st.session_state.user_id = user.id
                           st.session_state.username = user.username
           except:
               # If any error, clear the cookie
               st.session_state.cookies.set('auth_token', '', expires_at=datetime.now())
  
   # Variables for showing login/signup forms
   if 'show_auth_dialog' not in st.session_state:
       st.session_state.show_auth_dialog = False
  
   if 'auth_dialog_mode' not in st.session_state:
       st.session_state.auth_dialog_mode = "login"  # or "signup"
def signup_page():
   """Display the signup form and handle user registration"""
   st.subheader("Create an Account")
  
   with st.form("signup_form"):
       username = st.text_input("Username", key="signup_username")
       email = st.text_input("Email", key="signup_email")
       password = st.text_input("Password", type="password", key="signup_password")
       confirm_password = st.text_input("Confirm Password", type="password", key="signup_confirm")
      
       submitted = st.form_submit_button("Sign Up")
      
       if submitted:
           # Validate form
           if not username or not email or not password:
               st.error("All fields are required")
           elif password != confirm_password:
               st.error("Passwords do not match")
           elif len(password) < 8:
               st.error("Password must be at least 8 characters long")
           elif '@' not in email or '.' not in email:
               st.error("Please enter a valid email address")
           else:
               # Try to create user
               success, user_id = create_user(username, email, password)
              
               if success:
                   # User created successfully
                   st.success("Account created successfully! You can now log in.")
                  
                   # Automatically log user in
                   st.session_state.logged_in = True
                   st.session_state.user_id = user_id
                   st.session_state.username = username
                  
                   # Set auth cookie
                   expiry = datetime.now() + timedelta(days=30)
                   auth_data = {
                       'user_id': user_id,
                       'expiry': expiry.isoformat()
                   }
                   st.session_state.cookies.set('auth_token', json.dumps(auth_data), expires_at=expiry)
                  
                   # Close dialog and reload page
                   st.session_state.show_auth_dialog = False
                   st.rerun()
               else:
                   # Error creating user
                   st.error(f"Error creating account: {user_id}")
def login_page():
   """Display the login form and handle user authentication"""
   st.subheader("Log In")
  
   with st.form("login_form"):
       username = st.text_input("Username", key="login_username")
       password = st.text_input("Password", type="password", key="login_password")
       remember_me = st.checkbox("Remember me", value=True)
      
       submitted = st.form_submit_button("Log In")
      
       if submitted:
           if not username or not password:
               st.error("Please enter both username and password")
           else:
               # Try to authenticate
               user = authenticate_user(username, password)
              
               if user:
                   # Authentication successful
                   st.success("Logged in successfully!")
                  
                   # Set session state
                   st.session_state.logged_in = True
                   st.session_state.user_id = user.id
                   st.session_state.username = user.username
                  
                   # Set auth cookie if remember me is checked
                   if remember_me:
                       expiry = datetime.now() + timedelta(days=30)
                   else:
                       expiry = datetime.now() + timedelta(hours=1)
                  
                   auth_data = {
                       'user_id': user.id,
                       'expiry': expiry.isoformat()
                   }
                   st.session_state.cookies.set('auth_token', json.dumps(auth_data), expires_at=expiry)
                  
                   # Close dialog and reload page
                   st.session_state.show_auth_dialog = False
                   st.rerun()
               else:
                   # Authentication failed
                   st.error("Invalid username or password")
def logout():
   """Log the user out by clearing session state and cookies"""
   # Clear session state
   st.session_state.logged_in = False
   st.session_state.user_id = None
   st.session_state.username = None
  
   # Clear cookie
   if st.session_state.cookies.ready():
       st.session_state.cookies.set('auth_token', '', expires_at=datetime.now())
  
   # Reload page
   st.rerun()
def auth_header():
   """Display a header with user info and logout button if logged in"""
   # Create a container for the header
   with st.container():
       cols = st.columns([1, 8, 1])
      
       # App name/logo on the left
       with cols[0]:
           st.write("")  # Empty for now
      
       # Title in the middle (empty for now, as the main title is in the app)
       with cols[1]:
           st.write("")
      
       # User info and login/logout on the right
       with cols[2]:
           if st.session_state.logged_in:
               # Show username and logout option
               st.write(f"👤 **{st.session_state.username}**")
               if st.button("Logout"):
                   logout()
           else:
               # Show login button
               if st.button("Login"):
                   # Set state to show login dialog
                   st.session_state.show_auth_dialog = True
                   st.session_state.auth_dialog_mode = "login"
                   st.rerun()
def auth_dialog():
   """Show authentication dialog when login icon is clicked"""
   if st.session_state.show_auth_dialog:
       # Create a modal-like dialog
       with st.sidebar:
           st.markdown("## Account")
          
           # Close button
           if st.button("×", help="Close"):
               st.session_state.show_auth_dialog = False
               st.rerun()
          
           # Tabs for login/signup
           login_tab, signup_tab = st.tabs(["Login", "Sign Up"])
          
           with login_tab:
               login_page()
          
           with signup_tab:
               signup_page()
def require_login():
   """Check if user is logged in, if not redirect to login page"""
   if not st.session_state.logged_in:
       st.warning("You need to log in to access this feature")
       st.session_state.show_auth_dialog = True
       st.session_state.auth_dialog_mode = "login"
       st.rerun()
       return False
   return True
def auth_page():
   """Main authentication page that handles login/signup forms"""
   # Set up the page
   st.title("Account Authentication")
  
   # Display tabs for login and signup
   login_tab, signup_tab = st.tabs(["Login", "Create Account"])
  
   with login_tab:
       login_page()
  
   with signup_tab:
       signup_page()
db.py (Part 1/2)
import streamlit as st
import sqlalchemy as sa
from sqlalchemy import (
   create_engine, Column, Integer, String, DateTime,
   ForeignKey, Text, Boolean, func
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import os
import json
import uuid
import hashlib
import secrets
import string
import random
# Get database URL from environment or use default SQLite
DATABASE_URL = os.environ.get('DATABASE_URL')
# Create database engine
engine = create_engine(DATABASE_URL)
# Create declarative base
Base = sa.orm.declarative_base()
# Define database models
class Organization(Base):
   __tablename__ = 'organizations'
  
   id = Column(Integer, primary_key=True)
   name = Column(String(100), nullable=False)
   description = Column(Text, nullable=True)
   invite_code = Column(String(32), unique=True, nullable=False)
   created_at = Column(DateTime, default=func.now())
  
   # Relationships
   users = relationship("User", back_populates="organization")
  
   def __repr__(self):
       return f"<Organization {self.name}>"
class User(Base):
   __tablename__ = 'users'
  
   id = Column(Integer, primary_key=True)
   username = Column(String(50), unique=True, nullable=False)
   email = Column(String(100), unique=True, nullable=False)
   password_hash = Column(String(128), nullable=False)
   salt = Column(String(128), nullable=False)
   created_at = Column(DateTime, default=func.now())
  
   # Role: 'admin', 'manager', 'employee'
   role = Column(String(20), default="employee")
  
   # Optional organization relationship
   organization_id = Column(Integer, ForeignKey('organizations.id'), nullable=True)
   organization = relationship("Organization", back_populates="users")
  
   # Relationships
   saved_schedules = relationship("SavedSchedule", back_populates="user", cascade="all, delete-orphan")
   time_off_requests = relationship("TimeOffRequest", back_populates="user", cascade="all, delete-orphan")
  
   @staticmethod
   def hash_password(password, salt=None):
       """Hash a password with a salt, or generate a new salt if none is provided"""
       if salt is None:
           # Generate a new salt
           salt = secrets.token_hex(32)
      
       # Hash the password with the salt
       hash_obj = hashlib.sha256((password + salt).encode('utf-8'))
       password_hash = hash_obj.hexdigest()
      
       return password_hash, salt
  
   def verify_password(self, password):
       """Verify a password against the stored hash"""
       hash_obj = hashlib.sha256((password + self.salt).encode('utf-8'))
       password_hash = hash_obj.hexdigest()
       return password_hash == self.password_hash
  
   def is_admin(self):
       """Check if user is an organization admin"""
       return self.role == "admin"
  
   def is_manager(self):
       """Check if user is a manager"""
       return self.role in ["admin", "manager"]
  
   def is_employee(self):
       """Check if user is an employee (or higher)"""
       return self.role in ["admin", "manager", "employee"]
  
   def __repr__(self):
       return f"<User {self.username}>"
class TimeOffRequest(Base):
   __tablename__ = 'time_off_requests'
  
   id = Column(Integer, primary_key=True)
   user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
   start_date = Column(DateTime, nullable=False)
   end_date = Column(DateTime, nullable=False)
   reason = Column(Text, nullable=True)
   status = Column(String(20), default="pending")  # pending, approved, rejected
   created_at = Column(DateTime, default=func.now())
   updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
  
   # Relationships
   user = relationship("User", back_populates="time_off_requests")
  
   def __repr__(self):
       return f"<TimeOffRequest {self.id} by {self.user_id}>"
class SavedSchedule(Base):
   __tablename__ = 'saved_schedules'
  
   id = Column(Integer, primary_key=True)
   user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
   name = Column(String(100), nullable=False)
   description = Column(Text, nullable=True)
   month = Column(Integer, nullable=False)
   year = Column(Integer, nullable=False)
   schedule_data = Column(Text, nullable=False)  # JSON serialized schedule
   employees_data = Column(Text, nullable=False)  # JSON serialized employees
   created_at = Column(DateTime, default=func.now())
   updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
  
   # Relationships
   user = relationship("User", back_populates="saved_schedules")
  
   def __repr__(self):
       return f"<SavedSchedule {self.name} by {self.user_id}>"
  
   def get_schedule(self):
       """Convert JSON schedule_data to Python dictionary"""
       return json.loads(self.schedule_data)
  
   def set_schedule(self, schedule):
       """Convert Python dictionary to JSON for storage"""
       self.schedule_data = json.dumps(schedule)
  
   def get_employees(self):
       """Convert JSON employees_data to Python list"""
       return json.loads(self.employees_data)
  
   def set_employees(self, employees):
       """Convert Python list to JSON for storage"""
       self.employees_data = json.dumps(employees)
# Create tables
Base.metadata.create_all(engine)
# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
def get_db_session():
   """Create and return a new database session"""
   return SessionLocal()
def create_user(username, email, password):
   """Create a new user account"""
   session = get_db_session()
   try:
       # Check if username already exists
       if session.query(User).filter(User.username == username).first():
           return False, "Username already exists"
      
       # Check if email already exists
       if session.query(User).filter(User.email == email).first():
           return False, "Email already exists"
      
       # Hash the password
       password_hash, salt = User.hash_password(password)
      
       # Create the user
       new_user = User(
           username=username,
           email=email,
           password_hash=password_hash,
           salt=salt
       )
      
       session.add(new_user)
       session.commit()
       session.refresh(new_user)
      
       return True, new_user.id
   except Exception as e:
       session.rollback()
       return False, str(e)
   finally:
       session.close()
def authenticate_user(username, password):
   """Authenticate a user by username and password"""
   session = get_db_session()
   try:
       # Find user by username
       user = session.query(User).filter(User.username == username).first()
      
       if user and user.verify_password(password):
           return user
       return None
   except Exception as e:
       return None
   finally:
       session.close()
def get_user_by_id(user_id):
   """Get user information by ID"""
   session = get_db_session()
   try:
       return session.query(User).filter(User.id == user_id).first()
   except Exception as e:
       return None
   finally:
       session.close()
def save_schedule(user_id, name, description, month, year, schedule, employees):
   """Save a schedule to the database"""
   session = get_db_session()
   try:
       # Convert schedule data to appropriate format for storage
       # Need to convert defaultdict and day numbers to string keys for JSON serialization
       schedule_data = {}
       for day, shifts in schedule.items():
           schedule_data[str(day)] = shifts
      
       # Create new saved schedule
       new_schedule = SavedSchedule(
           user_id=user_id,
           name=name,
           description=description,
           month=month,
           year=year
       )
      
       # Set serialized data
       new_schedule.set_schedule(schedule_data)
       new_schedule.set_employees(employees)
      
       session.add(new_schedule)
       session.commit()
      
       return True, "Schedule saved successfully"
   except Exception as e:
       session.rollback()
       return False, str(e)
   finally:
       session.close()
def get_saved_schedules(user_id):
   """Get all saved schedules for a user"""
   session = get_db_session()
   try:
       return session.query(SavedSchedule).filter(SavedSchedule.user_id == user_id).order_by(SavedSchedule.created_at.desc()).all()
   except Exception as e:
       return []
   finally:
       session.close()
def get_saved_schedule(schedule_id, user_id=None):
   """Get a specific saved schedule"""
   session = get_db_session()
   try:
       query = session.query(SavedSchedule).filter(SavedSchedule.id == schedule_id)
      
       # If user_id is provided, ensure the schedule belongs to this user
       if user_id:
           query = query.filter(SavedSchedule.user_id == user_id)
      
       return query.first()
   except Exception as e:
       return None
   finally:
       session.close()
def update_saved_schedule(schedule_id, user_id, name=None, description=None,
                         month=None, year=None, schedule=None, employees=None):
   """Update an existing saved schedule"""
   session = get_db_session()
   try:
       # Get the schedule
       saved_schedule = session.query(SavedSchedule).filter(
           SavedSchedule.id == schedule_id,
           SavedSchedule.user_id == user_id
       ).first()
      
       if not saved_schedule:
           return False, "Schedule not found or access denied"
      
       # Update fields if provided
       if name:
           saved_schedule.name = name
      
       if description is not None:  # Allow empty description
           saved_schedule.description = description
      
       if month:
           saved_schedule.month = month
      
       if year:
           saved_schedule.year = year
      
       if schedule:
           # Convert schedule data for storage
           schedule_data = {}
           for day, shifts in schedule.items():
               schedule_data[str(day)] = shifts
          
           saved_schedule.set_schedule(schedule_data)
      
       if employees:
           saved_schedule.set_employees(employees)
      
       session.commit()
      
       return True, "Schedule updated successfully"
   except Exception as e:
       session.rollback()
       return False, str(e)
   finally:
       session.close()
def delete_saved_schedule(schedule_id, user_id):
   """Delete a saved schedule"""
   session = get_db_session()
   try:
       # Get the schedule
       saved_schedule = session.query(SavedSchedule).filter(
           SavedSchedule.id == schedule_id,
           SavedSchedule.user_id == user_id
       ).first()
      
       if not saved_schedule:
           return False, "Schedule not found or access denied"
      
       # Delete the schedule
       session.delete(saved_schedule)
       session.commit()
      
       return True, "Schedule deleted successfully"
   except Exception as e:
       session.rollback()
       return False, str(e)
   finally:
       session.close()
db.py (Part 2/2)
def create_organization(name, description=None, admin_user_id=None):
   """Create a new organization"""
   session = get_db_session()
   try:
       # Generate a unique invite code
       invite_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
      
       # Ensure invite code is unique
       while session.query(Organization).filter(Organization.invite_code == invite_code).first():
           invite_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
      
       # Create organization
       org = Organization(
           name=name,
           description=description,
           invite_code=invite_code
       )
      
       session.add(org)
       session.flush()  # Get the ID without committing
      
       # If an admin user is provided, update their role and organization
       if admin_user_id:
           admin_user = session.query(User).filter(User.id == admin_user_id).first()
           if admin_user:
               admin_user.organization_id = org.id
               admin_user.role = "admin"
      
       session.commit()
      
       return True, org.id, invite_code
   except Exception as e:
       session.rollback()
       return False, str(e), None
   finally:
       session.close()
def get_organization(org_id=None, invite_code=None):
   """Get organization details by ID or invite code"""
   session = get_db_session()
   try:
       query = session.query(Organization)
      
       if org_id:
           query = query.filter(Organization.id == org_id)
       elif invite_code:
           query = query.filter(Organization.invite_code == invite_code)
       else:
           return None  # Either org_id or invite_code must be provided
      
       return query.first()
   except Exception as e:
       return None
   finally:
       session.close()
def join_organization_by_invite(user_id, invite_code, role="employee"):
   """Join an organization using an invite code"""
   session = get_db_session()
   try:
       # Find the organization by invite code
       org = session.query(Organization).filter(Organization.invite_code == invite_code).first()
       if not org:
           return False, "Invalid invitation code"
      
       # Find the user
       user = session.query(User).filter(User.id == user_id).first()
       if not user:
           return False, "User not found"
      
       # Check if user is already part of an organization
       if user.organization_id:
           return False, "You are already part of an organization. Leave your current organization before joining a new one."
      
       # Join the organization (default role is employee)
       user.organization_id = org.id
       user.role = role
      
       session.commit()
      
       return True, "Successfully joined organization"
   except Exception as e:
       session.rollback()
       return False, str(e)
   finally:
       session.close()
def get_organization_members(org_id):
   """Get all members of an organization"""
   session = get_db_session()
   try:
       return session.query(User).filter(User.organization_id == org_id).all()
   except Exception as e:
       return []
   finally:
       session.close()
def add_user_to_organization(user_id, org_id, role="employee"):
   """Add an existing user to an organization with a specified role"""
   session = get_db_session()
   try:
       # Find the user
       user = session.query(User).filter(User.id == user_id).first()
       if not user:
           return False, "User not found"
      
       # Update organization and role
       user.organization_id = org_id
       user.role = role
      
       session.commit()
      
       return True, "User added to organization"
   except Exception as e:
       session.rollback()
       return False, str(e)
   finally:
       session.close()
def create_employee_account(username, email, password, org_id, role="employee"):
   """Create a new employee account and add to organization"""
   session = get_db_session()
   try:
       # Check if username already exists
       if session.query(User).filter(User.username == username).first():
           return False, "Username already exists"
      
       # Check if email already exists
       if session.query(User).filter(User.email == email).first():
           return False, "Email already exists"
      
       # Hash the password
       password_hash, salt = User.hash_password(password)
      
       # Create the user with organization
       new_user = User(
           username=username,
           email=email,
           password_hash=password_hash,
           salt=salt,
           organization_id=org_id,
           role=role
       )
      
       session.add(new_user)
       session.commit()
      
       return True, "Employee account created successfully"
   except Exception as e:
       session.rollback()
       return False, str(e)
   finally:
       session.close()
def submit_time_off_request(user_id, start_date, end_date, reason=None):
   """Submit a new time-off request"""
   session = get_db_session()
   try:
       # Create time-off request
       request = TimeOffRequest(
           user_id=user_id,
           start_date=start_date,
           end_date=end_date,
           reason=reason
       )
      
       session.add(request)
       session.commit()
      
       return True, "Time-off request submitted successfully"
   except Exception as e:
       session.rollback()
       return False, str(e)
   finally:
       session.close()
def get_time_off_requests(user_id=None, org_id=None, status=None):
   """Get time-off requests with various filters
  
   Args:
       user_id: Filter by specific user (get a user's requests)
       org_id: Filter by organization (for managers/admins to see all org requests)
       status: Filter by status (pending, approved, rejected)
   """
   session = get_db_session()
   try:
       query = session.query(TimeOffRequest)
      
       # Apply filters
       if user_id:
           query = query.filter(TimeOffRequest.user_id == user_id)
      
       if status:
           query = query.filter(TimeOffRequest.status == status)
      
       if org_id:
           # Need to join with User to filter by organization
           query = query.join(User).filter(User.organization_id == org_id)
      
       # Order by status (pending first), then start date
       query = query.order_by(
           # Put pending requests first
           sa.case(
               (TimeOffRequest.status == "pending", 0),
               (TimeOffRequest.status == "approved", 1),
               else_=2
           ),
           TimeOffRequest.start_date
       )
      
       return query.all()
   except Exception as e:
       return []
   finally:
       session.close()
def update_time_off_request(request_id, status, manager_user_id):
   """Update a time-off request status (approve/reject)"""
   session = get_db_session()
   try:
       # Get the request
       request = session.query(TimeOffRequest).filter(TimeOffRequest.id == request_id).first()
       if not request:
           return False, "Request not found"
      
       # Get the manager user
       manager = session.query(User).filter(User.id == manager_user_id).first()
       if not manager:
           return False, "Manager user not found"
      
       # Check manager permissions
       if not manager.is_manager():
           return False, "You don't have permission to update time-off requests"
      
       # Check if manager and employee are in the same organization
       employee = session.query(User).filter(User.id == request.user_id).first()
       if not employee or employee.organization_id != manager.organization_id:
           return False, "You can only manage requests from employees in your organization"
      
       # Update status
       request.status = status
       session.commit()
      
       return True, f"Request {status}"
   except Exception as e:
       session.rollback()
       return False, str(e)
   finally:
       session.close()
business.py
import streamlit as st
from datetime import datetime, date, timedelta
import calendar
import pandas as pd
# Import from our modules
from db import (
   create_organization, get_organization, get_organization_members,
   create_employee_account, add_user_to_organization,
   submit_time_off_request, get_time_off_requests, update_time_off_request,
   get_user_by_id, join_organization_by_invite
)
def business_page():
   """Main business page for organization management"""
   if 'active_business_tab' not in st.session_state:
       st.session_state.active_business_tab = "Organization"
  
   # Get current user info
   user = get_user_by_id(st.session_state.user_id)
  
   # Check if user is part of an organization
   if user.organization_id:
       # User is part of an organization - show organization info
       organization = get_organization(user.organization_id)
      
       st.subheader(f"{organization.name} - Business Portal")
      
       # Create tabs for different sections of business portal
       tab_options = ["Organization"]
      
       # Only show employee management for managers/admins
       if user.is_manager():
           tab_options.append("Employee Management")
      
       # Everyone can see time-off requests
       tab_options.append("Time-Off Requests")
      
       # Display horizontal tabs
       selected_tab = st.radio("Business Portal Navigation",
                               options=tab_options,
                               horizontal=True,
                               index=tab_options.index(st.session_state.active_business_tab))
      
       # Update active tab in session state
       st.session_state.active_business_tab = selected_tab
      
       # Display the selected tab content
       if selected_tab == "Organization":
           organization_tab(organization, user)
       elif selected_tab == "Employee Management" and user.is_manager():
           employee_management_tab(organization, user)
       elif selected_tab == "Time-Off Requests":
           time_off_requests_tab(organization, user)
   else:
       # User is not part of an organization - show options to create or join
       st.write("You are not currently part of a business account.")
      
       # Create tabs for create/join
       create_tab, join_tab = st.tabs(["Create Business Account", "Join Business"])
      
       with create_tab:
           create_organization_form()
      
       with join_tab:
           st.subheader("Join a Business")
           st.info("If you have an invitation code from a business administrator, you can join their organization.")
          
           with st.form("join_org_form"):
               invite_code = st.text_input("Invitation Code", help="Enter the invitation code provided by your business administrator", placeholder="ABC123XYZ")
               submitted = st.form_submit_button("Join Business")
              
               if submitted:
                   if not invite_code:
                       st.error("Please enter an invitation code")
                   else:
                       # Try to join the organization
                       success, message = join_organization_by_invite(
                           user_id=st.session_state.user_id,
                           invite_code=invite_code
                       )
                      
                       if success:
                           st.success("Successfully joined organization!")
                           st.rerun()
                       else:
                           st.error(message)
def create_organization_form():
   """Form to create a new organization"""
   st.subheader("Create a Business Account")
  
   with st.form("create_org_form"):
       org_name = st.text_input("Business Name", help="Enter your company or business name")
       org_description = st.text_area("Business Description (Optional)",
                                     help="Brief description of your business")
      
       submitted = st.form_submit_button("Create Business Account")
      
       if submitted:
           if not org_name:
               st.error("Please enter a business name")
           else:
               # Create organization with current user as admin
               success, org_id, invite_code = create_organization(
                   name=org_name,
                   description=org_description,
                   admin_user_id=st.session_state.user_id
               )
              
               if success:
                   st.success(f"Business account '{org_name}' created successfully!")
                   st.info(f"Invite Code: **{invite_code}** - Share this with employees to join your organization.")
                   st.rerun()
               else:
                   st.error(f"Error creating business account: {org_id}")
def organization_tab(organization, user):
   """Display organization information and settings"""
   st.write("### Business Information")
   st.write(f"**Business Name:** {organization.name}")
  
   if organization.description:
       st.write(f"**Description:** {organization.description}")
  
   # Show invite code for managers/admins
   if user.is_manager():
       with st.expander("Employee Invitation", expanded=False):
           st.write("Share this invitation code with employees to let them join your organization:")
           st.code(organization.invite_code, language=None)
           st.info("Employees can use this code to join your organization from their account page.")
  
   # Show members
   st.write("### Business Members")
   members = get_organization_members(organization.id)
  
   if members:
       member_data = []
       for member in members:
           member_data.append({
               "Username": member.username,
               "Email": member.email,
               "Role": member.role.capitalize(),
               "Member Since": member.created_at.strftime("%Y-%m-%d")
           })
      
       # Create a DataFrame for display
       members_df = pd.DataFrame(member_data)
       st.dataframe(members_df, use_container_width=True, hide_index=True)
   else:
       st.info("No members found.")
def employee_management_tab(organization, user):
   """Tab for managing employees (only for managers/admins)"""
   st.write("### Employee Management")
  
   # Form to add new employees
   with st.expander("Add New Employee", expanded=True):
       with st.form("add_employee_form"):
           st.write("Create new employee account")
           emp_username = st.text_input("Username")
           emp_email = st.text_input("Email")
           emp_password = st.text_input("Initial Password", type="password")
           emp_role = st.selectbox("Role", options=["employee", "manager"])
          
           # Only allow creating managers if user is admin
           if emp_role == "manager" and not user.is_admin():
               st.warning("Only administrators can create manager accounts")
          
           submitted = st.form_submit_button("Add Employee")
          
           if submitted:
               # Validate fields
               if not emp_username or not emp_email or not emp_password:
                   st.error("All fields are required")
               elif emp_role == "manager" and not user.is_admin():
                   st.error("You don't have permission to create manager accounts")
               else:
                   # Create employee account
                   success, message = create_employee_account(
                       username=emp_username,
                       email=emp_email,
                       password=emp_password,
                       org_id=organization.id,
                       role=emp_role
                   )
                  
                   if success:
                       st.success(f"Employee account for {emp_username} created successfully!")
                       st.rerun()
                   else:
                       st.error(f"Error creating employee account: {message}")
  
   # List and manage existing employees
   st.write("### Current Employees")
   members = get_organization_members(organization.id)
  
   if members:
       for member in members:
           # Don't include the current user
           if member.id != user.id:
               with st.container(border=True):
                   col1, col2, col3 = st.columns([3, 2, 1])
                   with col1:
                       st.write(f"**{member.username}**")
                       st.write(f"Role: {member.role.capitalize()}")
                   with col2:
                       st.write(f"Email: {member.email}")
                       st.write(f"Joined: {member.created_at.strftime('%Y-%m-%d')}")
                   with col3:
                       # Only show role management if user is admin
                       if user.is_admin() and member.id != user.id:
                           if member.role == "employee":
                               if st.button("Promote to Manager", key=f"promote_{member.id}"):
                                   success, message = add_user_to_organization(
                                       user_id=member.id,
                                       org_id=organization.id,
                                       role="manager"
                                   )
                                   if success:
                                       st.success(f"{member.username} promoted to manager.")
                                       st.rerun()
                                   else:
                                       st.error(f"Error updating role: {message}")
                           elif member.role == "manager":
                               if st.button("Demote to Employee", key=f"demote_{member.id}"):
                                   success, message = add_user_to_organization(
                                       user_id=member.id,
                                       org_id=organization.id,
                                       role="employee"
                                   )
                                   if success:
                                       st.success(f"{member.username} demoted to employee.")
                                       st.rerun()
                                   else:
                                       st.error(f"Error updating role: {message}")
   else:
       st.info("No employees found.")
def time_off_requests_tab(organization, user):
   """Tab for managing time-off requests"""
   st.write("### Time-Off Requests")
  
   # Create tabs for different views
   my_requests_tab, new_request_tab = st.tabs(["My Requests", "New Request"])
  
   # Add a third tab for managers to see all organization requests
   if user.is_manager():
       team_requests_tab = st.tabs(["Team Requests"])[0]
  
   with my_requests_tab:
       display_user_time_off_requests(user.id)
  
   with new_request_tab:
       submit_time_off_request_form(user.id)
  
   if user.is_manager():
       with team_requests_tab:
           display_team_time_off_requests(organization.id, user.id)
def display_user_time_off_requests(user_id):
   """Display time-off requests for a specific user"""
   st.write("Your time-off requests:")
  
   # Get user's time off requests
   requests = get_time_off_requests(user_id=user_id)
  
   if not requests:
       st.info("You don't have any time-off requests.")
       return
  
   # Group by status
   pending = [req for req in requests if req.status == "pending"]
   approved = [req for req in requests if req.status == "approved"]
   rejected = [req for req in requests if req.status == "rejected"]
  
   # Display pending requests first
   if pending:
       st.write("#### Pending Requests")
       for req in pending:
           with st.container(border=True):
               col1, col2 = st.columns(2)
               with col1:
                   st.write(f"**{req.start_date.strftime('%Y-%m-%d')} to {req.end_date.strftime('%Y-%m-%d')}**")
                   if req.reason:
                       st.write(f"Reason: {req.reason}")
               with col2:
                   st.write(f"Status: **{req.status.capitalize()}**")
                   st.write(f"Submitted: {req.created_at.strftime('%Y-%m-%d')}")
  
   # Display approved requests
   if approved:
       st.write("#### Approved Requests")
       for req in approved:
           with st.container(border=True):
               col1, col2 = st.columns(2)
               with col1:
                   st.write(f"**{req.start_date.strftime('%Y-%m-%d')} to {req.end_date.strftime('%Y-%m-%d')}**")
                   if req.reason:
                       st.write(f"Reason: {req.reason}")
               with col2:
                   st.write(f"Status: **{req.status.capitalize()}**")
                   st.write(f"Submitted: {req.created_at.strftime('%Y-%m-%d')}")
  
   # Display rejected requests
   if rejected:
       st.write("#### Rejected Requests")
       for req in rejected:
           with st.container(border=True):
               col1, col2 = st.columns(2)
               with col1:
                   st.write(f"**{req.start_date.strftime('%Y-%m-%d')} to {req.end_date.strftime('%Y-%m-%d')}**")
                   if req.reason:
                       st.write(f"Reason: {req.reason}")
               with col2:
                   st.write(f"Status: **{req.status.capitalize()}**")
                   st.write(f"Submitted: {req.created_at.strftime('%Y-%m-%d')}")
def submit_time_off_request_form(user_id):
   """Form to submit a new time-off request"""
   st.write("Submit a new time-off request:")
  
   with st.form("time_off_request_form"):
       # Date selection
       today = date.today()
       start_date = st.date_input(
           "Start Date",
           min_value=today,
           value=today + timedelta(days=7),
           help="First day of requested time off"
       )
      
       end_date = st.date_input(
           "End Date",
           min_value=start_date,
           value=start_date + timedelta(days=1),
           help="Last day of requested time off"
       )
      
       # Reason
       reason = st.text_area("Reason (Optional)", help="Brief explanation for your time-off request")
      
       # Submit button
       submitted = st.form_submit_button("Submit Request")
      
       if submitted:
           # Convert dates to datetime objects
           start_datetime = datetime.combine(start_date, datetime.min.time())
           end_datetime = datetime.combine(end_date, datetime.min.time())
          
           # Submit request
           success, result = submit_time_off_request(
               user_id=user_id,
               start_date=start_datetime,
               end_date=end_datetime,
               reason=reason
           )
          
           if success:
               st.success("Time-off request submitted successfully!")
               st.rerun()
           else:
               st.error(f"Error submitting request: {result}")
def display_team_time_off_requests(org_id, manager_id):
   """Display time-off requests for the entire team (managers only)"""
   st.write("Team time-off requests:")
  
   # Get organization time off requests
   requests = get_time_off_requests(org_id=org_id)
  
   if not requests:
       st.info("There are no time-off requests from your team.")
       return
  
   # Filter pending requests first
   pending = [req for req in requests if req.status == "pending"]
  
   # Display pending requests that need approval
   if pending:
       st.write("#### Pending Requests")
       for req in pending:
           with st.container(border=True):
               # Get employee info
               employee = get_user_by_id(req.user_id)
               employee_name = employee.username if employee else "Unknown"
              
               col1, col2, col3 = st.columns([3, 2, 1])
              
               with col1:
                   st.write(f"**{employee_name}**")
                   st.write(f"{req.start_date.strftime('%Y-%m-%d')} to {req.end_date.strftime('%Y-%m-%d')}")
                   if req.reason:
                       st.write(f"Reason: {req.reason}")
              
               with col2:
                   st.write(f"Status: **{req.status.capitalize()}**")
                   st.write(f"Submitted: {req.created_at.strftime('%Y-%m-%d')}")
              
               with col3:
                   if st.button("Approve", key=f"approve_{req.id}"):
                       success, message = update_time_off_request(
                           request_id=req.id,
                           status="approved",
                           manager_user_id=manager_id
                       )
                      
                       if success:
                           st.success("Request approved!")
                           st.rerun()
                       else:
                           st.error(f"Error: {message}")
                  
                   if st.button("Reject", key=f"reject_{req.id}"):
                       success, message = update_time_off_request(
                           request_id=req.id,
                           status="rejected",
                           manager_user_id=manager_id
                       )
                      
                       if success:
                           st.success("Request rejected.")
                           st.rerun()
                       else:
                           st.error(f"Error: {message}")
  
   # Display all other requests (approved/rejected) with expandable sections
   with st.expander("View All Approved/Rejected Requests", expanded=False):
       # Approved requests
       approved = [req for req in requests if req.status == "approved"]
       if approved:
           st.write("#### Approved Requests")
           for req in approved:
               with st.container(border=True):
                   # Get employee info
                   employee = get_user_by_id(req.user_id)
                   employee_name = employee.username if employee else "Unknown"
                  
                   col1, col2 = st.columns(2)
                  
                   with col1:
                       st.write(f"**{employee_name}**")
                       st.write(f"{req.start_date.strftime('%Y-%m-%d')} to {req.end_date.strftime('%Y-%m-%d')}")
                       if req.reason:
                           st.write(f"Reason: {req.reason}")
                  
                   with col2:
                       st.write(f"Status: **{req.status.capitalize()}**")
                       st.write(f"Submitted: {req.created_at.strftime('%Y-%m-%d')}")
      
       # Rejected requests
       rejected = [req for req in requests if req.status == "rejected"]
       if rejected:
           st.write("#### Rejected Requests")
           for req in rejected:
               with st.container(border=True):
                   # Get employee info
                   employee = get_user_by_id(req.user_id)
                   employee_name = employee.username if employee else "Unknown"
                  
                   col1, col2 = st.columns(2)
                  
                   with col1:
                       st.write(f"**{employee_name}**")
                       st.write(f"{req.start_date.strftime('%Y-%m-%d')} to {req.end_date.strftime('%Y-%m-%d')}")
                       if req.reason:
                           st.write(f"Reason: {req.reason}")
                  
                   with col2:
                       st.write(f"Status: **{req.status.capitalize()}**")
                       st.write(f"Submitted: {req.created_at.strftime('%Y-%m-%d')}")
