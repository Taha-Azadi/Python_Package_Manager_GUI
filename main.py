"""
Python Library Manager (GUI) — v1.0.1
----------------------------------
A Python package install/uninstall manager built with customtkinter.

Features:
  - Python interpreter/version selection from dropdown (auto-detects all
    installed versions on the system; on Windows also uses py launcher)
  - Install/uninstall runs with the exact selected Python interpreter
  - Refresh button to re-scan interpreters
  - Upgrade (--upgrade) and --user checkboxes
  - Import from requirements.txt and Export installed packages to requirements.txt
  - Upgrade pip button
  - Non-blocking execution (Thread) with live output in log
  - subprocess with argument list (no os.system) => safe against command injection
  - Package name validation with regex
  - Log saved to file and log copied to clipboard
  - Color status, indeterminate progress bar, button disabling during execution
  - Icon download with error handling (no internet won't crash)
  - PyPI Search: fetch latest version, description, link, download count
  - Installed Packages Panel: list on the left, click to show Version, Home Page, Author, License
  - Update Checker: compare installed version with latest on PyPI
  - Package Details: Author, License, Homepage, Summary, Dependencies
  - Virtual Environment: create venv inside the app
  - Requirements Compare: compare two requirements.txt files
  - Dependency Tree: like pipdeptree
  - Dark / Light Mode toggle
  - Auto Complete: package name suggestions as you type
"""

import os
import re
import sys
import glob
import shutil
import threading
import subprocess
import urllib.request
import urllib.error
from datetime import datetime

import customtkinter as ctk
from tkinter.messagebox import showinfo, showerror
from tkinter.filedialog import askopenfilename, asksaveasfilename

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


# Only letters/numbers/dot/underscore/hyphen and == >= <= for version allowed
PACKAGE_PATTERN = re.compile(r"^[A-Za-z0-9._-]+((==|>=|<=)[A-Za-z0-9._-]+)?$")


def get_version_label(python_path: str) -> str:
    """Return python --version output, empty string on error."""
    try:
        result = subprocess.run(
            [python_path, "--version"],
            capture_output=True, text=True, timeout=5,
        )
        out = (result.stdout or result.stderr).strip()
        return out
    except Exception:
        return ""


def detect_python_interpreters() -> dict:
    """
    Returns dict: label -> path
    label looks like "Python 3.12.1  (C:\\...\\python.exe)"
    """
    found = {}

    def add(path: str):
        if not path or not os.path.exists(path):
            return
        real = os.path.realpath(path)
        if any(os.path.realpath(p) == real for p in found.values()):
            return
        label = get_version_label(path)
        if not label:
            return
        found[f"{label}   —   {path}"] = path

    # Always add current interpreter
    add(sys.executable)

    if os.name == "nt":
        # On Windows use py launcher to list all installed versions
        try:
            result = subprocess.run(
                ["py", "-0p"], capture_output=True, text=True, timeout=5
            )
            for line in (result.stdout or "").splitlines():
                line = line.strip()
                if not line:
                    continue
                parts = line.split()
                candidate = parts[-1] if parts else ""
                if candidate.lower().endswith("python.exe"):
                    add(candidate)
        except Exception:
            pass
        # Also check common paths
        for pattern in (
            r"C:\Python*\python.exe",
            r"C:\Program Files\Python*\python.exe",
            os.path.expanduser(r"~\AppData\Local\Programs\Python\Python*\python.exe"),
        ):
            for p in glob.glob(pattern):
                add(p)
    else:
        # Linux/Mac: common names in PATH
        for name in [
            "python3", "python", "python3.9", "python3.10",
            "python3.11", "python3.12", "python3.13",
        ]:
            p = shutil.which(name)
            if p:
                add(p)
        for pattern in ("/usr/bin/python3*", "/usr/local/bin/python3*",
                        "/opt/homebrew/bin/python3*"):
            for p in glob.glob(pattern):
                add(p)

    return found


def fetch_pypi_info(package_name: str) -> dict:
    """Fetch package info from PyPI JSON API. Returns empty dict on failure."""
    try:
        import json
        url = f"https://pypi.org/pypi/{package_name}/json"
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            info = data.get("info", {})
            downloads = -1
            try:
                # Try to get total downloads from pypistats API
                stats_url = f"https://pypistats.org/api/packages/{package_name}/overall"
                with urllib.request.urlopen(stats_url, timeout=8) as stats_resp:
                    stats_data = json.loads(stats_resp.read().decode("utf-8"))
                    downloads = sum(item.get("downloads", 0) for item in stats_data.get("data", []))
            except Exception:
                pass
            return {
                "name": info.get("name", package_name),
                "version": info.get("version", "Unknown"),
                "summary": info.get("summary", "No description available."),
                "home_page": info.get("home_page", ""),
                "author": info.get("author", "Unknown"),
                "license": info.get("license", "Unknown"),
                "description": info.get("description", ""),
                "downloads": downloads,
                "url": f"https://pypi.org/project/{package_name}/",
                "requires_dist": info.get("requires_dist", []),
            }
    except Exception:
        return {}


def fetch_pypi_downloads(package_name: str) -> int:
    """Fetch total downloads from pypistats API. Returns -1 on failure."""
    try:
        import json
        url = f"https://pypistats.org/api/packages/{package_name}/overall"
        with urllib.request.urlopen(url, timeout=8) as response:
            data = json.loads(response.read().decode("utf-8"))
            return sum(item.get("downloads", 0) for item in data.get("data", []))
    except Exception:
        return -1


class LibManagerApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Python Library Manager v1.0.1")
        self.geometry("1000x750")
        self.minsize(900, 650)

        self._busy = False
        self.interpreters = {}  # label -> path
        self.current_python_path = sys.executable
        self.installed_packages = {}  # name -> {version, home_page, author, license}
        self.pypi_cache = {}  # name -> info dict
        self.autocomplete_list = []  # list of package names for autocomplete

        self._build_ui()
        self.refresh_interpreters()

    # ---------------------------------------------------------- UI ----
    def _build_ui(self):
        # Main container with left panel and right content
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ========== LEFT SIDEBAR: Installed Packages Panel ==========
        self.sidebar = ctk.CTkFrame(self, width=220)
        self.sidebar.grid(row=0, column=0, sticky="nswe", padx=(10, 0), pady=10)
        self.sidebar.grid_rowconfigure(2, weight=1)
        self.sidebar.grid_propagate(False)

        ctk.CTkLabel(
            self.sidebar, text="Installed Packages",
            font=ctk.CTkFont(size=14, weight="bold")
        ).grid(row=0, column=0, pady=(10, 5), padx=10)

        self.pkg_search_var = ctk.StringVar()
        self.pkg_search_var.trace_add("write", self._filter_installed_packages)
        self.pkg_search_entry = ctk.CTkEntry(
            self.sidebar, placeholder_text="Search installed...", textvariable=self.pkg_search_var
        )
        self.pkg_search_entry.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 5))

        self.pkg_listbox = ctk.CTkScrollableFrame(self.sidebar)
        self.pkg_listbox.grid(row=2, column=0, sticky="nswe", padx=10, pady=(0, 10))
        self.pkg_listbox.grid_columnconfigure(0, weight=1)

        ctk.CTkButton(
            self.sidebar, text="Refresh List", command=self.refresh_installed_packages
        ).grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 5))

        ctk.CTkButton(
            self.sidebar, text="Check Updates", command=self.check_all_updates
        ).grid(row=4, column=0, sticky="ew", padx=10, pady=(0, 10))

        # ========== RIGHT CONTENT ==========
        self.content = ctk.CTkFrame(self)
        self.content.grid(row=0, column=1, sticky="nswe", padx=10, pady=10)
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(3, weight=1)

        # ---- Header ----
        header = ctk.CTkFrame(self.content, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 10))

        ctk.CTkLabel(
            header, text="📦 Python Library Manager",
            font=ctk.CTkFont(size=20, weight="bold")
        ).pack(anchor="w")

        ctk.CTkLabel(
            header,
            text="Enter one or more package names (separate with space or comma). "
                 "Use == >= <= for versions, e.g. requests==2.31.0",
            font=ctk.CTkFont(size=12),
            text_color="gray70",
            wraplength=640,
            justify="left",
        ).pack(anchor="w", pady=(4, 0))

        # ---- Theme Toggle ----
        self.theme_btn = ctk.CTkButton(
            header, text="☀ Light Mode", width=110, command=self.toggle_theme
        )
        self.theme_btn.pack(anchor="e", side="right")

        # ---- Python interpreter selection ----
        py_frame = ctk.CTkFrame(self.content)
        py_frame.grid(row=1, column=0, sticky="ew", padx=20, pady=(10, 5))

        ctk.CTkLabel(py_frame, text="🐍 Python interpreter:",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(
            side="left", padx=(12, 8), pady=10
        )

        self.python_var = ctk.StringVar(value="Searching...")
        self.python_menu = ctk.CTkOptionMenu(
            py_frame, variable=self.python_var,
            values=["Searching..."],
            command=self.on_interpreter_selected,
            width=380,
        )
        self.python_menu.pack(side="left", padx=8, pady=10, fill="x", expand=True)

        ctk.CTkButton(
            py_frame, text="🔄 Refresh", width=90,
            command=self.refresh_interpreters,
        ).pack(side="left", padx=(8, 12), pady=10)

        # ---- PyPI Search ----
        pypi_frame = ctk.CTkFrame(self.content)
        pypi_frame.grid(row=2, column=0, sticky="ew", padx=20, pady=(5, 5))

        ctk.CTkLabel(pypi_frame, text="🔍 PyPI Search:",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(
            side="left", padx=(12, 8), pady=10
        )

        self.pypi_search_var = ctk.StringVar()
        self.pypi_search_var.trace_add("write", self._on_pypi_search_change)
        self.pypi_search_entry = ctk.CTkEntry(
            pypi_frame, placeholder_text="e.g. requests", textvariable=self.pypi_search_var,
            width=250
        )
        self.pypi_search_entry.pack(side="left", padx=8, pady=10)

        self.autocomplete_frame = ctk.CTkFrame(pypi_frame, fg_color="transparent")
        self.autocomplete_frame.pack(side="left", padx=0, pady=10)

        ctk.CTkButton(
            pypi_frame, text="Search", width=80, command=self.on_pypi_search
        ).pack(side="left", padx=8, pady=10)

        # ---- Package entry with autocomplete ----
        entry_frame = ctk.CTkFrame(self.content, fg_color="transparent")
        entry_frame.grid(row=3, column=0, sticky="ew", padx=20, pady=5)

        self.ent = ctk.CTkEntry(
            entry_frame, placeholder_text="e.g. numpy pandas requests==2.31.0",
            height=38,
        )
        self.ent.pack(side="left", fill="x", expand=True)
        self.ent.bind("<Return>", lambda e: self.on_install())
        self.ent.bind("<KeyRelease>", self._on_entry_keyrelease)

        # Autocomplete dropdown frame
        self.autocomplete_popup = ctk.CTkFrame(self.content)
        self.autocomplete_popup.grid(row=4, column=0, sticky="w", padx=20)
        self.autocomplete_popup.grid_remove()

        # ---- Checkboxes ----
        opts_frame = ctk.CTkFrame(self.content, fg_color="transparent")
        opts_frame.grid(row=5, column=0, sticky="ew", padx=20, pady=(2, 5))

        self.upgrade_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            opts_frame, text="Upgrade (--upgrade)", variable=self.upgrade_var
        ).pack(side="left", padx=(0, 20))

        self.user_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            opts_frame, text="Install to user site (--user)", variable=self.user_var
        ).pack(side="left")

        # ---- Main buttons ----
        btn_frame = ctk.CTkFrame(self.content, fg_color="transparent")
        btn_frame.grid(row=6, column=0, sticky="ew", padx=20, pady=(5, 5))

        self.btn_install = ctk.CTkButton(
            btn_frame, text="⬇ Install", command=self.on_install, width=100
        )
        self.btn_install.pack(side="left", padx=(0, 8))

        self.btn_uninstall = ctk.CTkButton(
            btn_frame, text="🗑 Uninstall", command=self.on_uninstall,
            width=100, fg_color="#a13d3d", hover_color="#812f2f",
        )
        self.btn_uninstall.pack(side="left", padx=8)

        self.btn_list = ctk.CTkButton(
            btn_frame, text="📋 List installed", command=self.on_list, width=120
        )
        self.btn_list.pack(side="left", padx=8)

        self.btn_pip_upgrade = ctk.CTkButton(
            btn_frame, text="⇧ Upgrade pip", command=self.on_upgrade_pip, width=110
        )
        self.btn_pip_upgrade.pack(side="left", padx=8)

        # ---- requirements.txt buttons ----
        req_frame = ctk.CTkFrame(self.content, fg_color="transparent")
        req_frame.grid(row=7, column=0, sticky="ew", padx=20, pady=(0, 8))

        self.btn_import_req = ctk.CTkButton(
            req_frame, text="📥 Install from requirements.txt",
            command=self.on_import_requirements, width=230,
        )
        self.btn_import_req.pack(side="left", padx=(0, 8))

        self.btn_export_req = ctk.CTkButton(
            req_frame, text="📤 Export installed to requirements.txt",
            command=self.on_export_requirements, width=260,
        )
        self.btn_export_req.pack(side="left", padx=8)

        # ---- Extra features buttons ----
        extra_frame = ctk.CTkFrame(self.content, fg_color="transparent")
        extra_frame.grid(row=8, column=0, sticky="ew", padx=20, pady=(0, 8))

        ctk.CTkButton(
            extra_frame, text="🌳 Dependency Tree", width=160,
            command=self.on_dependency_tree,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            extra_frame, text="📑 Compare Requirements", width=180,
            command=self.on_compare_requirements,
        ).pack(side="left", padx=8)

        ctk.CTkButton(
            extra_frame, text="🧪 Create Venv", width=130,
            command=self.on_create_venv,
        ).pack(side="left", padx=8)

        # ---- Progress & Status ----
        self.progress = ctk.CTkProgressBar(self.content, mode="indeterminate")
        self.progress.grid(row=9, column=0, sticky="ew", padx=20, pady=(2, 5))
        self.progress.stop()

        self.status_lbl = ctk.CTkLabel(self.content, text="Ready", font=ctk.CTkFont(size=12))
        self.status_lbl.grid(row=10, column=0, sticky="w", padx=20)

        # ---- Log box ----
        self.log_box = ctk.CTkTextbox(self.content, font=ctk.CTkFont(family="Consolas", size=12))
        self.log_box.grid(row=11, column=0, sticky="nswe", padx=20, pady=(8, 5))
        self.log_box.configure(state="disabled")

        # ---- Log buttons ----
        log_btn_frame = ctk.CTkFrame(self.content, fg_color="transparent")
        log_btn_frame.grid(row=12, column=0, sticky="ew", padx=20, pady=(0, 20))

        ctk.CTkButton(
            log_btn_frame, text="Clear log", width=100, fg_color="gray30",
            hover_color="gray20", command=self.clear_log,
        ).pack(side="right", padx=(8, 0))

        ctk.CTkButton(
            log_btn_frame, text="💾 Save log", width=100, fg_color="gray30",
            hover_color="gray20", command=self.save_log,
        ).pack(side="right", padx=(8, 0))

        ctk.CTkButton(
            log_btn_frame, text="📋 Copy log", width=100, fg_color="gray30",
            hover_color="gray20", command=self.copy_log,
        ).pack(side="right")

        # ---- Package Details Panel (hidden by default, shown on package click) ----
        self.details_window = None

        # Load autocomplete suggestions
        self._load_autocomplete_suggestions()

        # Initial load of installed packages
        self.refresh_installed_packages()

    # ------------------------------------------------------- helpers ----
    def log(self, text: str):
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log_box.configure(state="normal")
        line = text if text.endswith("\n") else text + "\n"
        self.log_box.insert("end", f"[{stamp}] {line}")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def clear_log(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    def copy_log(self):
        content = self.log_box.get("1.0", "end")
        self.clipboard_clear()
        self.clipboard_append(content)
        showinfo("Copied", "Log content copied to clipboard.")

    def save_log(self):
        path = asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text file", "*.txt"), ("All files", "*.*")],
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.log_box.get("1.0", "end"))
        showinfo("Saved", f"Log saved to:\n{path}")

    def parse_packages(self) -> list:
        raw = self.ent.get().strip()
        if not raw:
            showinfo("Error", "Please enter a package name first.")
            return []
        parts = [p.strip() for p in re.split(r"[,\s]+", raw) if p.strip()]
        invalid = [p for p in parts if not PACKAGE_PATTERN.match(p)]
        if invalid:
            showerror(
                "Invalid Name",
                "These inputs are not allowed:\n" + ", ".join(invalid) +
                "\n\nOnly letters/numbers/._- and == >= <= for version are allowed."
            )
            return []
        return parts

    def set_busy(self, busy: bool):
        self._busy = busy
        state = "disabled" if busy else "normal"
        for b in (self.btn_install, self.btn_uninstall, self.btn_list,
                  self.btn_pip_upgrade, self.btn_import_req, self.btn_export_req,
                  self.python_menu):
            b.configure(state=state)
        if busy:
            self.progress.start()
        else:
            self.progress.stop()

    def run_command_async(self, cmd: list, on_done_message: str):
        if self._busy:
            return
        self.set_busy(True)
        self.status_lbl.configure(text="Running...", text_color="#e0b23c")
        self.log(f"$ {' '.join(cmd)}")

        def worker():
            success = False
            try:
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
                for line in process.stdout:
                    self.after(0, self.log, line.rstrip())
                process.wait()
                success = process.returncode == 0
            except Exception as e:
                self.after(0, self.log, f"Error: {e}")

            def finish():
                self.set_busy(False)
                if success:
                    self.status_lbl.configure(text=on_done_message, text_color="#4caf50")
                else:
                    self.status_lbl.configure(text="Operation failed ❌", text_color="#e05555")
                # Refresh installed packages after any operation
                self.refresh_installed_packages()

            self.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()

    # ----------------------------------------------- Python selection ----
    def refresh_interpreters(self):
        self.status_lbl.configure(text="Searching for Python versions...", text_color="#e0b23c")

        def worker():
            found = detect_python_interpreters()

            def apply():
                self.interpreters = found
                labels = list(found.keys()) or ["No Python found"]
                self.python_menu.configure(values=labels)
                current_label = next(
                    (lbl for lbl, path in found.items()
                     if os.path.realpath(path) == os.path.realpath(sys.executable)),
                    labels[0],
                )
                self.python_var.set(current_label)
                self.on_interpreter_selected(current_label)
                self.status_lbl.configure(
                    text=f"{len(found)} Python version(s) found ✅", text_color="#4caf50"
                )

            self.after(0, apply)

        threading.Thread(target=worker, daemon=True).start()

    def on_interpreter_selected(self, label: str):
        path = self.interpreters.get(label)
        if path:
            self.current_python_path = path
            self.log(f"Selected interpreter: {label}")
            self.refresh_installed_packages()

    # --------------------------------------------------------- actions ----
    def _pip_base_cmd(self):
        return [self.current_python_path, "-m", "pip"]

    def on_install(self):
        packages = self.parse_packages()
        if not packages:
            return
        cmd = self._pip_base_cmd() + ["install"]
        if self.upgrade_var.get():
            cmd.append("--upgrade")
        if self.user_var.get():
            cmd.append("--user")
        cmd += packages
        self.run_command_async(cmd, f"Installed: {', '.join(packages)} ✅")

    def on_uninstall(self):
        packages = self.parse_packages()
        if not packages:
            return
        cmd = self._pip_base_cmd() + ["uninstall", "-y"] + packages
        self.run_command_async(cmd, f"Uninstalled: {', '.join(packages)} ✅")

    def on_list(self):
        cmd = self._pip_base_cmd() + ["list"]
        self.run_command_async(cmd, "Package list displayed ✅")

    def on_upgrade_pip(self):
        cmd = self._pip_base_cmd() + ["install", "--upgrade", "pip"]
        self.run_command_async(cmd, "pip upgraded ✅")

    def on_import_requirements(self):
        path = askopenfilename(
            title="Select requirements.txt",
            filetypes=[("Requirements file", "*.txt"), ("All files", "*.*")],
        )
        if not path:
            return
        cmd = self._pip_base_cmd() + ["install", "-r", path]
        if self.upgrade_var.get():
            cmd.append("--upgrade")
        self.run_command_async(cmd, f"Install from {os.path.basename(path)} completed ✅")

    def on_export_requirements(self):
        path = asksaveasfilename(
            title="Save as requirements.txt",
            defaultextension=".txt",
            initialfile="requirements.txt",
            filetypes=[("Requirements file", "*.txt"), ("All files", "*.*")],
        )
        if not path:
            return
        if self._busy:
            return
        self.set_busy(True)
        self.status_lbl.configure(text="Creating requirements.txt...", text_color="#e0b23c")
        cmd = self._pip_base_cmd() + ["freeze"]
        self.log(f"$ {' '.join(cmd)}  >  {path}")

        def worker():
            success = False
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(result.stdout)
                success = result.returncode == 0
                self.after(0, self.log, result.stdout)
            except Exception as e:
                self.after(0, self.log, f"Error: {e}")

            def finish():
                self.set_busy(False)
                if success:
                    self.status_lbl.configure(
                        text=f"Saved: {os.path.basename(path)} ✅", text_color="#4caf50"
                    )
                else:
                    self.status_lbl.configure(text="Error creating file ❌", text_color="#e05555")

            self.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()

    # =========================================================
    # NEW FEATURES v1.0.1
    # =========================================================

    # ---- 1. PyPI Search ----
    def on_pypi_search(self):
        query = self.pypi_search_var.get().strip()
        if not query:
            showinfo("Error", "Enter a package name to search on PyPI.")
            return

        self.set_busy(True)
        self.status_lbl.configure(text=f"Fetching PyPI info for {query}...", text_color="#e0b23c")

        def worker():
            info = fetch_pypi_info(query)

            def apply():
                self.set_busy(False)
                if not info:
                    self.status_lbl.configure(text="Failed to fetch PyPI info ❌", text_color="#e05555")
                    showerror("Error", f"Could not fetch info for '{query}' from PyPI.")
                    return

                downloads_str = "N/A"
                if info.get("downloads", -1) >= 0:
                    downloads_str = f"{info['downloads']:,}"

                msg = (
                    f"📦 {info['name']}\n"
                    f"Latest Version: {info['version']}\n"
                    f"Summary: {info['summary']}\n"
                    f"Author: {info['author']}\n"
                    f"License: {info['license']}\n"
                    f"Home Page: {info['home_page'] or 'N/A'}\n"
                    f"PyPI Link: {info['url']}\n"
                    f"Total Downloads: {downloads_str}\n"
                )
                self.log(msg)
                self.status_lbl.configure(
                    text=f"PyPI info for {query} fetched ✅", text_color="#4caf50"
                )

                # Show in details window
                self._show_package_details(info, is_pypi=True)

            self.after(0, apply)

        threading.Thread(target=worker, daemon=True).start()

    # ---- 2. Installed Packages Panel ----
    def refresh_installed_packages(self):
        self.status_lbl.configure(text="Loading installed packages...", text_color="#e0b23c")

        def worker():
            packages = {}
            try:
                result = subprocess.run(
                    self._pip_base_cmd() + ["list", "--format=json"],
                    capture_output=True, text=True, timeout=15
                )
                if result.returncode == 0:
                    import json
                    data = json.loads(result.stdout)
                    for item in data:
                        name = item.get("name", "")
                        version = item.get("version", "")
                        packages[name] = {
                            "version": version,
                            "home_page": "",
                            "author": "",
                            "license": "",
                        }
            except Exception:
                pass

            # Try to get more details with pip show
            for name in list(packages.keys())[:50]:  # Limit to avoid timeout
                try:
                    result = subprocess.run(
                        self._pip_base_cmd() + ["show", name],
                        capture_output=True, text=True, timeout=5
                    )
                    if result.returncode == 0:
                        for line in result.stdout.splitlines():
                            if line.startswith("Home-page:"):
                                packages[name]["home_page"] = line.split(":", 1)[1].strip()
                            elif line.startswith("Author:"):
                                packages[name]["author"] = line.split(":", 1)[1].strip()
                            elif line.startswith("License:"):
                                packages[name]["license"] = line.split(":", 1)[1].strip()
                except Exception:
                    pass

            def apply():
                self.installed_packages = packages
                self._render_installed_packages()
                self.status_lbl.configure(
                    text=f"{len(packages)} packages installed ✅", text_color="#4caf50"
                )

            self.after(0, apply)

        threading.Thread(target=worker, daemon=True).start()

    def _render_installed_packages(self, filter_text=""):
        # Clear existing
        for widget in self.pkg_listbox.winfo_children():
            widget.destroy()

        names = sorted(self.installed_packages.keys())
        if filter_text:
            names = [n for n in names if filter_text.lower() in n.lower()]

        for name in names:
            info = self.installed_packages[name]
            btn = ctk.CTkButton(
                self.pkg_listbox, text=f"{name}=={info['version']}",
                anchor="w", height=28,
                command=lambda n=name: self._on_package_click(n)
            )
            btn.pack(fill="x", pady=1)

    def _filter_installed_packages(self, *args):
        self._render_installed_packages(self.pkg_search_var.get())

    def _on_package_click(self, package_name: str):
        info = self.installed_packages.get(package_name, {})
        if not info:
            return

        # Fetch latest from PyPI for comparison
        self.set_busy(True)
        self.status_lbl.configure(text=f"Fetching details for {package_name}...", text_color="#e0b23c")

        def worker():
            pypi_info = fetch_pypi_info(package_name)
            latest_version = pypi_info.get("version", "Unknown") if pypi_info else "Unknown"

            def apply():
                self.set_busy(False)
                self._show_package_details({
                    "name": package_name,
                    "version": info.get("version", "Unknown"),
                    "latest_version": latest_version,
                    "summary": pypi_info.get("summary", "") if pypi_info else "",
                    "home_page": info.get("home_page", "") or (pypi_info.get("home_page", "") if pypi_info else ""),
                    "author": info.get("author", "") or (pypi_info.get("author", "") if pypi_info else ""),
                    "license": info.get("license", "") or (pypi_info.get("license", "") if pypi_info else ""),
                    "requires_dist": pypi_info.get("requires_dist", []) if pypi_info else [],
                    "url": f"https://pypi.org/project/{package_name}/",
                    "downloads": pypi_info.get("downloads", -1) if pypi_info else -1,
                }, is_pypi=False)

            self.after(0, apply)

        threading.Thread(target=worker, daemon=True).start()

    # ---- 3. Update Checker ----
    def check_all_updates(self):
        self.set_busy(True)
        self.status_lbl.configure(text="Checking for updates...", text_color="#e0b23c")
        self.log("Checking for outdated packages...")

        def worker():
            outdated = []
            try:
                result = subprocess.run(
                    self._pip_base_cmd() + ["list", "--outdated", "--format=json"],
                    capture_output=True, text=True, timeout=30
                )
                if result.returncode == 0:
                    import json
                    data = json.loads(result.stdout)
                    for item in data:
                        outdated.append({
                            "name": item.get("name", ""),
                            "current": item.get("version", ""),
                            "latest": item.get("latest_version", ""),
                        })
            except Exception as e:
                self.after(0, self.log, f"Error: {e}")

            def apply():
                self.set_busy(False)
                if not outdated:
                    self.status_lbl.configure(text="All packages are up to date ✅", text_color="#4caf50")
                    self.log("All packages are up to date!")
                    return

                self.log(f"\n{'='*50}")
                self.log("OUTDATED PACKAGES:")
                self.log(f"{'='*50}")
                for pkg in outdated:
                    self.log(f"  {pkg['name']}: {pkg['current']} → {pkg['latest']}")
                self.log(f"{'='*50}\n")

                self.status_lbl.configure(
                    text=f"{len(outdated)} update(s) available ⚠️", text_color="#e0b23c"
                )

                # Show update dialog
                self._show_update_dialog(outdated)

            self.after(0, apply)

        threading.Thread(target=worker, daemon=True).start()

    def _show_update_dialog(self, outdated: list):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Update Checker")
        dialog.geometry("500x400")
        dialog.transient(self)
        dialog.grab_set()

        ctk.CTkLabel(
            dialog, text="Available Updates", font=ctk.CTkFont(size=16, weight="bold")
        ).pack(pady=(15, 10))

        scroll = ctk.CTkScrollableFrame(dialog)
        scroll.pack(fill="both", expand=True, padx=15, pady=5)

        for pkg in outdated:
            frame = ctk.CTkFrame(scroll)
            frame.pack(fill="x", pady=2)

            ctk.CTkLabel(
                frame, text=f"{pkg['name']}", font=ctk.CTkFont(weight="bold")
            ).pack(side="left", padx=10)

            ctk.CTkLabel(
                frame, text=f"{pkg['current']} → {pkg['latest']}", text_color="gray70"
            ).pack(side="left", padx=10)

            ctk.CTkButton(
                frame, text="Update", width=80,
                command=lambda p=pkg['name']: self._update_single_package(p, dialog)
            ).pack(side="right", padx=10)

        ctk.CTkButton(
            dialog, text="Update All", width=120,
            command=lambda: self._update_all_packages(outdated, dialog)
        ).pack(pady=10)

    def _update_single_package(self, package_name: str, dialog=None):
        if dialog:
            dialog.destroy()
        cmd = self._pip_base_cmd() + ["install", "--upgrade", package_name]
        self.run_command_async(cmd, f"{package_name} updated ✅")

    def _update_all_packages(self, outdated: list, dialog=None):
        if dialog:
            dialog.destroy()
        names = [p["name"] for p in outdated]
        cmd = self._pip_base_cmd() + ["install", "--upgrade"] + names
        self.run_command_async(cmd, f"{len(names)} package(s) updated ✅")

    # ---- 4. Package Details ----
    def _show_package_details(self, info: dict, is_pypi: bool):
        if self.details_window and self.details_window.winfo_exists():
            self.details_window.destroy()

        self.details_window = ctk.CTkToplevel(self)
        self.details_window.title(f"Details: {info['name']}")
        self.details_window.geometry("500x550")
        self.details_window.transient(self)

        ctk.CTkLabel(
            self.details_window, text=f"📦 {info['name']}",
            font=ctk.CTkFont(size=18, weight="bold")
        ).pack(pady=(15, 5))

        # Version info
        version_text = f"Version: {info.get('version', 'Unknown')}"
        if not is_pypi and "latest_version" in info:
            version_text += f"  |  Latest: {info['latest_version']}"
            if info.get("version") != info.get("latest_version"):
                version_text += "  (Update available!)"
                ctk.CTkButton(
                    self.details_window, text="Update Now", width=100,
                    command=lambda: self._update_single_package(info['name'])
                ).pack(pady=5)

        ctk.CTkLabel(
            self.details_window, text=version_text, font=ctk.CTkFont(size=13)
        ).pack(pady=5)

        # Details frame
        details = ctk.CTkFrame(self.details_window)
        details.pack(fill="both", expand=True, padx=15, pady=10)

        fields = [
            ("Author", info.get("author", "Unknown")),
            ("License", info.get("license", "Unknown")),
            ("Home Page", info.get("home_page", "N/A")),
            ("Summary", info.get("summary", "N/A")),
            ("PyPI URL", info.get("url", "N/A")),
        ]

        if info.get("downloads", -1) >= 0:
            fields.append(("Total Downloads", f"{info['downloads']:,}"))

        for i, (label, value) in enumerate(fields):
            ctk.CTkLabel(
                details, text=f"{label}:", font=ctk.CTkFont(weight="bold")
            ).grid(row=i, column=0, sticky="nw", padx=10, pady=5)
            ctk.CTkLabel(
                details, text=value, wraplength=350, justify="left"
            ).grid(row=i, column=1, sticky="nw", padx=10, pady=5)

        # Dependencies
        deps = info.get("requires_dist", [])
        if deps:
            ctk.CTkLabel(
                self.details_window, text="Dependencies:",
                font=ctk.CTkFont(weight="bold")
            ).pack(anchor="w", padx=15, pady=(10, 0))

            deps_text = ctk.CTkTextbox(self.details_window, height=120)
            deps_text.pack(fill="x", padx=15, pady=5)
            for dep in deps[:20]:  # Show first 20
                deps_text.insert("end", f"  • {dep}\n")
            deps_text.configure(state="disabled")

    # ---- 5. Virtual Environment ----
    def on_create_venv(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Create Virtual Environment")
        dialog.geometry("400x200")
        dialog.transient(self)
        dialog.grab_set()

        ctk.CTkLabel(
            dialog, text="Create New Venv", font=ctk.CTkFont(size=16, weight="bold")
        ).pack(pady=(15, 10))

        ctk.CTkLabel(dialog, text="Venv name:").pack(pady=5)
        name_entry = ctk.CTkEntry(dialog, placeholder_text="myenv")
        name_entry.pack(pady=5)

        ctk.CTkButton(
            dialog, text="Create", width=100,
            command=lambda: self._do_create_venv(name_entry.get().strip(), dialog)
        ).pack(pady=15)

    def _do_create_venv(self, name: str, dialog):
        if not name:
            showerror("Error", "Please enter a name for the virtual environment.")
            return
        dialog.destroy()

        venv_path = os.path.join(os.getcwd(), name)
        if os.path.exists(venv_path):
            showerror("Error", f"A folder named '{name}' already exists.")
            return

        self.set_busy(True)
        self.status_lbl.configure(text=f"Creating venv '{name}'...", text_color="#e0b23c")
        self.log(f"Creating virtual environment: {venv_path}")

        def worker():
            success = False
            try:
                result = subprocess.run(
                    [self.current_python_path, "-m", "venv", venv_path],
                    capture_output=True, text=True, timeout=60
                )
                success = result.returncode == 0
                if not success:
                    self.after(0, self.log, f"Error: {result.stderr}")
            except Exception as e:
                self.after(0, self.log, f"Error: {e}")

            def finish():
                self.set_busy(False)
                if success:
                    self.status_lbl.configure(
                        text=f"Venv '{name}' created ✅", text_color="#4caf50"
                    )
                    self.log(f"Virtual environment created at: {venv_path}")
                    self.refresh_interpreters()  # New interpreter available
                else:
                    self.status_lbl.configure(text="Venv creation failed ❌", text_color="#e05555")

            self.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()

    # ---- 6. Requirements Compare ----
    def on_compare_requirements(self):
        path1 = askopenfilename(
            title="Select first requirements.txt",
            filetypes=[("Requirements file", "*.txt"), ("All files", "*.*")],
        )
        if not path1:
            return
        path2 = askopenfilename(
            title="Select second requirements.txt",
            filetypes=[("Requirements file", "*.txt"), ("All files", "*.*")],
        )
        if not path2:
            return

        def parse_req(path):
            pkgs = {}
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        match = re.match(r"^([A-Za-z0-9._-]+)(.*)$", line)
                        if match:
                            pkgs[match.group(1).lower()] = line
            except Exception:
                pass
            return pkgs

        req1 = parse_req(path1)
        req2 = parse_req(path2)

        only_in_1 = set(req1.keys()) - set(req2.keys())
        only_in_2 = set(req2.keys()) - set(req1.keys())
        in_both = set(req1.keys()) & set(req2.keys())

        # Check version differences
        version_diffs = []
        for pkg in in_both:
            if req1[pkg] != req2[pkg]:
                version_diffs.append((pkg, req1[pkg], req2[pkg]))

        dialog = ctk.CTkToplevel(self)
        dialog.title("Requirements Compare")
        dialog.geometry("600x500")
        dialog.transient(self)

        ctk.CTkLabel(
            dialog, text="📑 Requirements Comparison",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(pady=(15, 10))

        text = ctk.CTkTextbox(dialog, font=ctk.CTkFont(family="Consolas", size=12))
        text.pack(fill="both", expand=True, padx=15, pady=5)

        text.insert("end", f"File 1: {os.path.basename(path1)}\n")
        text.insert("end", f"File 2: {os.path.basename(path2)}\n")
        text.insert("end", f"{'='*50}\n\n")

        if only_in_1:
            text.insert("end", f"Only in File 1 ({len(only_in_1)}):\n")
            for pkg in sorted(only_in_1):
                text.insert("end", f"  + {req1[pkg]}\n")
            text.insert("end", "\n")

        if only_in_2:
            text.insert("end", f"Only in File 2 ({len(only_in_2)}):\n")
            for pkg in sorted(only_in_2):
                text.insert("end", f"  + {req2[pkg]}\n")
            text.insert("end", "\n")

        if version_diffs:
            text.insert("end", f"Version Differences ({len(version_diffs)}):\n")
            for pkg, v1, v2 in sorted(version_diffs):
                text.insert("end", f"  {pkg}:\n")
                text.insert("end", f"    File 1: {v1}\n")
                text.insert("end", f"    File 2: {v2}\n")
            text.insert("end", "\n")

        if not only_in_1 and not only_in_2 and not version_diffs:
            text.insert("end", "✅ Files are identical!\n")

        text.insert("end", f"{'='*50}\n")
        text.configure(state="disabled")

    # ---- 7. Dependency Tree ----
    def on_dependency_tree(self):
        self.set_busy(True)
        self.status_lbl.configure(text="Generating dependency tree...", text_color="#e0b23c")
        self.log("Generating dependency tree...")

        def worker():
            try:
                # Try pipdeptree first
                result = subprocess.run(
                    [self.current_python_path, "-m", "pipdeptree"],
                    capture_output=True, text=True, timeout=30
                )
                if result.returncode != 0:
                    # Fallback to pip list
                    result = subprocess.run(
                        self._pip_base_cmd() + ["list"],
                        capture_output=True, text=True, timeout=15
                    )
                    output = result.stdout
                else:
                    output = result.stdout
            except Exception as e:
                output = f"Error: {e}"

            def finish():
                self.set_busy(False)
                self.log("\n" + "="*50)
                self.log("DEPENDENCY TREE:")
                self.log("="*50)
                self.log(output)
                self.log("="*50 + "\n")
                self.status_lbl.configure(text="Dependency tree generated ✅", text_color="#4caf50")

            self.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()

    # ---- 8. Dark / Light Mode ----
    def toggle_theme(self):
        current = ctk.get_appearance_mode()
        new_mode = "light" if current == "Dark" else "dark"
        ctk.set_appearance_mode(new_mode)
        self.theme_btn.configure(text="🌙 Dark Mode" if new_mode == "light" else "☀ Light Mode")

    # ---- 9. Auto Complete ----
    def _load_autocomplete_suggestions(self):
        """Load top PyPI packages for autocomplete."""
        def worker():
            try:
                # Fetch top packages from PyPI simple index
                import json
                url = "https://pypi.org/simple/"
                with urllib.request.urlopen(url, timeout=10) as response:
                    html = response.read().decode("utf-8")
                    # Extract package names from simple index
                    packages = re.findall(r'/simple/([^/]+)/', html)
                    self.autocomplete_list = sorted(set(packages))[:5000]  # Top 5000
            except Exception:
                # Fallback to common packages
                self.autocomplete_list = [
                    "requests", "numpy", "pandas", "matplotlib", "flask", "django",
                    "pytest", "black", "pylint", "mypy", "pillow", "opencv-python",
                    "scikit-learn", "tensorflow", "torch", "transformers",
                    "fastapi", "uvicorn", "sqlalchemy", "alembic", "celery",
                    "redis", "boto3", "botocore", "httpx", "aiohttp", "tornado",
                    "jinja2", "markupsafe", "werkzeug", "click", "itsdangerous",
                    "cryptography", "pyjwt", "passlib", "bcrypt", "argon2-cffi",
                    "psycopg2-binary", "pymongo", "mysql-connector-python",
                    "beautifulsoup4", "lxml", "scrapy", "selenium", "playwright",
                    "pytest-cov", "pytest-asyncio", "coverage", "tox", "nox",
                    "sphinx", "mkdocs", "pre-commit", "isort", "autopep8",
                    "yapf", "bandit", "safety", "pip-audit", "pipdeptree",
                ]

        threading.Thread(target=worker, daemon=True).start()

    def _on_entry_keyrelease(self, event):
        text = self.ent.get()
        if len(text) < 2:
            self.autocomplete_popup.grid_remove()
            return

        matches = [p for p in self.autocomplete_list if p.lower().startswith(text.lower())][:8]
        if not matches:
            self.autocomplete_popup.grid_remove()
            return

        # Clear and rebuild popup
        for widget in self.autocomplete_popup.winfo_children():
            widget.destroy()

        for match in matches:
            btn = ctk.CTkButton(
                self.autocomplete_popup, text=match, anchor="w", height=24,
                fg_color="transparent", hover_color=("gray85", "gray25"),
                command=lambda m=match: self._select_autocomplete(m)
            )
            btn.pack(fill="x")

        self.autocomplete_popup.grid()

    def _select_autocomplete(self, match: str):
        self.ent.delete(0, "end")
        self.ent.insert(0, match)
        self.autocomplete_popup.grid_remove()

    def _on_pypi_search_change(self, *args):
        # Could add autocomplete for PyPI search too
        pass


if __name__ == "__main__":
    app = LibManagerApp()
    app.mainloop()
