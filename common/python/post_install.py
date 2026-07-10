import os
import sys
import shutil
import subprocess
import tempfile
import urllib.request
import threading
import tkinter as tk
from tkinter import messagebox

class PostInstallApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Blinky Setup - Addons")
        self.root.geometry("500x380")
        self.root.configure(bg="#0f172a") # Slate 900
        self.root.resizable(False, False)

        # Style constants
        self.bg_color = "#0f172a"
        self.card_color = "#1e293b" # Slate 800
        self.text_color = "#f8fafc" # Slate 50
        self.accent_color = "#38bdf8" # Sky 400
        self.button_color = "#0284c7" # Sky 600
        self.button_hover = "#0369a1" # Sky 700
        self.success_color = "#4ade80" # Green 400

        # Check if already installed
        self.ollama_installed = self.check_ollama()

        # State variables
        self.install_ollama_var = tk.BooleanVar(value=not self.ollama_installed)
        self.install_playwright_var = tk.BooleanVar(value=True)

        self.setup_ui()

    def check_ollama(self):
        if shutil.which("ollama"):
            return True
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        if local_app_data:
            default_path = os.path.join(local_app_data, "Programs", "Ollama", "ollama.exe")
            if os.path.exists(default_path):
                return True
        return False

    def setup_ui(self):
        # Header Container
        header_frame = tk.Frame(self.root, bg=self.bg_color, pady=15)
        header_frame.pack(fill="x")

        title = tk.Label(
            header_frame, 
            text="Configure Blinky Addons", 
            font=("Segoe UI", 16, "bold"), 
            bg=self.bg_color, 
            fg=self.accent_color
        )
        title.pack(anchor="w", padx=25)

        subtitle = tk.Label(
            header_frame, 
            text="Choose optional components to install on this laptop.", 
            font=("Segoe UI", 10), 
            bg=self.bg_color, 
            fg="#94a3b8" # Slate 400
        )
        subtitle.pack(anchor="w", padx=25, pady=(2, 0))

        # Main content card
        self.card_frame = tk.Frame(self.root, bg=self.card_color, bd=1, relief="flat", padx=20, pady=15)
        self.card_frame.pack(fill="both", expand=True, padx=25, pady=(5, 15))

        # Ollama Option
        ollama_frame = tk.Frame(self.card_frame, bg=self.card_color, pady=8)
        ollama_frame.pack(fill="x")

        ollama_cb = tk.Checkbutton(
            ollama_frame,
            text="Install Ollama (Recommended)",
            variable=self.install_ollama_var,
            bg=self.card_color,
            fg=self.text_color,
            selectcolor=self.bg_color,
            activebackground=self.card_color,
            activeforeground=self.accent_color,
            font=("Segoe UI", 11, "bold"),
            bd=0,
            highlightthickness=0
        )
        ollama_cb.pack(anchor="w")
        if self.ollama_installed:
            ollama_cb.configure(state="disabled", text="Install Ollama (Already Installed)")
            self.install_ollama_var.set(False)

        ollama_desc = tk.Label(
            ollama_frame,
            text="Downloads & installs Ollama to run AI models locally (offline).",
            font=("Segoe UI", 9),
            bg=self.card_color,
            fg="#94a3b8",
            wraplength=400,
            justify="left"
        )
        ollama_desc.pack(anchor="w", padx=28, pady=(2, 0))

        # Playwright Option
        playwright_frame = tk.Frame(self.card_frame, bg=self.card_color, pady=12)
        playwright_frame.pack(fill="x")

        playwright_cb = tk.Checkbutton(
            playwright_frame,
            text="Pre-download Playwright Chromium Browser",
            variable=self.install_playwright_var,
            bg=self.card_color,
            fg=self.text_color,
            selectcolor=self.bg_color,
            activebackground=self.card_color,
            activeforeground=self.accent_color,
            font=("Segoe UI", 11, "bold"),
            bd=0,
            highlightthickness=0
        )
        playwright_cb.pack(anchor="w")

        playwright_desc = tk.Label(
            playwright_frame,
            text="Downloads the browser binary for Blinky's browser autopilot. This avoids downloading it on first run (~120MB).",
            font=("Segoe UI", 9),
            bg=self.card_color,
            fg="#94a3b8",
            wraplength=400,
            justify="left"
        )
        playwright_desc.pack(anchor="w", padx=28, pady=(2, 0))

        # Action Buttons Container
        self.btn_frame = tk.Frame(self.root, bg=self.bg_color, pady=15, padx=25)
        self.btn_frame.pack(fill="x", side="bottom")

        self.apply_btn = tk.Button(
            self.btn_frame,
            text="Apply & Finish",
            command=self.start_installations,
            bg=self.button_color,
            fg="white",
            activebackground=self.button_hover,
            activeforeground="white",
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            padx=20,
            pady=6,
            bd=0,
            cursor="hand2"
        )
        self.apply_btn.pack(side="right")

        self.skip_btn = tk.Button(
            self.btn_frame,
            text="Skip Addons",
            command=self.root.quit,
            bg="transparent",
            fg="#94a3b8",
            activebackground=self.bg_color,
            activeforeground=self.text_color,
            font=("Segoe UI", 10),
            relief="flat",
            padx=15,
            pady=6,
            bd=0,
            cursor="hand2"
        )
        self.skip_btn.pack(side="right", padx=(0, 10))

    def start_installations(self):
        # Clear main checkboxes, transition to progress screen
        for child in self.card_frame.winfo_children():
            child.pack_forget()

        self.apply_btn.pack_forget()
        self.skip_btn.pack_forget()

        # Status Label
        self.status_title = tk.Label(
            self.card_frame,
            text="Installing Selected Addons...",
            font=("Segoe UI", 12, "bold"),
            bg=self.card_frame.cget("bg"),
            fg=self.accent_color
        )
        self.status_title.pack(anchor="w", pady=(5, 10))

        # Action status log
        self.status_log = tk.Label(
            self.card_frame,
            text="Starting tasks...",
            font=("Segoe UI", 10),
            bg=self.card_frame.cget("bg"),
            fg=self.text_color,
            justify="left",
            wraplength=400
        )
        self.status_log.pack(anchor="w", pady=5)

        # Start execution in a background thread
        threading.Thread(target=self.run_background_tasks, daemon=True).start()

    def update_status(self, text, color=None):
        self.status_log.configure(text=text)
        if color:
            self.status_log.configure(fg=color)

    def run_background_tasks(self):
        do_ollama = self.install_ollama_var.get()
        do_playwright = self.install_playwright_var.get()

        if do_ollama:
            try:
                url = "https://ollama.com/download/OllamaSetup.exe"
                temp_dir = tempfile.gettempdir()
                installer_path = os.path.join(temp_dir, "OllamaSetup.exe")
                
                self.root.after(0, self.update_status, "Downloading Ollama installer...")
                urllib.request.urlretrieve(url, installer_path)
                
                self.root.after(0, self.update_status, "Launching Ollama installer...")
                subprocess.Popen([installer_path])
                
                # Sleep briefly to let setup launch
                import time
                time.sleep(1)
            except Exception as e:
                self.root.after(0, self.update_status, f"Ollama download failed: {e}", "#f87171")
                import time
                time.sleep(3)

        if do_playwright:
            try:
                self.root.after(0, self.update_status, "Downloading Playwright Chromium (~120MB). Please wait...")
                res = subprocess.run(
                    [sys.executable, "-m", "playwright", "install", "chromium"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                if res.returncode == 0:
                    self.root.after(0, self.update_status, "Playwright Chromium installed successfully!", self.success_color)
                else:
                    self.root.after(0, self.update_status, f"Playwright error: {res.stderr or res.stdout}", "#f87171")
                import time
                time.sleep(2)
            except Exception as e:
                self.root.after(0, self.update_status, f"Playwright install failed: {e}", "#f87171")
                import time
                time.sleep(3)

        self.root.after(0, self.complete_installation)

    def complete_installation(self):
        self.status_title.configure(text="Configuration Complete!", fg=self.success_color)
        self.status_log.configure(
            text="Optional addons have been configured successfully.\n\nClick 'Finish' to close setup.", 
            fg=self.text_color
        )
        
        finish_btn = tk.Button(
            self.btn_frame,
            text="Finish",
            command=self.root.quit,
            bg=self.button_color,
            fg="white",
            activebackground=self.button_hover,
            activeforeground="white",
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            padx=25,
            pady=6,
            bd=0,
            cursor="hand2"
        )
        finish_btn.pack(side="right")

if __name__ == "__main__":
    root = tk.Tk()
    app = PostInstallApp(root)
    root.mainloop()
