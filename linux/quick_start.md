# Blinky Quick Start Guide for Linux Machines

## Overview

This guide walks you through setting up **Blinky** on a Linux workstation. It covers both **Ollama** and **Groq** inference back‑ends.We are testing it on many linux distros but if you face any issues , please feel free to raise an issue on github.

## Prerequisites

- A recent Linux distribution (Ubuntu 22.04+, Arch, Fedora, etc.)
- **Node.js** (>=18) and **bun**
- **Python 3.11** with `venv` support
- **curl**, **jq**, and **git** installed
- **Docker** and **Docker Compose** installed (To run searxng in a Docker container)
- For Wayland users: ensure `xwayland` is installed (needed for some X11‑only tools)

## Install & Pull the Model

### Ollama (local inference)

```bash
# Install Ollama (for arhc linux – adapt for your distro)
sudo pacman -S ollama
# Start the Ollama daemon
ollama serve &
# Pull the gemma4:e4b model
ollama pull gemma4:e4b
```

### Groq (cloud inference)

1. Create an account at https://groq.com and obtain an API key.
2. Export the key in your shell:

```bash
export GROQ_API_KEY=your_api_key_here
```

3. Optionally verify access with the helper script later (scripts/groq-check.sh) .

## Install Project Dependencies

```bash
# Clone the repository if you haven't already
git clone git@github.com:KingSahil/Blinky.git && cd blinky
# Install Node dependencies
bun install
# Install Python requirements (creates a .venv folder in root)
bun run linux:setup:python   # runs ./linux/scripts/setup-python.sh
```

### Additional Linux Requirements

#### 1. Audio Support (GStreamer)
To prevent WebKit audio context initialization failures, install the GStreamer good plugins:
* **Arch Linux**:
  ```bash
  sudo pacman -S gst-plugins-good
  ```
* **Ubuntu/Debian**:
  ```bash
  sudo apt-get install gstreamer1.0-plugins-good
  ```

#### 2. OCR Language Data (Tesseract)
Although `tesseract` is a system requirement, some Linux distributions (like Arch) package the language data separately.
* **Option A (System install)**:
  ```bash
  sudo pacman -S tesseract-data-eng  # Arch Linux
  ```
* **Option B (Local user install - no sudo needed)**:
  Download the dataset directly to your workspace:
  ```bash
  mkdir -p common/tessdata
  curl -L -o common/tessdata/eng.traineddata https://github.com/tesseract-ocr/tessdata_fast/raw/main/eng.traineddata
  ```
  Then, add the following line to your `.env` file in the project root:
  ```env
  TESSDATA_PREFIX=/absolute/path/to/Blinky/common/tessdata/
  ```

## Verify Model Availability

```bash
# Ollama check (will exit if the model is missing)
bun run linux:check:ollama
# Groq check (requires GROQ_API_KEY)
bun run linux:check:groq
```

## Run the Application

```bash
# Start Blinky
bun run dev   # Starts Vite + Tauri (http://localhost:5173 / WebSocket server on 9001)
```

```bash
# Run SearXNG via Docker Compose from the root folder
docker compose -f common/docker-compose.yml up -d
```

## Troubleshooting

- **Wayland display errors**: Install `xwayland` (`sudo apt install xwayland`) and restart your session.
- **OCR/Tesseract fails**: Ensure either `tesseract-data-eng` is installed system-wide or `TESSDATA_PREFIX` is properly configured in `.env`.
- **Ollama not reachable**: Ensure the daemon is running (`ps aux | grep ollama`). Use `./linux/scripts/check-ollama.sh` for a quick health check.
- **Groq API failures**: Verify `GROQ_API_KEY` and network connectivity. Run `./linux/scripts/groq-check.sh` for detailed diagnostics.
- On Wayland, if you encounter issues with Electron‑based tools, prepend `export ELECTRON_ENABLE_LOGGING=1` before the command.

Happy hacking! 🎉
