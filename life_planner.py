"""Life Planner — offline desktop planner, Python standard library only."""
import calendar
import csv
import os
import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime, timedelta
from pathlib import Path

FMT = '%Y-%m-%d %H:%M'

def next_due(due, repeat):
    if repeat == 'Daily': return due + timedelta(days=1)
    if repeat == 'Weekdays':
        due += timedelta(days=1)
        while due.weekday() > 4: due += timedelta(days=1)
        return due
    if repeat == 'Weekly': return due + timedelta(days=7)
    if repeat == 'Monthly':
        month = due.month % 12 + 1
        year = due.year + (due.month == 12)
        return due.replace(year=year, month=month, day=min(due.day, calendar.monthrange(year, month)[1]))
    return None

class Planner:
    def __init__(self, root):
        self.root = root
        folder = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'MunazzaLifePlanner'
        folder.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(folder / 'planner.sqlite3')
        self.db.execute('CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY, title TEXT, category TEXT, due TEXT, recurrence TEXT, lead INTEGER, notes TEXT, done INTEGER DEFAULT 0, notified TEXT)')
        root.title('Life Planner | Work • Home • School')
        root.geometry('1120x720'); root.minsize(920, 620)
        root.configure(bg='#eef2ff')
        style = ttk.Style(); style.theme_use('clam')
        style.configure('Treeview', rowheight=32, font=('Segoe UI', 10))
        style.configure('TButton', padding=8)
        tk.Label(root, text='Life Planner', font=('Segoe UI', 25, 'bold'), fg='#312e81', bg='#eef2ff').pack(anchor='w', padx=24, pady=(18, 0))
        tk.Label(root, text='A little clarity for work, motherhood and tomorrow.', font=('Segoe UI', 11), bg='#eef2ff', fg='#475569').pack(anchor='w', padx=26, pady=(2, 12))
        bar = ttk.Frame(root); bar.pack(fill='x', padx=24)
        self.view = tk.StringVar(value='Tomorrow'); self.cat = tk.StringVar(value='All categories')
        for variable, choices in [(self.view, ['Today', 'Tomorrow', 'Next 7 days', 'All active', 'Completed']), (self.cat, ['All categories', 'Work', 'Daughter / School', 'Home / Personal'])]:
            box = ttk.Combobox(bar, textvariable=variable, values=choices, state='readonly', width=22); box.pack(side='left', padx=(0, 8)); box.bind('<<ComboboxSelected>>', lambda e: self.refresh())
        ttk.Button(bar, text='+ Add task', command=self.editor).pack(side='right')
        self.summary = tk.StringVar(); ttk.Label(root, textvariable=self.summary).pack(anchor='w', padx=26, pady=12)
        frame = ttk.Frame(root); frame.pack(fill='both', expand=True, padx=24)
        self.tree = ttk.Treeview(frame, columns=('due','title','category','repeat','status'), show='headings', selectmode='browse')
        for col, title, width in [('due','Date & time',155),('title','Task',300),('category','Area of life',170),('repeat','Repeat',100),('status','Status',100)]:
            self.tree.heading(col, text=title); self.tree.column(col, width=width)
        scroll = ttk.Scrollbar(frame, orient='vertical', command=self.tree.yview); self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side='left', fill='both', expand=True); scroll.pack(side='right', fill='y')
        self.tree.tag_configure('late', foreground='#b91c1c'); self.tree.bind('<Double-1>', lambda e: self.edit_selected())
        actions = ttk.Frame(root); actions.pack(fill='x', padx=24, pady=14)
        for label, cmd in [('✓ Complete', self.complete), ('Edit / notes', self.edit_selected), ('Snooze 10 min', self.snooze), ('Delete', self.delete), ('Export all CSV', self.export)]:
            ttk.Button(actions, text=label, command=cmd).pack(side='left', padx=(0, 8))
        tk.Label(root, text='Reminders work while this app is running and your computer is awake. Minimize to keep reminders active.\nTimes follow your computer’s local clock. Data stays on this computer; export CSV for backup.', bg='#eef2ff', fg='#475569', justify='left').pack(anchor='w', padx=26, pady=(0, 16))
        root.protocol('WM_DELETE_WINDOW', self.close)
        self.refresh(); root.after(1000, self.check)

    def selected(self):
        ids = self.tree.selection()
        if not ids: messagebox.showinfo('Choose a task', 'Please select a task first.'); return None
        return self.db.execute('SELECT * FROM tasks WHERE id=?', (ids[0],)).fetchone()

    def refresh(self):
        for i in self.tree.get_children(): self.tree.delete(i)
        now = datetime.now(); today = now.date(); view = self.view.get()
        rows = self.db.execute('SELECT * FROM tasks ORDER BY due,id').fetchall()
        active = [r for r in rows if not r[7]]
        self.summary.set(f'{sum(datetime.strptime(r[3], FMT).date()==today for r in active)} due today  •  {sum(datetime.strptime(r[3], FMT).date()==today+timedelta(days=1) for r in active)} tomorrow  •  {sum(datetime.strptime(r[3], FMT)<now for r in active)} overdue')
        for r in rows:
            date = datetime.strptime(r[3], FMT)
            if bool(r[7]) != (view == 'Completed'): continue
            if self.cat.get() != 'All categories' and r[2] != self.cat.get(): continue
            if view == 'Today' and date.date() != today: continue
            if view == 'Tomorrow' and date.date() != today + timedelta(days=1): continue
            if view == 'Next 7 days' and not today <= date.date() <= today+timedelta(days=6): continue
            late = date < now and not r[7]
            self.tree.insert('', 'end', iid=r[0], values=(r[3],r[1],r[2],r[4], 'Completed' if r[7] else 'Overdue' if late else 'Upcoming'), tags=('late',) if late else ())

    def editor(self, row=None):
        win = tk.Toplevel(self.root); win.title('Edit task' if row else 'Add a task'); win.geometry('490x580'); win.transient(self.root); win.grab_set()
        defaults = [row[1],row[2],row[3],row[4],str(row[5]),row[6]] if row else ['', 'Work', (datetime.now()+timedelta(days=1)).replace(hour=9,minute=0).strftime(FMT), 'None', '15', '']
        fields = []
        for index, label in enumerate(['Task title', 'Category', 'Due date & time (YYYY-MM-DD HH:MM)', 'Repeat', 'Remind me before (minutes)', 'Notes / school items to carry']):
            ttk.Label(win, text=label).pack(anchor='w', padx=20, pady=(12, 3))
            var = tk.StringVar(value=defaults[index]); fields.append(var)
            choices = {1:['Work','Daughter / School','Home / Personal'], 3:['None','Daily','Weekdays','Weekly','Monthly']}.get(index)
            entry = ttk.Combobox(win, textvariable=var, values=choices, state='readonly') if choices else ttk.Entry(win,textvariable=var)
            entry.pack(fill='x', padx=20)
        def save():
            title, category, due, repeat, lead, notes = [v.get().strip() for v in fields]
            try:
                due = datetime.strptime(due,FMT).strftime(FMT); lead = int(lead)
                if not title or not 0 <= lead <= 10080: raise ValueError()
            except ValueError:
                messagebox.showerror('Check task', 'Enter a title, valid date/time, and reminder minutes from 0 to 10080.',parent=win); return
            with self.db:
                if row: self.db.execute('UPDATE tasks SET title=?,category=?,due=?,recurrence=?,lead=?,notes=?,notified=NULL WHERE id=?', (title,category,due,repeat,lead,notes,row[0]))
                else: self.db.execute('INSERT INTO tasks(title,category,due,recurrence,lead,notes) VALUES(?,?,?,?,?,?)',(title,category,due,repeat,lead,notes))
            self.refresh(); win.destroy()
        ttk.Button(win,text='Save task',command=save).pack(pady=20)

    def edit_selected(self):
        row = self.selected()
        if row: self.editor(row)

    def complete(self):
        r = self.selected()
        if not r or r[7]: return
        due = next_due(datetime.strptime(r[3],FMT), r[4])
        # Skip missed repeats, preserving the scheduled time instead of completion time.
        while due and due <= datetime.now(): due = next_due(due, r[4])
        with self.db:
            self.db.execute('UPDATE tasks SET done=1 WHERE id=?', (r[0],))
            if due: self.db.execute('INSERT INTO tasks(title,category,due,recurrence,lead,notes) VALUES(?,?,?,?,?,?)', (r[1],r[2],due.strftime(FMT),r[4],r[5],r[6]))
        self.refresh()

    def snooze(self):
        r = self.selected()
        if not r or r[7]: return
        with self.db: self.db.execute('UPDATE tasks SET notified=? WHERE id=?', ((datetime.now()+timedelta(minutes=10)).strftime(FMT),r[0]))
        messagebox.showinfo('Snoozed', 'Reminder postponed for 10 minutes. The due date is unchanged.')

    def delete(self):
        r = self.selected()
        if r and messagebox.askyesno('Delete task', 'Delete this task? No further repeats will be created from it.'):
            with self.db: self.db.execute('DELETE FROM tasks WHERE id=?', (r[0],))
            self.refresh()

    def export(self):
        path = filedialog.asksaveasfilename(defaultextension='.csv', initialfile='Life_Planner_Backup.csv',filetypes=[('CSV','*.csv')])
        if path:
            try:
                with open(path, 'w', newline='', encoding='utf-8-sig') as f:
                    writer = csv.writer(f); writer.writerow(['ID','Task','Category','Due','Repeat','Reminder minutes','Notes','Completed','Next reminder']); writer.writerows(self.db.execute('SELECT * FROM tasks ORDER BY due'))
                messagebox.showinfo('Exported','All tasks exported. Keep this file private.')
            except OSError as e: messagebox.showerror('Export failed',str(e))

    def check(self):
        now = datetime.now(); alerts = []
        with self.db:
            for r in self.db.execute('SELECT * FROM tasks WHERE done=0').fetchall():
                due = datetime.strptime(r[3],FMT)
                eligible = datetime.strptime(r[8],FMT) if r[8] else due-timedelta(minutes=r[5])
                if now >= eligible:
                    alerts.append(f'{r[3]} | {r[2]}\n{r[1]}'+(f'\n{r[6]}' if r[6] else ''))
                    self.db.execute('UPDATE tasks SET notified=? WHERE id=?', ((now+timedelta(minutes=30)).strftime(FMT),r[0]))
        self.refresh()
        if alerts:
            popup = tk.Toplevel(self.root); popup.title('Your task reminders'); popup.geometry('550x360'); popup.attributes('-topmost',True)
            box = tk.Text(popup,wrap='word',font=('Segoe UI',11)); box.pack(fill='both',expand=True,padx=12,pady=12); box.insert('1.0','\n\n'.join(alerts)); box.configure(state='disabled')
            ttk.Button(popup,text='Dismiss — reminds again in 30 minutes',command=popup.destroy).pack(pady=8)
            self.root.bell()
        self.root.after(20000,self.check)

    def close(self):
        if messagebox.askyesno('Close planner?', 'Closing stops reminders. Minimize instead to keep them running. Close now?'):
            self.db.close(); self.root.destroy()

if __name__ == '__main__':
    root = tk.Tk(); Planner(root); root.mainloop()
