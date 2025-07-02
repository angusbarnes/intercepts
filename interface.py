import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
import toml
import os


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
    def __init__(self, root):
        self.root = root
        self.root.title("TOML Configuration Editor")
        self.data = {}
        self.entries = {}

        self.notebook = ttk.Notebook(root)
        self.settings_frame = ttk.Frame(self.notebook)
        self.assay_frame = ttk.Frame(self.notebook)

        self.notebook.add(self.settings_frame, text='Settings')
        self.notebook.add(self.assay_frame, text='Assays')
        self.notebook.pack(expand=1, fill='both')

        self.build_settings_tab()
        self.build_assay_tab()
        self.load_config()

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
            self.entries[key] = ent
            row += 1

        def add_checkbox(key, label):
            nonlocal row
            var = tk.BooleanVar()
            chk = ttk.Checkbutton(frm, text=label, variable=var)
            chk.grid(row=row, column=0, columnspan=2, sticky='w')
            self.entries[key] = var
            row += 1

        def add_list_editor(key, label):
            nonlocal row
            def edit_list():
                current = self.data['settings'].get(key, ['*'])
                val = simpledialog.askstring("Edit list", f"Comma-separated list for {key}:", 
                                             initialvalue=', '.join(current))
                if val is not None:
                    self.data['settings'][key] = [v.strip() for v in val.split(',') if v.strip()]
                    self.entries[key].config(text=str(self.data['settings'][key]))

            ttk.Label(frm, text=label).grid(row=row, column=0, sticky='w')
            btn = ttk.Button(frm, text="Edit", command=edit_list)
            btn.grid(row=row, column=1, sticky='w')
            self.entries[key] = btn
            row += 1

        # Add fields
        add_list_editor('hole_selections', 'Hole Selections')
        add_list_editor('queries_to_run', 'Queries to Run')
        add_checkbox('seperate_assay_files', 'Separate Assay Files')
        add_entry('exported_data_path', 'Exported CSV Path', is_path=True)
        add_entry('sample_id_column_name', 'Sample ID Column')
        add_entry('hole_id_column_name', 'Hole ID Column')
        add_entry('cache_location', 'Cache Location')

        # Buttons
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(pady=(10, 0))
        ttk.Button(btn_frame, text="Load", command=self.load_config).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Save", command=self.save_config).pack(side=tk.LEFT, padx=5)



    def build_assay_tab(self):
        self.assay_list_frame = ttk.Frame(self.assay_frame)
        self.assay_list_frame.pack(fill='both', expand=True)

        self.assay_controls = ttk.Frame(self.assay_frame)
        self.assay_controls.pack(fill='x', pady=5)

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

    def render_assays(self):
        for widget in self.assay_list_frame.winfo_children():
            widget.destroy()

        for assay_name in sorted(k for k in self.assay_data if k.endswith('_assay')):
            frame = ttk.LabelFrame(self.assay_list_frame, text=assay_name)
            frame.pack(fill='x', padx=10, pady=5)

            row = 0

            def label_entry(key, default=''):
                nonlocal row
                ttk.Label(frame, text=key).grid(row=row, column=0, sticky='w')
                ent = ttk.Entry(frame, width=20)
                ent.grid(row=row, column=1)
                ent.insert(0, self.assay_data[assay_name].get(key, default))
                self.entries[f'{assay_name}.{key}'] = ent
                row += 1

            label_entry('element')
            label_entry('base_unit')
            label_entry('reported_unit')

            # Cutoffs
            ttk.Label(frame, text="cutoffs").grid(row=row, column=0, sticky='w')
            cutoff_ent = ttk.Entry(frame, width=30)
            cutoff_ent.insert(0, ', '.join(map(str, self.assay_data[assay_name].get('cutoffs', []))))
            cutoff_ent.grid(row=row, column=1)
            self.entries[f'{assay_name}.cutoffs'] = cutoff_ent
            row += 1

            # Co-analytes button
            def edit_co_analytes(assay=assay_name):
                co_list = self.assay_data[assay].get('co_analytes', [])
                new_str = simpledialog.askstring(
                    "Edit Co-Analytes",
                    "Enter list in format: El:Unit->ReportUnit, comma separated\nExample: Au:ppm->ppm",
                    initialvalue=', '.join(f"{c['element']}:{c['base_unit']}->{c['reported_unit']}" for c in co_list)
                )
                if new_str is not None:
                    try:
                        parsed = []
                        for item in new_str.split(','):
                            el, units = item.strip().split(':')
                            base, rep = units.split('->')
                            parsed.append({
                                'element': el.strip(),
                                'base_unit': base.strip(),
                                'reported_unit': rep.strip()
                            })
                        self.data[assay]['co_analytes'] = parsed
                        messagebox.showinfo("Saved", "Co-analytes updated.")
                    except Exception:
                        messagebox.showerror("Error", "Invalid format.")
            ttk.Button(frame, text="Edit Co-analytes", command=edit_co_analytes).grid(row=row, column=0, columnspan=2)
            row += 1

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


        s = self.data['settings']

        self.entries['hole_selections'].config(text=str(s.get('hole_selections', ['*'])))
        self.entries['queries_to_run'].config(text=str(s.get('queries_to_run', ['*'])))
        self.entries['seperate_assay_files'].set(s.get('seperate_assay_files', False))

        self.entries['exported_data_path'].delete(0, tk.END)
        self.entries['exported_data_path'].insert(0, s.get('exported_data_path', ''))

        self.entries['sample_id_column_name'].delete(0, tk.END)
        self.entries['sample_id_column_name'].insert(0, s.get('sample_id_column_name', ''))

        self.entries['hole_id_column_name'].delete(0, tk.END)
        self.entries['hole_id_column_name'].insert(0, s.get('hole_id_column_name', ''))

        self.entries['cache_location'].delete(0, tk.END)
        self.entries['cache_location'].insert(0, s.get('cache_location', './cache'))

    def save_config(self):
        s = self.data['settings']
        s['seperate_assay_files'] = self.entries['seperate_assay_files'].get()
        s['exported_data_path'] = self.entries['exported_data_path'].get()
        s['sample_id_column_name'] = self.entries['sample_id_column_name'].get()
        s['hole_id_column_name'] = self.entries['hole_id_column_name'].get()
        s['cache_location'] = self.entries['cache_location'].get()

        with open(CONFIG_PATH, 'w') as f:
            toml.dump(self.data, f)

        with open(ASSAY_CONFIG_PATH, 'w') as f:
            toml.dump(self.assay_data, f)

        messagebox.showinfo("Success", f"Configuration saved to {CONFIG_PATH}.")


if __name__ == '__main__':
    root = tk.Tk()
    app = ConfigEditor(root)
    root.mainloop()
