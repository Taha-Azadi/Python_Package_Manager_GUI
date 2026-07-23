# 📦 Python Library Manager

A modern and user-friendly **Python Package Manager GUI** built with **CustomTkinter**.

This application provides an easy way to install, uninstall, upgrade, and manage Python packages without using the command line. It automatically detects installed Python interpreters, allowing you to manage packages for any Python version installed on your system.

---

## ✨ Features

* 🐍 Automatically detects installed Python interpreters
* 🔄 Select the Python version you want to use
* 📦 Install one or multiple packages
* 🗑️ Uninstall installed packages
* 📋 View installed packages
* ⬆️ Upgrade pip with one click
* 📥 Install packages from a `requirements.txt` file
* 📤 Export installed packages to `requirements.txt`
* 🔄 Refresh the interpreter list at any time
* ⚡ Non-blocking operations using threads
* 📜 Live command output and logging
* 💾 Save logs to a file
* 📋 Copy logs to the clipboard
* ✅ Package name validation using regular expressions
* 🔒 Secure subprocess execution (no `os.system`)
* 🎨 Modern dark interface built with CustomTkinter
* 🚫 Automatic button disabling while tasks are running
* 📊 Progress indicator and status messages
* 💻 Supports Windows, Linux, and macOS

---

## 📸 Screenshot

> Add screenshots of the application inside a `screenshots/` folder and update this section.

```
screenshots/
├── main_window.png
├── install_package.png
└── package_list.png
```

---

## 📁 Project Structure

```
Python_Library_Manager/
├── main.py
├── README.md
├── requirements.txt
├── LICENSE
└── screenshots/
```

---

## 🚀 Installation

Clone the repository:

```bash
git clone https://github.com/Taha-Azadi/Python_Library_Manager
cd Python_Library_Manager
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the application:

```bash
python main.py
```

---

## 📦 Requirements

* Python 3.8+
* CustomTkinter

Install dependencies manually if needed:

```bash
pip install customtkinter
```

---

## 🛠️ Usage

1. Launch the application.
2. Select the desired Python interpreter.
3. Enter one or more package names.
4. Choose whether to use:

   * `--upgrade`
   * `--user`
5. Click **Install** or **Uninstall**.
6. View live logs in the built-in console.
7. Export or import `requirements.txt` whenever needed.

---

## 🔒 Security

This project avoids using `os.system()` and instead relies on Python's `subprocess` module with argument lists, making command execution safer and resistant to command injection.

---

## 🧰 Built With

* Python
* CustomTkinter
* subprocess
* threading
* tkinter
* Regular Expressions (re)

---

## 📄 License

This project is licensed under the MIT License.

---

## 👨‍💻 Author

**Taha Azadi**

GitHub: https://github.com/Taha-Azadi

---

⭐ If you find this project useful, consider giving it a star!
