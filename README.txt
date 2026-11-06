 
AJ TaskSphere: Quick Gist
What it is: a web portal for Akshita Joshi & Associates to assign client work, track deadlines, collect daily End-of-Day (EOD) reports from staff, get them approved by managers, and see hours and compliance on a dashboard. It is one Python file and opens in any browser.
Who uses it
Role	Access
Admin	Everything: users, clients, assignments, holidays, settings, audit log.
Partner / Manager	Review and approve EODs, create assignments. Managers see only their team.
Employee	Own assignments only. Submits daily EODs and reads feedback.
Key features
•	Dashboard with 8 KPI cards and 4 charts, filterable by day, week, month, financial year or custom dates.
•	EOD workflow: Draft, Submitted, Under Review, Approved or Changes Requested. Approved records are locked.
•	Client master with duplicate checks (code, PAN, GSTIN) and 16 CA service categories for assignments.
•	Maharashtra holiday calendar for FY 2026-27, in-app notifications, CSV reports and an audit log.
Built with
Tool	Purpose
Python 3 and Flask	The language and web framework that run the portal.
SQLite	Database kept in one file (eod_portal.db). No server needed.
Werkzeug	Scrambles (hashes) passwords for safe storage.
Chart.js	Draws the dashboard charts (needs internet).
HTML and CSS	Page design, written inside the Python file.
PyInstaller / Gunicorn	Optional: make a Windows .exe, or run on an online host.
How to run
1.	Install Python, then run: pip install flask
2.	Run: python assignment_tracker_eod_portal.py
3.	Open http://127.0.0.1:5000 in a browser and sign in. This address works only on the same computer.
Starting logins
Admin: akshitaaa.gpt@gmail.com    Employee: Kajal Singh. Passwords are set in the code. Change them before using real data.
