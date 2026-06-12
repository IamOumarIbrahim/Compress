# ⚡ Media Compressor

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![FFmpeg](https://img.shields.io/badge/Dependency-FFmpeg-green.svg?style=flat-square&logo=ffmpeg&logoColor=white)](https://ffmpeg.org/)
[![Pillow](https://img.shields.io/badge/Library-Pillow_9.5+-orange.svg?style=flat-square&logo=python&logoColor=white)](https://python-pillow.org/)
[![PyPDF](https://img.shields.io/badge/Library-PyPDF_6.13+-yellow.svg?style=flat-square)](https://pypi.org/project/pypdf/)
[![Compiler](https://img.shields.io/badge/Compiler-PyInstaller-blue.svg?style=flat-square)](https://pyinstaller.org/)
[![License: CC0](https://img.shields.io/badge/License-CC0_1.0-lightgrey.svg?style=flat-square)](https://creativecommons.org/publicdomain/zero/1.0/)

A premium, multi-format compression utility featuring a clean desktop GUI and a powerful command-line interface. Precisely compress audio, video, images, PDFs, and Office documents (`.docx`, `.pptx`) to fit target sizes (such as **15MB** limits for messaging systems, email attachments, or web uploads).

---

## 📖 Table of Contents
- [Key Features](#-key-features)
- [System Architecture](#-system-architecture)
- [Quick Setup & Installation](#-quick-setup--installation)
- [How to Use](#-how-to-use)
  - [Option A: Graphical Interface (GUI)](#option-a-graphical-interface-gui)
  - [Option B: Command-Line Interface (CLI)](#option-b-command-line-interface-cli)
- [Standalone Executable Build (`.exe`)](#-standalone-executable-build-exe)
- [License](#-license)

---

## ✨ Key Features

- 📁 **Universal Format Support**: 
  - **Audio**: `.mp3`, `.m4a`
  - **Video**: `.mp4`
  - **Images**: `.jpg`, `.jpeg`, `.png`, `.gif` (including animated GIFs)
  - **Documents**: `.pdf`
  - **Office Documents**: `.docx`, `.pptx`
- 🎨 **Tkinter Clam Theme UI**: A clean, responsive dashboard designed for desktop convenience.
- 🎯 **Precise Target Size Allocation**: Iteratively calculates bitrates, downscales resolution, and adjusts quality variables to fit output sizes strictly under limits (with a built-in safety headroom).
- ⚙️ **Smart Document Compression**:
  - Treats `.docx` and `.pptx` files as OpenXML zip packages, extracting and optimizing only internal media assets (`word/media`, `ppt/media`). This shrinks the document dramatically with 100% formatting and text integrity preserved.
  - Compresses PDF streams and internal images using `pypdf`'s object optimization.
- 💻 **Dual Mode**: Starts as a graphical user interface, or runs as a CLI for developer batch operations.

---

## ⚙️ System Architecture

The following block diagram illustrates the application's routing mechanism and processing pipelines:

```mermaid
graph TD
    User["User Input: File + Target Size"] --> ModeSelect{Execution Mode}
    ModeSelect -->|GUI Mode| Tkinter[Tkinter UI Panel]
    ModeSelect -->|CLI Mode| Parser[CLI Argument Parser]
    Tkinter --> Config[Configuration Options]
    Parser --> Config
    Config --> Router{File Format Router}
    
    Router -->|Audio/Video| FFmpeg["FFmpeg & FFprobe Pipeline"]
    Router -->|Images| Pillow["Pillow Iterative Optimizer"]
    Router -->|PDF Documents| PyPDF["pypdf Object & Stream Compressor"]
    Router -->|Office Docs| ZipFile["ZipFile Media Packer"]
    
    FFmpeg --> Verify[Size Verification]
    Pillow --> Verify
    PyPDF --> Verify
    ZipFile --> Verify
    
    Verify --> Output[Compressed File]
    
    classDef default fill:#0f172a,stroke:#3b82f6,stroke-width:2px,color:#fff;
    classDef process fill:#1e1b4b,stroke:#a855f7,stroke-width:2px,color:#fff;
    class FFmpeg,Pillow,PyPDF,ZipFile process;
```

---

## 🚀 Quick Setup & Installation

This utility requires **Python 3.8+** and **FFmpeg** installed on your system.

### 1️⃣ Install Python
- **Windows / macOS**: Download and run the official installer from [python.org](https://www.python.org/downloads/). During installation on Windows, **make sure to check "Add Python to PATH"**.
- **Linux**: Usually pre-installed. If not, run:
  ```bash
  sudo apt install python3 python3-pip
  ```

### 2️⃣ Install Python Libraries
Install the core compression dependencies:
```bash
pip install Pillow pypdf
```

### 3️⃣ Install FFmpeg
The tool relies on FFmpeg for audio/video processing. Install it using the standard method for your OS:

- **Windows** (via PowerShell as Administrator):
  ```powershell
  winget install Gyan.FFmpeg
  ```
  *(Restart your computer or terminal after installation completes).*
  
- **macOS** (via Homebrew):
  ```bash
  brew install ffmpeg
  ```

- **Linux** (Debian/Ubuntu):
  ```bash
  sudo apt update && sudo apt install ffmpeg
  ```

---

## 🛠️ How to Use

### Option A: Graphical Interface (GUI)
Run the script to open the interactive utility panel:
```bash
python compress.py
```
Select your input file, choose the destination directory, set the target size in MB, and click **Start Compression**.

### Option B: Command-Line Interface (CLI)
For batch tasks or scripting:
```bash
# Compress a video to a standard 15MB target (saves to c:\Dev\tools\Compress\DONE)
python compress.py input.mp4

# Compress a PDF file to a custom target of 5MB in a specific directory
python compress.py input.pdf output_dir 5.0
```

---

## 📦 Standalone Executable Build (`.exe`)

You can compile a portable, single-file Windows executable that runs without requiring Python installed:

1. Install PyInstaller:
   ```bash
   pip install pyinstaller
   ```
2. Build the executable:
   ```bash
   pyinstaller --onefile --noconsole --name "MediaCompressor" compress.py
   ```
3. Your portable executable will be created in the `dist/` directory as `MediaCompressor.exe`.

---

## 📄 License
This repository is licensed under the [CC0 1.0 Universal (CC0 1.0) Public Domain Dedication](LICENSE).
