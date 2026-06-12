import os
import subprocess
import sys
import threading
import io
import zipfile
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText
from PIL import Image
from pypdf import PdfReader, PdfWriter

def find_ffmpeg_tools():
    # Check if ffmpeg/ffprobe are in PATH
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["ffprobe", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return "ffmpeg", "ffprobe"
    except FileNotFoundError:
        pass

    # Search in Winget Packages folder
    winget_dir = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages")
    if os.path.exists(winget_dir):
        ffmpeg_path = None
        ffprobe_path = None
        for root, dirs, files in os.walk(winget_dir):
            if "ffmpeg.exe" in files:
                ffmpeg_path = os.path.join(root, "ffmpeg.exe")
            if "ffprobe.exe" in files:
                ffprobe_path = os.path.join(root, "ffprobe.exe")
            if ffmpeg_path and ffprobe_path:
                return ffmpeg_path, ffprobe_path

    # Fallback defaults
    return "ffmpeg", "ffprobe"

def get_audio_duration(ffprobe_path, input_file):
    cmd = [
        ffprobe_path,
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        input_file
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
    return float(result.stdout.strip())

def compress_audio(input_file, output_dir, max_size_mb=15.0, log_callback=print):
    ffmpeg_path, ffprobe_path = find_ffmpeg_tools()
    log_callback(f"Using ffmpeg: {ffmpeg_path}")
    log_callback(f"Using ffprobe: {ffprobe_path}")
    
    try:
        duration = get_audio_duration(ffprobe_path, input_file)
    except Exception as e:
        log_callback(f"Error reading duration: {e}")
        return False
        
    log_callback(f"Audio duration: {duration:.2f} seconds ({duration/60:.2f} minutes)")
    
    target_size_bytes = max_size_mb * 1024 * 1024 * 0.96
    target_total_bits = target_size_bytes * 8
    
    raw_bitrate_kbps = (target_total_bits / duration) / 1000
    log_callback(f"Raw target bitrate: {raw_bitrate_kbps:.2f} kbps")
    
    _, ext = os.path.splitext(input_file.lower())
    if ext == ".m4a":
        codec = "aac"
        selected_kbps = min(256, max(16, int(raw_bitrate_kbps)))
    else:
        codec = "libmp3lame"
        ext = ".mp3"
        standard_bitrates = [8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320]
        selected_kbps = 8
        for b in sorted(standard_bitrates, reverse=True):
            if b <= raw_bitrate_kbps:
                selected_kbps = b
                break
                
    log_callback(f"Selected bitrate: {selected_kbps} kbps")
    
    filename = os.path.basename(input_file)
    base, _ = os.path.splitext(filename)
    output_file = os.path.join(output_dir, base + ext)
    
    cmd = [ffmpeg_path, "-y", "-i", input_file, "-map", "0:a:0", "-codec:a", codec]
    
    if selected_kbps < 64:
        log_callback("Downmixing to mono to improve quality at lower bitrate.")
        cmd.extend(["-ac", "1"])
        
    if selected_kbps < 32:
        log_callback("Lowering sampling rate to 22050 Hz to reduce artifacts at very low bitrate.")
        cmd.extend(["-ar", "22050"])
        
    cmd.extend(["-b:a", f"{selected_kbps}k", output_file])
    
    log_callback(f"Running FFmpeg command: {' '.join(cmd)}")
    
    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        while True:
            line = process.stdout.readline()
            if not line:
                break
            line_str = line.strip()
            if line_str and ("size=" in line_str or "time=" in line_str or "bitrate=" in line_str):
                log_callback(line_str)
        process.wait()
        return process.returncode == 0
    except Exception as e:
        log_callback(f"Error running FFmpeg: {e}")
        return False

def compress_video(input_file, output_dir, max_size_mb=15.0, log_callback=print):
    ffmpeg_path, ffprobe_path = find_ffmpeg_tools()
    log_callback(f"Using ffmpeg: {ffmpeg_path}")
    log_callback(f"Using ffprobe: {ffprobe_path}")
    
    try:
        duration = get_audio_duration(ffprobe_path, input_file)
    except Exception as e:
        log_callback(f"Error reading video duration: {e}")
        return False
        
    log_callback(f"Video duration: {duration:.2f} seconds ({duration/60:.2f} minutes)")
    
    target_size_bytes = max_size_mb * 1024 * 1024 * 0.94
    target_total_bits = target_size_bytes * 8
    
    target_overall_bitrate_kbps = (target_total_bits / duration) / 1000
    log_callback(f"Target overall bitrate: {target_overall_bitrate_kbps:.2f} kbps")
    
    audio_bitrate_kbps = min(128, max(32, int(target_overall_bitrate_kbps * 0.15)))
    video_bitrate_kbps = max(50, int(target_overall_bitrate_kbps - audio_bitrate_kbps))
    
    log_callback(f"Allocated bitrates: Video {video_bitrate_kbps} kbps, Audio {audio_bitrate_kbps} kbps")
    
    filename = os.path.basename(input_file)
    base, _ = os.path.splitext(filename)
    output_file = os.path.join(output_dir, base + ".mp4")
    
    scale_filter = []
    if video_bitrate_kbps < 200:
        log_callback("Bitrate is very low. Downscaling video to 240p.")
        scale_filter = ["-vf", "scale=-2:240"]
    elif video_bitrate_kbps < 500:
        log_callback("Bitrate is low. Downscaling video to 360p.")
        scale_filter = ["-vf", "scale=-2:360"]
    elif video_bitrate_kbps < 1000:
        log_callback("Bitrate is moderate. Downscaling video to 480p.")
        scale_filter = ["-vf", "scale=-2:480"]
    else:
        log_callback("Bitrate is high. Downscaling video to 720p.")
        scale_filter = ["-vf", "scale=-2:720"]
        
    cmd = [
        ffmpeg_path, "-y", "-i", input_file,
        "-codec:v", "libx264", "-preset", "medium",
        "-b:v", f"{video_bitrate_kbps}k"
    ]
    cmd.extend(scale_filter)
    cmd.extend([
        "-codec:a", "aac", "-b:a", f"{audio_bitrate_kbps}k",
        "-ac", "1",
        output_file
    ])
    
    log_callback(f"Running video compression: {' '.join(cmd)}")
    
    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        while True:
            line = process.stdout.readline()
            if not line:
                break
            line_str = line.strip()
            if line_str and ("size=" in line_str or "time=" in line_str or "bitrate=" in line_str or "frame=" in line_str):
                log_callback(line_str)
        process.wait()
        return process.returncode == 0
    except Exception as e:
        log_callback(f"Error running FFmpeg: {e}")
        return False

def compress_image(input_path, output_path, max_size_mb, log_callback=print):
    target_bytes = max_size_mb * 1024 * 1024
    _, ext = os.path.splitext(input_path.lower())
    
    try:
        img = Image.open(input_path)
    except Exception as e:
        log_callback(f"Error opening image: {e}")
        return False
        
    img_format = img.format or ('JPEG' if ext in ('.jpg', '.jpeg') else 'PNG' if ext == '.png' else 'GIF')
    
    quality = 85
    scale = 1.0
    
    for attempt in range(5):
        img_temp = img.copy()
        if scale < 1.0:
            new_size = (int(img_temp.width * scale), int(img_temp.height * scale))
            img_temp = img_temp.resize(new_size, Image.Resampling.LANCZOS)
            
        img_bytes = io.BytesIO()
        if img_format == 'JPEG' or ext in ('.jpg', '.jpeg'):
            img_temp.save(img_bytes, format='JPEG', quality=quality, optimize=True)
        elif img_format == 'PNG' or ext == '.png':
            if attempt >= 2:
                img_temp = img_temp.convert('P', palette=Image.ADAPTIVE, colors=256)
            img_temp.save(img_bytes, format='PNG', optimize=True)
        elif img_format == 'GIF' or ext == '.gif':
            if getattr(img, "is_animated", False):
                frames = []
                for frame_idx in range(img.n_frames):
                    img.seek(frame_idx)
                    frame = img.copy()
                    if scale < 1.0:
                        new_size = (int(frame.width * scale), int(frame.height * scale))
                        frame = frame.resize(new_size, Image.Resampling.LANCZOS)
                    if attempt >= 2:
                        frame = frame.convert('P', palette=Image.ADAPTIVE, colors=256)
                    frames.append(frame)
                
                frames[0].save(
                    img_bytes,
                    format='GIF',
                    save_all=True,
                    append_images=frames[1:],
                    loop=img.info.get('loop', 0),
                    duration=img.info.get('duration', 100),
                    optimize=True
                )
            else:
                img_temp.save(img_bytes, format='GIF', optimize=True)
        else:
            img_temp.save(img_bytes, format=img_format)
            
        data = img_bytes.getvalue()
        current_size = len(data)
        log_callback(f"Attempt {attempt+1}: Quality={quality}, Scale={scale:.2f} -> Size={current_size/(1024*1024):.2f} MB")
        
        if current_size <= target_bytes:
            with open(output_path, 'wb') as f:
                f.write(data)
            return True
            
        quality = max(20, quality - 20)
        scale = max(0.3, scale - 0.2)
        
    with open(output_path, 'wb') as f:
        f.write(data)
    return False

def compress_pdf(input_path, output_path, max_size_mb, log_callback=print):
    target_bytes = max_size_mb * 1024 * 1024
    quality = 80
    
    for attempt in range(4):
        try:
            writer = PdfWriter(clone_from=input_path)
            writer.compress_identical_objects(remove_duplicates=True, remove_unreferenced=True)
            
            for page in writer.pages:
                page.compress_content_streams()
                for img in page.images:
                    try:
                        img.replace(img.image, quality=quality)
                    except Exception:
                        pass
                        
            pdf_bytes = io.BytesIO()
            writer.write(pdf_bytes)
            data = pdf_bytes.getvalue()
            current_size = len(data)
            
            log_callback(f"Attempt {attempt+1}: PDF Image Quality={quality} -> Size={current_size/(1024*1024):.2f} MB")
            
            if current_size <= target_bytes:
                with open(output_path, 'wb') as f:
                    f.write(data)
                return True
        except Exception as e:
            log_callback(f"PDF compression error at attempt {attempt+1}: {e}")
            return False
            
        quality = max(20, quality - 20)
        
    with open(output_path, 'wb') as f:
        f.write(data)
    return False

def compress_docx_pptx(input_path, output_path, max_size_mb, log_callback=print):
    target_bytes = max_size_mb * 1024 * 1024
    quality = 80
    scale = 1.0
    
    for attempt in range(4):
        try:
            in_buf = io.BytesIO()
            with zipfile.ZipFile(input_path, 'r') as yin:
                with zipfile.ZipFile(in_buf, 'w', zipfile.ZIP_DEFLATED) as yout:
                    for item in yin.infolist():
                        data = yin.read(item.filename)
                        is_media_image = False
                        lower_name = item.filename.lower()
                        if ('word/media/' in lower_name or 'ppt/media/' in lower_name or 'xl/media/' in lower_name):
                            if lower_name.endswith(('.jpg', '.jpeg', '.png', '.gif')):
                                is_media_image = True
                                
                        if is_media_image:
                            try:
                                img = Image.open(io.BytesIO(data))
                                img_format = img.format
                                
                                if scale < 1.0:
                                    new_size = (int(img.width * scale), int(img.height * scale))
                                    img = img.resize(new_size, Image.Resampling.LANCZOS)
                                    
                                img_bytes = io.BytesIO()
                                if img_format == 'JPEG' or lower_name.endswith(('.jpg', '.jpeg')):
                                    img.save(img_bytes, format='JPEG', quality=quality, optimize=True)
                                elif img_format == 'PNG' or lower_name.endswith('.png'):
                                    if attempt >= 2:
                                        img = img.convert('P', palette=Image.ADAPTIVE, colors=256)
                                    img.save(img_bytes, format='PNG', optimize=True)
                                elif img_format == 'GIF' or lower_name.endswith('.gif'):
                                    img.save(img_bytes, format='GIF', optimize=True)
                                else:
                                    img.save(img_bytes, format=img_format)
                                    
                                data = img_bytes.getvalue()
                            except Exception as e:
                                log_callback(f"Failed to compress embedded image {item.filename}: {e}")
                                
                        yout.writestr(item, data)
                        
            compressed_data = in_buf.getvalue()
            current_size = len(compressed_data)
            log_callback(f"Attempt {attempt+1}: Quality={quality}, Scale={scale:.2f} -> Size={current_size/(1024*1024):.2f} MB")
            
            if current_size <= target_bytes:
                with open(output_path, 'wb') as f:
                    f.write(compressed_data)
                return True
        except Exception as e:
            log_callback(f"Error compressing Docx/Pptx at attempt {attempt+1}: {e}")
            return False
            
        quality = max(20, quality - 20)
        scale = max(0.4, scale - 0.2)
        
    with open(output_path, 'wb') as f:
        f.write(compressed_data)
    return False

def compress_file(input_file, output_dir, max_size_mb=15.0, log_callback=print):
    if not os.path.isfile(input_file):
        log_callback(f"Error: Input file '{input_file}' not found.")
        return False
        
    os.makedirs(output_dir, exist_ok=True)
    filename = os.path.basename(input_file)
    _, ext = os.path.splitext(input_file.lower())
    
    log_callback(f"Processing compression for {filename} (target: {max_size_mb} MB)")
    
    success = False
    if ext in ('.mp3', '.m4a'):
        success = compress_audio(input_file, output_dir, max_size_mb, log_callback)
    elif ext == '.mp4':
        success = compress_video(input_file, output_dir, max_size_mb, log_callback)
    elif ext in ('.jpg', '.jpeg', '.png', '.gif'):
        output_file = os.path.join(output_dir, filename)
        success = compress_image(input_file, output_file, max_size_mb, log_callback)
    elif ext == '.pdf':
        output_file = os.path.join(output_dir, filename)
        success = compress_pdf(input_file, output_file, max_size_mb, log_callback)
    elif ext in ('.docx', '.pptx'):
        output_file = os.path.join(output_dir, filename)
        success = compress_docx_pptx(input_file, output_file, max_size_mb, log_callback)
    else:
        log_callback(f"Error: Unsupported file extension '{ext}'")
        return False
        
    if success:
        # Get final output path
        out_ext = ".mp4" if ext == ".mp4" else ext
        base, _ = os.path.splitext(filename)
        output_file_path = os.path.join(output_dir, base + out_ext)
        if os.path.exists(output_file_path):
            final_size = os.path.getsize(output_file_path)
            final_size_mb = final_size / (1024 * 1024)
            log_callback(f"Verification: output size is {final_size_mb:.2f} MB")
            if final_size_mb <= max_size_mb:
                log_callback("SUCCESS: File size is under the target limit.")
                return True
            else:
                log_callback("WARNING: Compressed size still exceeds the target limit.")
                return False
    return False

class AudioCompressorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Media Compressor (All Formats)")
        self.root.geometry("600x480")
        self.root.minsize(500, 400)
        
        self.style = ttk.Style()
        self.style.theme_use("clam")
        
        self.create_widgets()
        
    def create_widgets(self):
        main_frame = ttk.Frame(self.root, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Input File Selection
        lbl_input = ttk.Label(main_frame, text="Input File (Audio, Video, Images, Documents):", font=("Segoe UI", 10, "bold"))
        lbl_input.pack(anchor=tk.W, pady=(0, 2))
        
        input_entry_frame = ttk.Frame(main_frame)
        input_entry_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.input_path_var = tk.StringVar()
        self.input_entry = ttk.Entry(input_entry_frame, textvariable=self.input_path_var)
        self.input_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        btn_browse_input = ttk.Button(input_entry_frame, text="Browse...", command=self.browse_input)
        btn_browse_input.pack(side=tk.RIGHT)
        
        # Output Directory Selection
        lbl_output = ttk.Label(main_frame, text="Output Directory:", font=("Segoe UI", 10, "bold"))
        lbl_output.pack(anchor=tk.W, pady=(0, 2))
        
        output_entry_frame = ttk.Frame(main_frame)
        output_entry_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.output_path_var = tk.StringVar(value=r"c:\Dev\tools\Compress\DONE")
        self.output_entry = ttk.Entry(output_entry_frame, textvariable=self.output_path_var)
        self.output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        btn_browse_output = ttk.Button(output_entry_frame, text="Browse...", command=self.browse_output)
        btn_browse_output.pack(side=tk.RIGHT)
        
        # Settings Frame (Target Size)
        settings_frame = ttk.Frame(main_frame)
        settings_frame.pack(fill=tk.X, pady=(0, 15))
        
        lbl_size = ttk.Label(settings_frame, text="Target Size Limit (MB):", font=("Segoe UI", 10, "bold"))
        lbl_size.pack(side=tk.LEFT, padx=(0, 10))
        
        self.size_var = tk.StringVar(value="15.0")
        self.size_entry = ttk.Entry(settings_frame, textvariable=self.size_var, width=10)
        self.size_entry.pack(side=tk.LEFT)
        
        # Action Button
        self.btn_compress = ttk.Button(main_frame, text="Start Compression", command=self.start_compression_thread)
        self.btn_compress.pack(fill=tk.X, pady=(0, 10))
        
        # Status
        self.status_var = tk.StringVar(value="Ready")
        self.lbl_status = ttk.Label(main_frame, textvariable=self.status_var, font=("Segoe UI", 9, "italic"))
        self.lbl_status.pack(anchor=tk.W, pady=(0, 5))
        
        # Logs
        lbl_logs = ttk.Label(main_frame, text="Logs:", font=("Segoe UI", 9))
        lbl_logs.pack(anchor=tk.W)
        
        self.log_text = ScrolledText(main_frame, height=10, state=tk.DISABLED, font=("Consolas", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
    def browse_input(self):
        file_types = [
            ("All supported media", "*.mp3 *.m4a *.mp4 *.jpg *.jpeg *.png *.gif *.pdf *.docx *.pptx"),
            ("Audio files", "*.mp3 *.m4a"),
            ("Video files", "*.mp4"),
            ("Image files", "*.jpg *.jpeg *.png *.gif"),
            ("PDF Documents", "*.pdf"),
            ("Word/Powerpoint Documents", "*.docx *.pptx"),
            ("All files", "*.*")
        ]
        file_path = filedialog.askopenfilename(filetypes=file_types)
        if file_path:
            self.input_path_var.set(file_path)
            
    def browse_output(self):
        dir_path = filedialog.askdirectory()
        if dir_path:
            self.output_path_var.set(dir_path)
            
    def log(self, message):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
        
    def start_compression_thread(self):
        input_file = self.input_path_var.get().strip()
        output_dir = self.output_path_var.get().strip()
        size_str = self.size_var.get().strip()
        
        if not input_file:
            messagebox.showerror("Error", "Please select an input audio file.")
            return
            
        if not output_dir:
            messagebox.showerror("Error", "Please select an output directory.")
            return
            
        try:
            max_size_mb = float(size_str)
            if max_size_mb <= 0:
                raise ValueError()
        except ValueError:
            messagebox.showerror("Error", "Please enter a valid positive number for target size.")
            return
            
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)
        
        self.btn_compress.config(state=tk.DISABLED)
        self.status_var.set("Compressing...")
        
        thread = threading.Thread(
            target=self.run_compression,
            args=(input_file, output_dir, max_size_mb),
            daemon=True
        )
        thread.start()
        
    def run_compression(self, input_file, output_dir, max_size_mb):
        def log_cb(msg):
            self.root.after(0, self.log, msg)
            
        success = compress_file(input_file, output_dir, max_size_mb, log_cb)
        
        def done():
            self.btn_compress.config(state=tk.NORMAL)
            if success:
                self.status_var.set("Success!")
                messagebox.showinfo("Success", "Compression completed successfully!")
            else:
                self.status_var.set("Failed")
                messagebox.showerror("Error", "Compression failed. See logs for details.")
                
        self.root.after(0, done)

def main():
    if len(sys.argv) > 1:
        input_file = sys.argv[1]
        output_dir = r"c:\Dev\tools\Compress\DONE"
        max_size = 15.0
        
        if len(sys.argv) > 2:
            output_dir = sys.argv[2]
        if len(sys.argv) > 3:
            try:
                max_size = float(sys.argv[3])
            except ValueError:
                pass
                
        success = compress_file(input_file, output_dir, max_size)
        sys.exit(0 if success else 1)
    else:
        root = tk.Tk()
        app = AudioCompressorGUI(root)
        root.mainloop()

if __name__ == "__main__":
    main()
