import csv
from config import config, force_reload_global_config
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
import tkinter.font as tkFont
import tomllib
import toml
import os
import threading
import time

from tqdm import tqdm

from library import convert_unit, count_lines_and_hash, try_parse_to_assay_type
from refactor import analyse_hole, build_data_table



CONFIG_PATH = 'config.toml'
ASSAY_CONFIG_PATH = 'assays.toml'
VALID_UNITS = ['%', 'ppm', 'ppb']
VALID_ELEMENTS = {
    # Common chemical symbols
    "H", "He", "Li", "Be", "B", "C", "N", "O", "F", "Ne",
    "Na", "Mg", "Al", "Si", "P", "S", "Cl", "Ar", "K", "Ca",
    "Sc", "Ti", "V", "Cr", "Mn", "Fe", "Co", "Ni", "Cu", "Zn",
    "Ga", "Ge", "As", "Se", "Br", "Kr", "Rb", "Sr", "Y", "Zr",
    "Nb", "Mo", "Tc", "Ru", "Rh", "Pd", "Ag", "Cd", "In", "Sn",
    "Sb", "Te", "I", "Xe", "Cs", "Ba", "La", "Ce", "Pr", "Nd",
    "Pm", "Sm", "Eu", "Gd", "Tb", "Dy", "Ho", "Er", "Tm", "Yb",
    "Lu", "Hf", "Ta", "W", "Re", "Os", "Ir", "Pt", "Au", "Hg",
    "Tl", "Pb", "Bi", "Po", "At", "Rn", "Fr", "Ra", "Ac", "Th",
    "Pa", "U", "Np", "Pu", "Am", "Cm", "Bk", "Cf", "Es", "Fm"
}


class ConfigEditor:
    def __init__(self, root, font):
        self.root = root
        self.root.title("TOML Configuration Editor")
        self.data = {}
        self.entries = {}
        self.main_entries = {}

        self.notebook = ttk.Notebook(root)
        self.settings_frame = ttk.Frame(self.notebook)
        self.assay_frame = ttk.Frame(self.notebook)

        self.font = font

        self.notebook.add(self.settings_frame, text='Settings')
        self.notebook.add(self.assay_frame, text='Assays')
        self.notebook.pack(expand=1, fill='both')

        self.build_settings_tab()
        self.build_assay_tab()
        self.load_config()

        self.run_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.run_tab, text="Run")
        self.build_run_tab()
        self.unsaved_changes = False


    def build_run_tab(self):
        frame = ttk.Frame(self.run_tab, padding=10)
        frame.pack(fill="both", expand=True)

        # File location
        ttk.Label(frame, text="Save File Location:", font=self.font).pack(anchor="w")
        self.output_path_var = tk.StringVar()
        output_frame = ttk.Frame(frame)
        output_frame.pack(fill="x", pady=5)

        output_entry = ttk.Entry(output_frame, textvariable=self.output_path_var)
        output_entry.pack(side="left", fill="x", expand=True)

        def choose_output_file():
            path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV Files", "*.csv")])
            if path:
                self.output_path_var.set(path)

        ttk.Button(output_frame, text="Browse...", command=choose_output_file).pack(side="left")

        # Run button
        ttk.Button(frame, text="Run", command=self.start_run_process).pack(pady=10)

        # Progress bar
        self.progress = ttk.Progressbar(frame, mode="determinate")
        self.progress.pack(fill="x", pady=10)

    def build_settings_tab(self):
        frm = ttk.Frame(self.settings_frame)
        frm.pack(padx=10, pady=10)

        row = 0

        def add_label(text):
            nonlocal row
            ttk.Label(frm, text=text).grid(row=row, column=0, sticky='w')
            row += 1

        def add_entry(key, label, is_path=False):
            nonlocal row

            ttk.Label(frm, text=label).grid(row=row, column=0, sticky='w')
            ent = ttk.Entry(frm, width=50)
            ent.grid(row=row, column=1)
            if is_path:
                def browse():
                    path = filedialog.askopenfilename(
                        initialdir='.',
                        title='Select CSV file',
                        filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
                    )

                    if path:
                        ent.delete(0, tk.END)
                        ent.insert(0, path)
                ttk.Button(frm, text="Browse", command=browse).grid(row=row, column=2)

            def on_focus_out(event):
                self.unsaved_changes = True
            ent.bind('<FocusOut>', on_focus_out)
            self.main_entries[key] = ent
            row += 1

        def add_checkbox(key, label):
            nonlocal row
            var = tk.BooleanVar()
            chk = ttk.Checkbutton(frm, text=label, variable=var)
            chk.grid(row=row, column=0, columnspan=2, sticky='w')
            self.main_entries[key] = var
            def on_focus_out(event):
                self.unsaved_changes = True
            chk.bind('<FocusOut>', on_focus_out)
            row += 1

        def add_list_editor(key, label):
            nonlocal row
            def edit_list():
                current = self.data['settings'].get(key, ['*'])
                val = simpledialog.askstring("Edit list", f"Comma-separated list for {key}:", 
                                             initialvalue=', '.join(current))
                if val is not None:
                    self.data['settings'][key] = [v.strip() for v in val.split(',') if v.strip()]
                    self.main_entries[key].config(text=str(self.data['settings'][key]))

            ttk.Label(frm, text=label).grid(row=row, column=0, sticky='w')
            btn = ttk.Button(frm, text="Edit", command=edit_list)
            btn.grid(row=row, column=1, sticky='w')
            self.main_entries[key] = btn
            row += 1

        # Add fields
        add_list_editor('hole_selections', 'Hole Selections')
        add_list_editor('queries_to_run', 'Queries to Run')
        add_checkbox('seperate_assay_files', 'Separate Assay Files')
        add_entry('exported_data_path', 'Exported CSV Path', is_path=True)
        add_entry('sample_id_column_name', 'Sample ID Column')
        add_entry('hole_id_column_name', 'Hole ID Column')
        add_entry('cache_location', 'Cache Location')
        add_entry('internal_dilution_intervals', "Internal Dilution Factor")
        add_entry("from_column_name", "'From' column name")
        add_entry("to_column_name", "'To' column name")

        # Buttons
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(pady=(10, 0))
        ttk.Button(btn_frame, text="Load", command=self.load_config).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Save", command=self.save_config).pack(side=tk.LEFT, padx=5)


    def start_run_process(self):

        if self.unsaved_changes:
                if messagebox.askyesno("Confirmation", "You may have unsaved changes. Would you like to save these before running?"):
                    self.save_config()

        output_path = self.output_path_var.get()
        if not output_path:
            messagebox.showwarning("Missing Output", "Please select a save file location first.")
            return

        # Reset progress
        self.progress["value"] = 0
        self.progress["maximum"] = 100

        # Run the long process in a thread
        threading.Thread(target=self.run_long_task, daemon=True).start()

    def run_long_task(self):

        file_name = config.settings.exported_data_path

        loc, hash_value = count_lines_and_hash(file_name)
        self.progress["maximum"] = loc -1

        i = 0
        def update_progress():
            nonlocal i
            self.progress.after(0, lambda val=i: self.progress.configure(value=val))
            i+=1

        data_table_ = build_data_table(file_name, loc, update_progress)

        self.progress["value"] = 0

        queries = None
        with open('assays.toml', 'rb') as queries_file:
            queries = tomllib.load(queries_file)

        assay_list_ = []
        for assay in list(queries.values()):
            element = assay['element']
            base_unit = assay['base_unit']
            reported_unit = assay['reported_unit']
            cutoffs = assay['cutoffs']
            
            primary = try_parse_to_assay_type(element, base_unit, reported_unit)

            for i, cutoff in enumerate(cutoffs):
                cutoffs[i] = convert_unit(cutoff, primary.reported_unit, primary.base_unit)

            co_analytes = assay['co_analytes']
            analytes = []
            for co in co_analytes:
                analytes.append(try_parse_to_assay_type(co['element'], co['base_unit'], co['reported_unit']))

            assay_list_.append((primary, cutoffs, analytes))

        print(assay_list_)

        filename = self.output_path_var.get()

        if config.settings.hole_selections == ['*']:
            holes_to_calc = list(data_table_.keys())
        else:
            holes_to_calc = config.settings.hole_selections


        with open(filename, mode='w', newline='') as csvfile:
            writer = csv.writer(csvfile, quoting=csv.QUOTE_NONNUMERIC, escapechar='\\')

            header = ['Hole', 'Primary Analyte', 'Cutoff', 'Cutoff Unit', 'From', 'To', 'Interval', 'Primary Intercept', 'Intercept Label', 'Co Analytes']
            writer.writerow(header)

            self.progress["maximum"] = len(holes_to_calc)

            i = 0
            for hole in holes_to_calc:
                analyse_hole(hole, writer, data_table_, assay_list_)
                self.progress.after(0, lambda val=i: self.progress.configure(value=val))
                i+=1

        messagebox.showinfo("Success", "Intervals were successfully calculated and exported")
            

    def save_assay_changes(self):
        """Save all changes from entry widgets back to assay_data dictionary"""
        for entry_key, entry_widget in self.entries.items():
            if '.' in entry_key:
                assay_name, field_name = entry_key.split('.', 1)
                
                if assay_name in self.assay_data:
                    value = entry_widget.get().strip()
                    
                    if field_name == 'cutoffs':
                        # Parse cutoffs as comma-separated floats
                        try:
                            if value:
                                cutoffs = [float(x.strip()) for x in value.split(',') if x.strip()]
                            else:
                                cutoffs = []
                            self.assay_data[assay_name][field_name] = cutoffs
                        except ValueError:
                            messagebox.showerror("Error", f"Invalid cutoffs format for {assay_name}. Please use comma-separated numbers.")
                            return False
                    else:
                        # For other fields (element, base_unit, reported_unit)
                        self.assay_data[assay_name][field_name] = value
        
        messagebox.showinfo("Saved", "All assay changes have been saved.")
        return True

    def save_and_refresh_assays(self):
        """Save changes and refresh the display"""
        if self.save_assay_changes():
            self.render_assays()

    # You can also add auto-save functionality when fields lose focus
    def setup_auto_save_for_entry(self, entry_widget, entry_key):
        """Set up auto-save when an entry field loses focus"""
        def on_focus_out(event):
            self.unsaved_changes = True
            if '.' in entry_key:
                assay_name, field_name = entry_key.split('.', 1)
                
                if assay_name in self.assay_data:
                    value = entry_widget.get().strip()
                    
                    if field_name == 'cutoffs':
                        try:
                            if value:
                                cutoffs = [float(x.strip()) for x in value.split(',') if x.strip()]
                            else:
                                cutoffs = []
                            self.assay_data[assay_name][field_name] = cutoffs
                        except ValueError:
                            # Revert to original value if invalid
                            original_cutoffs = self.assay_data[assay_name].get('cutoffs', [])
                            entry_widget.delete(0, tk.END)
                            entry_widget.insert(0, ', '.join(map(str, original_cutoffs)))
                            messagebox.showerror("Error", f"Invalid cutoffs format for {assay_name}. Reverted to original value.")
                    else:
                        self.assay_data[assay_name][field_name] = value
        
        entry_widget.bind('<FocusOut>', on_focus_out)


    def build_assay_tab(self):
        self.assay_list_frame = ttk.Frame(self.assay_frame)
        self.assay_list_frame.pack(fill='both', expand=True)

        self.assay_controls = ttk.Frame(self.assay_frame)
        self.assay_controls.pack(fill='x', pady=5, expand=True)

        ttk.Button(self.assay_controls, text="Add Assay", command=self.add_assay_dialog).pack(side='left')

    def add_assay_dialog(self):
        assay_name = simpledialog.askstring("New Assay", "Enter name for new assay (e.g. copper_assay):")
        if not assay_name:
            return
        if assay_name in self.assay_data:
            messagebox.showerror("Error", "That assay already exists.")
            return

        # Create a new blank assay entry
        self.assay_data[assay_name] = {
            'element': '',
            'base_unit': 'ppm',
            'reported_unit': 'ppm',
            'cutoffs': [],
            'co_analytes': []
        }
        self.render_assays()

    
    def open_co_analytes_editor(self, assay_name):
        """Open a UI-based editor for co-analytes instead of string parsing"""
        
        # Create new window
        editor_window = tk.Toplevel(self.root)
        editor_window.title(f"Edit Co-analytes for {assay_name}")
        editor_window.geometry("900x300")
        editor_window.transient(self.root)
        editor_window.grab_set()
        
        # Get existing co-analytes
        co_list = self.assay_data[assay_name].get('co_analytes', [])
        
        # Main frame with scrollable area
        main_frame = ttk.Frame(editor_window)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Create canvas and scrollbar for co-analytes list
        canvas = tk.Canvas(main_frame, highlightthickness=0, height=250)
        scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Store entry widgets for each co-analyte
        co_analyte_entries = []
        
        def create_co_analyte_row(index, co_analyte=None):
            """Create a row of inputs for a single co-analyte"""
            row_frame = ttk.Frame(scrollable_frame)
            row_frame.pack(fill='x', pady=2)
            
            # Element entry
            ttk.Label(row_frame, text="Element:", width=8).pack(side='left', padx=(0,5))
            element_entry = ttk.Entry(row_frame, width=6)
            element_entry.pack(side='left', padx=(0,10))
            
            # Base unit entry
            ttk.Label(row_frame, text="Base Unit:", width=9).pack(side='left', padx=(0,5))
            base_unit_entry = ttk.Entry(row_frame, width=8)
            base_unit_entry.pack(side='left', padx=(0,10))
            
            # Reported unit entry
            ttk.Label(row_frame, text="Report Unit:", width=10).pack(side='left', padx=(0,5))
            reported_unit_entry = ttk.Entry(row_frame, width=8)
            reported_unit_entry.pack(side='left', padx=(0,10))
            
            # Delete button
            def delete_row():
                row_frame.destroy()
                co_analyte_entries.remove(entry_set)
                canvas.configure(scrollregion=canvas.bbox("all"))
            
            delete_btn = ttk.Button(row_frame, text="×", width=3, command=delete_row)
            delete_btn.pack(side='left', padx=(5,0))
            
            # Pre-fill if editing existing co-analyte
            if co_analyte:
                element_entry.insert(0, co_analyte.get('element', ''))
                base_unit_entry.insert(0, co_analyte.get('base_unit', ''))
                reported_unit_entry.insert(0, co_analyte.get('reported_unit', ''))
            
            entry_set = {
                'frame': row_frame,
                'element': element_entry,
                'base_unit': base_unit_entry,
                'reported_unit': reported_unit_entry
            }
            co_analyte_entries.append(entry_set)
            
            return entry_set
        
        # Create rows for existing co-analytes
        for i, co_analyte in enumerate(co_list):
            create_co_analyte_row(i, co_analyte)
        
        # If no existing co-analytes, create one empty row
        if not co_list:
            create_co_analyte_row(0)
        
        # Button frame
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill='x', pady=(10,0))
        
        # Add new co-analyte button
        def add_new_row():
            create_co_analyte_row(len(co_analyte_entries))
            canvas.configure(scrollregion=canvas.bbox("all"))
            # Scroll to bottom to show new row
            canvas.yview_moveto(1.0)
        
        ttk.Button(button_frame, text="Add Co-analyte", command=add_new_row).pack(side='left')
        
        # Save and Cancel buttons
        def save_co_analytes():
            """Save the co-analytes back to the data structure"""
            new_co_analytes = []
            
            for entry_set in co_analyte_entries:
                element = entry_set['element'].get().strip()
                base_unit = entry_set['base_unit'].get().strip()
                reported_unit = entry_set['reported_unit'].get().strip()
                
                # Only add if all fields have values
                if element and base_unit and reported_unit:
                    new_co_analytes.append({
                        'element': element,
                        'base_unit': base_unit,
                        'reported_unit': reported_unit
                    })
            
            # Update the data
            self.assay_data[assay_name]['co_analytes'] = new_co_analytes
            
            # Close window
            editor_window.destroy()
            
            # Show confirmation
            messagebox.showinfo("Saved", f"Co-analytes updated for {assay_name}")
        
        def cancel_edit():
            editor_window.destroy()
        
        ttk.Button(button_frame, text="Save", command=save_co_analytes).pack(side='right', padx=(5,0))
        ttk.Button(button_frame, text="Cancel", command=cancel_edit).pack(side='right')
        
        # Bind mousewheel to canvas
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        
        # Center the window
        editor_window.update_idletasks()
        x = (editor_window.winfo_screenwidth() // 2) - (editor_window.winfo_width() // 2)
        y = (editor_window.winfo_screenheight() // 2) - (editor_window.winfo_height() // 2)
        editor_window.geometry(f"+{x}+{y}")
        
        # Focus on first element entry if available
        if co_analyte_entries:
            co_analyte_entries[0]['element'].focus()

    def render_assays(self):
        # Clear existing widgets
        for widget in self.assay_list_frame.winfo_children():
            widget.destroy()
        
        # Create canvas and scrollbar
        canvas = tk.Canvas(self.assay_list_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.assay_list_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        # Configure scrolling
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        # Create the window in the canvas
        canvas_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        
        # Configure canvas to update scrollable_frame width when canvas width changes
        def configure_canvas(event):
            canvas.itemconfig(canvas_window, width=event.width)
        
        canvas.bind('<Configure>', configure_canvas)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Pack canvas and scrollbar
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Render assays in the scrollable frame
        for assay_name in sorted(self.assay_data):
            frame = ttk.LabelFrame(scrollable_frame, text=assay_name)
            frame.pack(fill='x', padx=10, pady=5)

            row = 0

            def label_entry(key, default=''):
                nonlocal row
                ttk.Label(frame, text=key, font=self.font).grid(row=row, column=0, sticky='w')
                ent = ttk.Entry(frame, width=20)
                ent.grid(row=row, column=1)
                ent.insert(0, self.assay_data[assay_name].get(key, default))
                self.setup_auto_save_for_entry(ent, f'{assay_name}.{key}')
                self.entries[f'{assay_name}.{key}'] = ent
                row += 1

            label_entry('element')
            label_entry('base_unit')
            label_entry('reported_unit')

            # Cutoffs
            ttk.Label(frame, text="cutoffs").grid(row=row, column=0, sticky='w')
            cutoff_ent = ttk.Entry(frame, width=20)
            cutoff_ent.insert(0, ', '.join(map(str, self.assay_data[assay_name].get('cutoffs', []))))
            cutoff_ent.grid(row=row, column=1)
            self.setup_auto_save_for_entry(cutoff_ent, f'{assay_name}.cutoffs')
            self.entries[f'{assay_name}.cutoffs'] = cutoff_ent
            row += 1

            # Co-analytes button
            def edit_co_analytes(assay=assay_name):
                self.open_co_analytes_editor(assay)
            ttk.Button(frame, text="Edit Co-analytes", command=edit_co_analytes).grid(row=0, column=2, columnspan=1, pady=(5,0))
            row += 1
            
            # Delete assay button
            def delete_assay(assay=assay_name):
                result = messagebox.askyesno(
                    "Delete Assay", 
                    f"Are you sure you want to delete the assay '{assay}'?\nThis action cannot be undone."
                )
                if result:
                    # Remove from assay_data dictionary
                    if assay in self.assay_data:
                        del self.assay_data[assay]
                    
                    # Remove related entries from self.entries
                    entries_to_remove = [key for key in self.entries.keys() if key.startswith(f'{assay}.')]
                    for key in entries_to_remove:
                        del self.entries[key]
                    
                    # Refresh the display
                    self.render_assays()
                    messagebox.showinfo("Deleted", f"Assay '{assay}' has been deleted.")
            
            ttk.Button(frame, text="Delete Assay", command=delete_assay, 
                    style="Toolbutton").grid(row=1, column=2, columnspan=1, pady=(5,0))
            row += 1

        # Bind mousewheel to canvas for smooth scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        
        canvas.bind_all("<MouseWheel>", _on_mousewheel)  # Windows
        canvas.bind_all("<Button-4>", lambda e: canvas.yview_scroll(-1, "units"))  # Linux
        canvas.bind_all("<Button-5>", lambda e: canvas.yview_scroll(1, "units"))   # Linux

    def load_config(self):
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'r') as f:
                self.data = toml.load(f)
        else:
            self.data = {'settings': {}}

        if os.path.exists(ASSAY_CONFIG_PATH):
            with open(ASSAY_CONFIG_PATH, 'r') as f:
                self.assay_data = toml.load(f)
        else:
            self.assay_data = {}

        self.render_assays()


        s = self.data['settings']

        self.main_entries['hole_selections'].config(text=str(s.get('hole_selections', ['*'])))
        self.main_entries['queries_to_run'].config(text=str(s.get('queries_to_run', ['*'])))
        self.main_entries['seperate_assay_files'].set(s.get('seperate_assay_files', False))

        self.main_entries['exported_data_path'].delete(0, tk.END)
        self.main_entries['exported_data_path'].insert(0, s.get('exported_data_path', ''))

        self.main_entries['sample_id_column_name'].delete(0, tk.END)
        self.main_entries['sample_id_column_name'].insert(0, s.get('sample_id_column_name', ''))

        self.main_entries['internal_dilution_intervals'].delete(0, tk.END)
        self.main_entries['internal_dilution_intervals'].insert(0, s.get('internal_dilution_intervals', 2))

        self.main_entries['hole_id_column_name'].delete(0, tk.END)
        self.main_entries['hole_id_column_name'].insert(0, s.get('hole_id_column_name', ''))

        self.main_entries['to_column_name'].delete(0, tk.END)
        self.main_entries['to_column_name'].insert(0, s.get('to_column_name', 'To'))

        self.main_entries['from_column_name'].delete(0, tk.END)
        self.main_entries['from_column_name'].insert(0, s.get('from_column_name', 'From'))

        self.main_entries['cache_location'].delete(0, tk.END)
        self.main_entries['cache_location'].insert(0, s.get('cache_location', './cache'))

    def save_config(self, silent=True):
        s = self.data['settings']
        s['seperate_assay_files'] = self.main_entries['seperate_assay_files'].get()
        s['exported_data_path'] = self.main_entries['exported_data_path'].get()
        s['sample_id_column_name'] = self.main_entries['sample_id_column_name'].get()
        s['hole_id_column_name'] = self.main_entries['hole_id_column_name'].get()
        s['cache_location'] = self.main_entries['cache_location'].get()
        s['internal_dilution_intervals'] = int(self.main_entries['internal_dilution_intervals'].get())
        s['from_column_name'] = self.main_entries['from_column_name'].get()
        s['to_column_name'] = self.main_entries['to_column_name'].get()

        with open(CONFIG_PATH, 'w') as f:
            toml.dump(self.data, f)

        with open(ASSAY_CONFIG_PATH, 'w') as f:
            toml.dump(self.assay_data, f)

        if not silent:
            messagebox.showinfo("Success", f"Configuration saved.")

        force_reload_global_config()
        self.unsaved_changes = False


if __name__ == '__main__':
    from ttkthemes import ThemedTk
    window = ThemedTk(theme="ubuntu")
    custom_font = tkFont.Font( size=12)
    app = ConfigEditor(window, custom_font)
    window.mainloop()
