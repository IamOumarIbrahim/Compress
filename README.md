# ⚡ Media Compressor (v0.4)

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![FFmpeg](https://img.shields.io/badge/Dependency-FFmpeg-green.svg?style=flat-square&logo=ffmpeg&logoColor=white)](https://ffmpeg.org/)
[![Pillow](https://img.shields.io/badge/Library-Pillow_9.5+-orange.svg?style=flat-square&logo=python&logoColor=white)](https://python-pillow.org/)
[![PyPDF](https://img.shields.io/badge/Library-PyPDF_6.13+-yellow.svg?style=flat-square)](https://pypi.org/project/pypdf/)
[![Compiler](https://img.shields.io/badge/Compiler-PyInstaller-blue.svg?style=flat-square)](https://pyinstaller.org/)
[![License: CC0](https://img.shields.io/badge/License-CC0_1.0-lightgrey.svg?style=flat-square)](https://creativecommons.org/publicdomain/zero/1.0/)

A premium, multi-format compression utility featuring a dual-pane desktop GUI and a powerful command-line interface. Precisely compress audio, video, images, PDFs, Office documents, and ZIP archives to fit target sizes (such as **15MB** limits for messaging systems, email attachments, or web uploads).

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
  - **Audio**: `.mp3`, `.m4a`, `.wav`, `.flac`, `.ogg`, `.aac`, `.wma`
  - **Video**: `.mp4`, `.mkv`, `.avi`, `.mov`, `.webm`, `.flv`, `.wmv`
  - **Images**: `.jpg`, `.jpeg`, `.png`, `.gif`, `.webp`, `.bmp`, `.tiff`
  - **PDF Documents**: `.pdf`
  - **Office Documents**: `.docx`, `.pptx`, `.xlsx`
  - **Archives**: `.zip`
- 🖥️ **Dual-Pane Desktop GUI (v0.4)**:
  - **Left Pane (Control Center)**: Configure file inputs, targets, speed, and image resize parameters.
  - **Right Pane (Preview Center)**:
    - **Selected File Preview**: Displays live image thumbnails and detailed file metadata (durations, pages, sizes).
    - **Output Folder Preview**: Lists files in the target directory (name, size, modification date) inside an interactive Treeview. Double-clicking any file highlights it instantly in Windows Explorer.
- 📁 **Explorer Integration (v0.4)**:
  - Added a **Go to File Location** button next to Start Compression that highlights the output file in Windows Explorer.
- ⏩ **Speed Adjustments (v0.3)**: 
  - Adjust speed multipliers from `0.5x` to `3.0x` with a live duration preview. 
  - Correctly applies speed multiplier before compression (`setpts` + chained `atempo` filters) to maintain high video/audio pitch sync.
- 📐 **Image Resizing**: 
  - Scale image dimensions from `10%` to `100%` using a slider with a live resolution preview.
- ⚙️ **Smart Document & Archive Compression**:
  - Treats `.docx`, `.pptx`, and `.xlsx` files as OpenXML zip packages, extracting and optimizing only internal media assets (`word/media`, `ppt/media`, `xl/media`) to preserve 100% formatting.
  - Compresses PDF streams and internal images using `pypdf`'s object optimization.
  - Automatically unzips `.zip` archives, recursively compresses all compressible media files inside using a relative target size budget, and re-packages them.

---

## ⚙️ System Architecture

The following block diagram illustrates the routing and processing pipelines of the compressor:

```mermaid
graph TD
    User["User Input: File + Target Size"] --> ModeSelect{Execution Mode}
    ModeSelect -->|GUI Mode| Tkinter[Tkinter Dual-Pane UI]
    ModeSelect -->|CLI Mode| Parser[CLI Argument Parser]
    Tkinter --> Config[Configuration Options: Speed & Scale]
    Parser --> Config
    Config --> Router{File Format Router}
    
    Router -->|Audio/Video| FFmpeg["FFmpeg speed-then-compress Pipeline"]
    Router -->|Images| Pillow["Pillow Scale & Quality Optimizer"]
    Router -->|PDF Documents| PyPDF["pypdf Object & Stream Compressor"]
    Router -->|Office Docs| ZipFile["ZipFile Media Packer"]
    Router -->|Zip Archives| ZipPack["ZIP Recursive Packer"]
    
    FFmpeg --> Verify[Size Verification]
    Pillow --> Verify
    PyPDF --> Verify
    ZipFile --> Verify
    ZipPack --> Verify
    
    Verify --> Output[Compressed File]
    
    classDef default fill:#0f172a,stroke:#3b82f6,stroke-width:2px,color:#fff;
    classDef process fill:#1e1b4b,stroke:#a855f7,stroke-width:2px,color:#fff;
    class FFmpeg,Pillow,PyPDF,ZipFile,ZipPack process;
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
Install the core dependencies:
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
1. Select your input file.
2. If it is an audio/video file, use the **Speed settings** slider to speed up/slow down the file.
3. If it is an image, use the **Image Resize** slider to scale the resolution.
4. Set the target size in MB, and click **Start Compression**.
5. Once compression succeeds, click **Go to File Location** or double-click items in the folder preview tree to view the outputs.

### Option B: Command-Line Interface (CLI)
For batch tasks or scripting:
```bash
# Compress a video to a standard 15MB target at 1.5x speed (saves to c:\Dev\tools\Compress\DONE)
python compress.py input.mp4 -s 1.5

# Compress and resize an image to 50% scale under 2MB
python compress.py input.jpg output_dir 2.0 -r 0.5

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
