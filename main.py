"""
Python Library Manager (GUI) — v1.0.0
----------------------------------
An app for installing/uninstalling Python libraries using customtkinter.

Features of this version:
  - Select Python interpreter/version from a dropdown (automatically detects all
    versions installed on the system; utilizes the 'py' launcher on Windows)
  - Installation/uninstallation runs using the specific Python version selected
  - Refresh button to re-scan interpreters
  - Checkboxes for Upgrade (--upgrade) and --user flags
  - Import from requirements.txt and Export package list to requirements.txt
  - Upgrade pip button
  - Non-blocking execution (threading) with live output display in the log
  - Uses subprocess with argument lists (avoiding os.system) => secure against command injection
  - Package name validation using regex
  - Log saving to file and copying log to clipboard
  - Color-coded status, indeterminate progress bar, and button disabling during execution
  - Icon downloading with error handling (no internet connection does not cause a crash)
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


# Only letters, numbers, dots, underscores, hyphens, and ==, >=, <= for version specifiers are allowed
PACKAGE_PATTERN = re.compile(r"^[A-Za-z0-9._-]+((==|>=|<=)[A-Za-z0-9._-]+)?$")


def get_version_label(python_path: str) -> str:
    """Returns the version by running python --version; returns empty string on error."""
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
    Returns a dict: label -> path
    label is something like "Python 3.12.1  (C:\\...\\python.exe)"
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

    # Always add the current interpreter
    add(sys.executable)

    if os.name == "nt":
        # On Windows, use the py launcher to list all installed versions
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
        # Also check a few other common paths
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


class LibManagerApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Python Library Manager")
        self.geometry("700x650")
        self.minsize(620, 560)

        self._busy = False
        self.interpreters = {}  # label -> path
        self.current_python_path = sys.executable

        self._build_ui()
        self.refresh_interpreters()

    # ---------------------------------------------------------- UI ----
    def _build_ui(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(20, 10))

        ctk.CTkLabel(
            header, text="📦 Python Library Manager",
            font=ctk.CTkFont(size=20, weight="bold")
        ).pack(anchor="w")

        ctk.CTkLabel(
            header,
            text="Enter one or more package names (separated by space or comma). "
                 "Use ==, >=, or <= for specific versions, e.g. requests==2.31.0",
            font=ctk.CTkFont(size=12),
            text_color="gray70",
            wraplength=640,
            justify="left",
        ).pack(anchor="w", pady=(4, 0))

        # ---- Python version selection ----
        py_frame = ctk.CTkFrame(self)
        py_frame.pack(fill="x", padx=20, pady=(10, 5))

        ctk.CTkLabel(py_frame, text="🐍 Python interpreter:",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(
            side="left", padx=(12, 8), pady=10
        )

        self.python_var = ctk.StringVar(value="Scanning...")
        self.python_menu = ctk.CTkOptionMenu(
            py_frame, variable=self.python_var,
            values=["Scanning..."],
            command=self.on_interpreter_selected,
            width=380,
        )
        self.python_menu.pack(side="left", padx=8, pady=10, fill="x", expand=True)

        ctk.CTkButton(
            py_frame, text="🔄 Refresh", width=90,
            command=self.refresh_interpreters,
        ).pack(side="left", padx=(8, 12), pady=10)

        # ---- Package input ----
        entry_frame = ctk.CTkFrame(self, fg_color="transparent")
        entry_frame.pack(fill="x", padx=20, pady=5)

        self.ent = ctk.CTkEntry(
            entry_frame, placeholder_text="e.g. numpy pandas requests==2.31.0",
            height=38,
        )
        self.ent.pack(side="left", fill="x", expand=True)
        self.ent.bind("<Return>", lambda e: self.on_install())

        # ---- Checkboxes ----
        opts_frame = ctk.CTkFrame(self, fg_color="transparent")
        opts_frame.pack(fill="x", padx=20, pady=(2, 5))

        self.upgrade_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            opts_frame, text="Upgrade (--upgrade)", variable=self.upgrade_var
        ).pack(side="left", padx=(0, 20))

        self.user_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            opts_frame, text="Install to user site (--user)", variable=self.user_var
        ).pack(side="left")

        # ---- Main buttons ----
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(5, 5))

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
        req_frame = ctk.CTkFrame(self, fg_color="transparent")
        req_frame.pack(fill="x", padx=20, pady=(0, 8))

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

        self.progress = ctk.CTkProgressBar(self, mode="indeterminate")
        self.progress.pack(fill="x", padx=20, pady=(2, 5))
        self.progress.stop()

        self.status_lbl = ctk.CTkLabel(self, text="Ready", font=ctk.CTkFont(size=12))
        self.status_lbl.pack(anchor="w", padx=20)

        self.log_box = ctk.CTkTextbox(self, font=ctk.CTkFont(family="Consolas", size=12))
        self.log_box.pack(fill="both", expand=True, padx=20, pady=(8, 5))
        self.log_box.configure(state="disabled")

        log_btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        log_btn_frame.pack(fill="x", padx=20, pady=(0, 20))

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
        showinfo("Copied", "Log copied to clipboard.")

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
                "\n\nOnly letters, numbers, ., _, -, and ==, >=, <= for version specifiers are allowed."
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
                # Try to keep the current interpreter selected
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
        self.run_command_async(cmd, f"Installation from {os.path.basename(path)} completed ✅")

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
        self.status_lbl.configure(text="Generating requirements.txt...", text_color="#e0b23c")
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
                    self.status_lbl.configure(text="Error generating file ❌", text_color="#e05555")

            self.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()


if __name__ == "__main__":
    app = LibManagerApp()
    app.mainloop()