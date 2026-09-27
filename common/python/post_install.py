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
        self.root.geometry("500x480")
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

        # Resolve paths
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.common_dir = os.path.dirname(self.script_dir)
        self.project_root = os.path.dirname(self.common_dir)

        # Check existing components
        self.ollama_installed = self.check_ollama()
        self.docker_cmd = self.get_docker_cmd()
        self.docker_installed = self.docker_cmd is not None
        self.docker_running = self.check_docker_running()

        # State variables
        self.install_ollama_var = tk.BooleanVar(value=not self.ollama_installed)
        self.install_playwright_var = tk.BooleanVar(value=True)
        self.install_searxng_var = tk.BooleanVar(value=True)

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

    def get_docker_cmd(self):
        # 1. Check system PATH
        cmd = shutil.which("docker")
        if cmd:
            return cmd
        
        # 2. Check standard Windows path
        std_path = r"C:\Program Files\Docker\Docker\resources\bin\docker.exe"
        if os.path.exists(std_path):
            return std_path
        return None

    def check_docker_running(self):
        if not self.docker_installed or not self.docker_cmd:
            return False
        try:
            res = subprocess.run([self.docker_cmd, "info"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return res.returncode == 0
        except Exception:
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
        ollama_frame = tk.Frame(self.card_frame, bg=self.card_color, pady=6)
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
        playwright_frame = tk.Frame(self.card_frame, bg=self.card_color, pady=6)
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

        # SearXNG Option
        searxng_frame = tk.Frame(self.card_frame, bg=self.card_color, pady=6)
        searxng_frame.pack(fill="x")

        searxng_cb = tk.Checkbutton(
            searxng_frame,
            text="Install Docker & Setup SearXNG Search Engine",
            variable=self.install_searxng_var,
            bg=self.card_color,
            fg=self.text_color,
            selectcolor=self.bg_color,
            activebackground=self.card_color,
            activeforeground=self.accent_color,
            font=("Segoe UI", 11, "bold"),
            bd=0,
            highlightthickness=0
        )
        searxng_cb.pack(anchor="w")

        if not self.docker_installed:
            searxng_status_text = "Docker not found. Setup will download & launch Docker Desktop Installer (~580MB) and start SearXNG."
        elif not self.docker_running:
            searxng_status_text = "Docker is installed but not running. Setup will configure SearXNG to start once you open Docker Desktop."
        else:
            searxng_status_text = "Docker is running. Setup will automatically spin up the local SearXNG container."

        searxng_desc = tk.Label(
            searxng_frame,
            text=searxng_status_text,
            font=("Segoe UI", 9),
            bg=self.card_color,
            fg="#94a3b8" if self.docker_installed else "#f39c12", # orange warning if docker missing but we'll install it
            wraplength=400,
            justify="left"
        )
        searxng_desc.pack(anchor="w", padx=28, pady=(2, 0))

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
            bg=self.bg_color,
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

    def set_env_var(self, key, value):
        env_path = os.path.join(self.project_root, ".env")
        if not os.path.exists(env_path):
            example_path = os.path.join(self.common_dir, ".envexample")
            if os.path.exists(example_path):
                try:
                    shutil.copy(example_path, env_path)
                except Exception:
                    pass
            if not os.path.exists(env_path):
                try:
                    with open(env_path, "w", encoding="utf-8") as f:
                        f.write("")
                except Exception:
                    pass

        try:
            lines = []
            found = False
            if os.path.exists(env_path):
                with open(env_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()

            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped and not stripped.startswith("#") and "=" in stripped:
                    k, v = stripped.split("=", 1)
                    if k.strip() == key:
                        lines[i] = f"{key}={value}\n"
                        found = True
                        break
            if not found:
                lines.append(f"{key}={value}\n")

            with open(env_path, "w", encoding="utf-8") as f:
                f.writelines(lines)
        except Exception as e:
            print(f"Error writing to env: {e}")

    def run_background_tasks(self):
        do_ollama = self.install_ollama_var.get()
        do_playwright = self.install_playwright_var.get()
        do_searxng = self.install_searxng_var.get()

        import time

        if do_ollama:
            try:
                url = "https://ollama.com/download/OllamaSetup.exe"
                temp_dir = tempfile.gettempdir()
                installer_path = os.path.join(temp_dir, "OllamaSetup.exe")
                
                self.root.after(0, self.update_status, "Downloading Ollama installer...")
                urllib.request.urlretrieve(url, installer_path)
                
                self.root.after(0, self.update_status, "Launching Ollama installer...")
                subprocess.Popen([installer_path])
                
                time.sleep(1)
            except Exception as e:
                self.root.after(0, self.update_status, f"Ollama download failed: {e}", "#f87171")
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
                time.sleep(2)
            except Exception as e:
                self.root.after(0, self.update_status, f"Playwright install failed: {e}", "#f87171")
                time.sleep(3)

        if do_searxng:
            if not self.docker_installed:
                try:
                    self.root.after(0, self.update_status, "Downloading Docker Desktop Installer (~580MB). Please wait...")
                    url = "https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe"
                    temp_dir = tempfile.gettempdir()
                    installer_path = os.path.join(temp_dir, "DockerDesktopInstaller.exe")
                    
                    urllib.request.urlretrieve(url, installer_path)
                    
                    self.root.after(0, self.update_status, "Launching Docker Desktop Installer...")
                    subprocess.Popen([installer_path])
                    
                    self.root.after(0, self.set_env_var, "BLINKY_SEARXNG_URL", "http://127.0.0.1:8888")
                    time.sleep(2)
                except Exception as e:
                    self.root.after(0, self.update_status, f"Docker download failed: {e}", "#f87171")
                    time.sleep(3)
            else:
                # Docker is installed — make sure it's running (start it automatically if not)
                if not self.check_docker_running():
                    self.root.after(0, self.update_status, "Docker is installed but not running. Starting Docker Desktop automatically...")
                    docker_desktop_paths = [
                        r"C:\Program Files\Docker\Docker\Docker Desktop.exe",
                        os.path.join(os.environ.get("PROGRAMFILES", r"C:\Program Files"), "Docker", "Docker", "Docker Desktop.exe"),
                    ]
                    docker_desktop_exe = next((p for p in docker_desktop_paths if os.path.exists(p)), None)
                    if docker_desktop_exe:
                        subprocess.Popen([docker_desktop_exe])
                        # Poll up to 3 minutes until Docker daemon is ready
                        max_wait = 180
                        waited = 0
                        poll_interval = 5
                        while waited < max_wait:
                            time.sleep(poll_interval)
                            waited += poll_interval
                            self.root.after(0, self.update_status, f"Waiting for Docker to start... ({waited}s / {max_wait}s)")
                            if self.check_docker_running():
                                break
                        else:
                            self.root.after(0, self.update_status, "Docker did not start in time. Please open Docker Desktop manually and re-run setup.", "#f87171")
                            self.root.after(0, self.set_env_var, "BLINKY_SEARXNG_URL", "http://127.0.0.1:8888")
                            time.sleep(4)
                            self.root.after(0, self.complete_installation)
                            return
                    else:
                        self.root.after(0, self.update_status, "Could not find Docker Desktop.exe. Please start Docker manually.", "#f87171")
                        self.root.after(0, self.set_env_var, "BLINKY_SEARXNG_URL", "http://127.0.0.1:8888")
                        time.sleep(4)
                        self.root.after(0, self.complete_installation)
                        return

                # Docker is now running — spin up SearXNG
                try:
                    self.root.after(0, self.update_status, "Running Docker Compose to pull & start local SearXNG...")
                    compose_file = os.path.join(self.common_dir, "docker-compose.yml")
                    
                    res = subprocess.run(
                        [self.docker_cmd, "compose", "-f", compose_file, "up", "-d"],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        cwd=self.project_root
                    )
                    
                    if res.returncode == 0:
                        self.root.after(0, self.update_status, "Local SearXNG container started successfully!", self.success_color)
                        self.root.after(0, self.set_env_var, "BLINKY_SEARXNG_URL", "http://127.0.0.1:8888")
                    else:
                        self.root.after(0, self.update_status, f"Docker Compose error: {res.stderr or res.stdout}", "#f87171")
                    time.sleep(2)
                except Exception as e:
                    self.root.after(0, self.update_status, f"SearXNG setup failed: {e}", "#f87171")
                    time.sleep(3)
        else:
            # If not explicitly starting docker, still write the default URL so it works once docker starts
            self.root.after(0, self.set_env_var, "BLINKY_SEARXNG_URL", "http://127.0.0.1:8888")

        self.root.after(0, self.complete_installation)

    def complete_installation(self):
        self.status_title.configure(text="Configuration Complete!", fg=self.success_color)
        
        msg = "Optional addons have been configured successfully."
        if self.install_searxng_var.get() and not self.docker_installed:
            msg += "\n\nNote: The Docker Desktop installer was launched. After Docker installation completes, please re-run this setup to start the local SearXNG container."
        
        msg += "\n\nClick 'Finish' to close setup."
        self.status_log.configure(text=msg, fg=self.text_color)
        
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
