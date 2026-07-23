# 📦 Python Package Manager GUI

A modern **Python Package Manager** built with **Python** and **CustomTkinter**.

Manage Python packages with an intuitive graphical interface instead of using the command line.

---

## ✨ Features

* 🐍 Automatically detect installed Python interpreters
* 🔄 Select the Python version you want to use
* 📦 Install one or multiple packages
* 🗑️ Uninstall packages
* ⬆️ Upgrade installed packages
* 🚀 Upgrade **pip**
* 📋 Display installed packages
* 📥 Install packages from `requirements.txt`
* 📤 Export installed packages to `requirements.txt`
* 👤 Optional `--user` installation
* ⬆️ Optional `--upgrade` installation
* 🛡️ Package name validation using Regular Expressions
* ⚡ Secure execution using `subprocess` (no `os.system`)
* 🧵 Non-blocking operations using background threads
* 📜 Live command output
* 📋 Copy logs to clipboard
* 💾 Save logs to a text file
* 📊 Progress indicator
* 🎨 Modern Dark UI built with **CustomTkinter**

---

## 📸 Screenshots

### Screenshot 1
![Screenshot 1](screenshots/Screenshot(1).png)
### Screenshot 2
![Screenshot 2](screenshots/Screenshot(2).png)
### Screenshot 3
![Screenshot 3](screenshots/Screenshot(3).png)
### Screenshot 4
![Screenshot 4](screenshots/Screenshot(4).png)
### Screenshot 5
![Screenshot 5](screenshots/Screenshot(5).png)
---

## 📁 Project Structure

```text
Python-Package-Manager-GUI/
│
├── main.py
├── requirements.txt
├── README.md
├── LICENSE
│
└── screenshots/
```

---

## 🚀 Installation

```bash
git clone https://github.com/Taha-Azadi/Python-Package-Manager-GUI

cd Python-Package-Manager-GUI

pip install -r requirements.txt

python main.py
```

---

## 🛠 Requirements

* Python 3.8+
* customtkinter

Install dependencies:

```bash
pip install -r requirements.txt
```

---

## 📚 Technologies

* Python
* CustomTkinter
* subprocess
* threading
* Regular Expressions
* tkinter
* urllib
* glob
* shutil

---

## 🔒 Security

This application executes **pip** commands using Python's **subprocess** module with argument lists instead of shell commands, reducing the risk of command injection.

Package names are validated before execution using regular expressions.

---

## 💡 Why This Project?

Managing Python libraries from the terminal can be inconvenient for beginners.

This project provides a clean and user-friendly desktop interface for installing, removing, updating, and managing Python packages across multiple Python installations.

---

## 📌 Future Plans

* 🔍 Search packages on PyPI
* 📄 Package information viewer
* 📦 Dependency tree
* 🌐 Proxy support
* 🔄 Package update checker
* ⭐ Favorite packages
* 🎨 Light/Dark theme switch
* 🐍 Virtual Environment Manager

---

## 📄 License

This project is licensed under the **MIT License**.

---

## 👨‍💻 Developer

**Taha Azadi**

GitHub: https://github.com/Taha-Azadi

⭐ If you like this project, consider giving it a star!
