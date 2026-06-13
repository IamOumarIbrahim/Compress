import os
import subprocess
import sys
import threading
import io
import zipfile
import shutil
import tempfile
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText
from PIL import Image
from pypdf import PdfReader, PdfWriter

def find_ffmpeg_tools():
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["ffprobe", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return "ffmpeg", "ffprobe"
    except FileNotFoundError:
        pass

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

def get_atempo_filter(speed):
    if speed == 1.0:
        return ""
    filters = []
    temp_speed = speed
    while temp_speed > 2.0:
        filters.append("atempo=2.0")
        temp_speed /= 2.0
    while temp_speed < 0.5:
        filters.append("atempo=0.5")
        temp_speed /= 0.5
    if temp_speed != 1.0:
        filters.append(f"atempo={temp_speed:.4f}")
    return ",".join(filters)

def format_duration(seconds):
    secs = int(seconds)
    hours = secs // 3600
    minutes = (secs % 3600) // 60
    remaining_secs = secs % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{remaining_secs:02d}"
    return f"{minutes:02d}:{remaining_secs:02d}"

def compress_audio(input_file, output_dir, max_size_mb=15.0, speed=1.0, log_callback=print):
    ffmpeg_path, ffprobe_path = find_ffmpeg_tools()
    log_callback(f"Using ffmpeg: {ffmpeg_path}")
    log_callback(f"Using ffprobe: {ffprobe_path}")
    
    try:
        duration = get_audio_duration(ffprobe_path, input_file)
    except Exception as e:
        log_callback(f"Error reading duration: {e}")
        return False
        
    original_duration = duration
    if speed != 1.0:
        duration = original_duration / speed
        log_callback(f"Audio duration adjusted for speed ({speed}x): {original_duration:.2f}s ➔ {duration:.2f}s")
    else:
        log_callback(f"Audio duration: {duration:.2f} seconds ({duration/60:.2f} minutes)")
    
    target_size_bytes = max_size_mb * 1024 * 1024 * 0.96
    target_total_bits = target_size_bytes * 8
    
    raw_bitrate_kbps = (target_total_bits / duration) / 1000
    log_callback(f"Raw target bitrate: {raw_bitrate_kbps:.2f} kbps")
    
    _, ext = os.path.splitext(input_file.lower())
    if ext in ('.wav', '.flac', '.wma'):
        codec = "libmp3lame"
        out_ext = ".mp3"
        log_callback(f"Transcoding lossless {ext} to compressed .mp3.")
        
        standard_bitrates = [8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320]
        selected_kbps = 8
        for b in sorted(standard_bitrates, reverse=True):
            if b <= raw_bitrate_kbps:
                selected_kbps = b
                break
    elif ext == ".ogg":
        codec = "libvorbis"
        out_ext = ".ogg"
        selected_kbps = min(256, max(16, int(raw_bitrate_kbps)))
    elif ext in (".m4a", ".aac"):
        codec = "aac"
        out_ext = ext
        selected_kbps = min(256, max(16, int(raw_bitrate_kbps)))
    else:
        codec = "libmp3lame"
        out_ext = ".mp3"
        standard_bitrates = [8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320]
        selected_kbps = 8
        for b in sorted(standard_bitrates, reverse=True):
            if b <= raw_bitrate_kbps:
                selected_kbps = b
                break
                
    log_callback(f"Selected bitrate: {selected_kbps} kbps")
    
    filename = os.path.basename(input_file)
    base, _ = os.path.splitext(filename)
    output_file = os.path.join(output_dir, base + out_ext)
    
    cmd = [ffmpeg_path, "-y", "-i", input_file, "-map", "0:a:0", "-codec:a", codec]
    
    if selected_kbps < 64:
        log_callback("Downmixing to mono to improve quality at lower bitrate.")
        cmd.extend(["-ac", "1"])
        
    if selected_kbps < 32:
        log_callback("Lowering sampling rate to 22050 Hz to reduce artifacts at very low bitrate.")
        cmd.extend(["-ar", "22050"])
        
    if speed != 1.0:
        atempo_str = get_atempo_filter(speed)
        if atempo_str:
            cmd.extend(["-filter:a", atempo_str])
            
    cmd.extend(["-b:a", f"{selected_kbps}k", output_file])
    
    log_callback(f"Running FFmpeg: {' '.join(cmd)}")
    
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

def compress_video(input_file, output_dir, max_size_mb=15.0, speed=1.0, log_callback=print):
    ffmpeg_path, ffprobe_path = find_ffmpeg_tools()
    log_callback(f"Using ffmpeg: {ffmpeg_path}")
    log_callback(f"Using ffprobe: {ffprobe_path}")
    
    try:
        duration = get_audio_duration(ffprobe_path, input_file)
    except Exception as e:
        log_callback(f"Error reading video duration: {e}")
        return False
        
    original_duration = duration
    if speed != 1.0:
        duration = original_duration / speed
        log_callback(f"Video duration adjusted for speed ({speed}x): {original_duration:.2f}s ➔ {duration:.2f}s")
    else:
        log_callback(f"Video duration: {duration:.2f} seconds ({duration/60:.2f} minutes)")
    
    # Check if video has an audio stream
    has_audio = True
    try:
        cmd_probe = [ffprobe_path, "-v", "error", "-select_streams", "a", "-show_entries", "stream=codec_type", "-of", "csv=p=0", input_file]
        res = subprocess.run(cmd_probe, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if not res.stdout.strip():
            has_audio = False
    except Exception:
        pass
    
    target_size_bytes = max_size_mb * 1024 * 1024 * 0.94
    target_total_bits = target_size_bytes * 8
    
    target_overall_bitrate_kbps = (target_total_bits / duration) / 1000
    log_callback(f"Target overall bitrate: {target_overall_bitrate_kbps:.2f} kbps")
    
    if has_audio:
        audio_bitrate_kbps = min(128, max(32, int(target_overall_bitrate_kbps * 0.15)))
        video_bitrate_kbps = max(50, int(target_overall_bitrate_kbps - audio_bitrate_kbps))
    else:
        audio_bitrate_kbps = 0
        video_bitrate_kbps = max(50, int(target_overall_bitrate_kbps))
        
    log_callback(f"Allocated bitrates: Video {video_bitrate_kbps} kbps, Audio {audio_bitrate_kbps} kbps")
    
    filename = os.path.basename(input_file)
    base, ext = os.path.splitext(filename)
    
    out_ext = ext
    if ext.lower() in ('.webm', '.wmv'):
        log_callback(f"Transcoding {ext} to standard .mp4 for better compression speed.")
        out_ext = '.mp4'
        
    output_file = os.path.join(output_dir, base + out_ext)
    
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
        
    cmd = [ffmpeg_path, "-y", "-i", input_file]
    
    if speed != 1.0:
        cmd.extend(["-filter:v", f"setpts=PTS/{speed}"])
        
    cmd.extend(["-codec:v", "libx264", "-preset", "medium", "-b:v", f"{video_bitrate_kbps}k"])
    cmd.extend(scale_filter)
    
    if has_audio:
        cmd.extend(["-map", "0:a:0", "-codec:a", "aac", "-b:a", f"{audio_bitrate_kbps}k"])
        if audio_bitrate_kbps < 64:
            cmd.extend(["-ac", "1"])
        if speed != 1.0:
            atempo_str = get_atempo_filter(speed)
            if atempo_str:
                cmd.extend(["-filter:a", atempo_str])
                
    cmd.append(output_file)
    
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

def compress_image(input_path, output_path, max_size_mb, user_scale=1.0, log_callback=print):
    target_bytes = max_size_mb * 1024 * 1024
    _, ext = os.path.splitext(input_path.lower())
    
    try:
        img = Image.open(input_path)
    except Exception as e:
        log_callback(f"Error opening image: {e}")
        return False
        
    img_format = img.format or ('JPEG' if ext in ('.jpg', '.jpeg') else 'PNG' if ext == '.png' else 'GIF')
    
    quality = 85
    scale = user_scale
    
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
        elif img_format == 'WEBP' or ext == '.webp':
            img_temp.save(img_bytes, format='WEBP', quality=quality, optimize=True)
        elif img_format == 'BMP' or ext == '.bmp':
            img_temp.save(img_bytes, format='BMP')
        elif img_format == 'TIFF' or ext in ('.tiff', '.tif'):
            img_temp.save(img_bytes, format='TIFF', compression='tiff_lzw')
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
        if attempt >= 2:
            scale = scale * 0.8
        
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
            log_callback(f"PDF compression error: {e}")
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
            log_callback(f"Error compressing Docx/Pptx/Xlsx: {e}")
            return False
            
        quality = max(20, quality - 20)
        scale = max(0.4, scale - 0.2)
        
    with open(output_path, 'wb') as f:
        f.write(compressed_data)
    return False

def compress_zip(input_path, output_path, max_size_mb, log_callback=print):
    target_bytes = max_size_mb * 1024 * 1024
    temp_dir = tempfile.mkdtemp(prefix="temp_zip_")
    
    try:
        log_callback("Extracting zip archive...")
        with zipfile.ZipFile(input_path, 'r') as z:
            z.extractall(temp_dir)
            
        compressible_files = []
        total_compressible_size = 0
        
        compressible_exts = (
            '.mp3', '.m4a', '.wav', '.flac', '.ogg', '.aac', '.wma',
            '.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.wmv',
            '.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff',
            '.pdf', '.docx', '.pptx', '.xlsx'
        )
        
        for root, dirs, files in os.walk(temp_dir):
            for file in files:
                file_path = os.path.join(root, file)
                _, ext = os.path.splitext(file.lower())
                size = os.path.getsize(file_path)
                
                if ext in compressible_exts:
                    compressible_files.append((file_path, size))
                    total_compressible_size += size
                    
        log_callback(f"Found {len(compressible_files)} compressible file(s) inside zip (Total size: {total_compressible_size/(1024*1024):.2f} MB)")
        
        if total_compressible_size > 0:
            budget_for_compressible = target_bytes * 0.90
            scale_factor = min(1.0, budget_for_compressible / total_compressible_size)
            log_callback(f"Compression scaling factor for zip elements: {scale_factor:.2f}")
            
            for file_path, original_size in compressible_files:
                file_target_mb = (original_size * scale_factor) / (1024 * 1024)
                file_target_mb = max(0.2, file_target_mb)
                
                log_callback(f"Optimizing: {os.path.basename(file_path)} -> Target {file_target_mb:.2f} MB")
                
                out_dir = os.path.dirname(file_path)
                filename = os.path.basename(file_path)
                temp_out = os.path.join(out_dir, "zipcomp_" + filename)
                
                success = False
                _, ext = os.path.splitext(file_path.lower())
                
                if ext in ('.mp3', '.m4a', '.wav', '.flac', '.ogg', '.aac', '.wma'):
                    success = compress_audio(file_path, out_dir, file_target_mb, 1.0, lambda x: None)
                elif ext in ('.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.wmv'):
                    success = compress_video(file_path, out_dir, file_target_mb, 1.0, lambda x: None)
                elif ext in ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff'):
                    success = compress_image(file_path, temp_out, file_target_mb, 1.0, lambda x: None)
                elif ext == '.pdf':
                    success = compress_pdf(file_path, temp_out, file_target_mb, lambda x: None)
                elif ext in ('.docx', '.pptx', '.xlsx'):
                    success = compress_docx_pptx(file_path, temp_out, file_target_mb, lambda x: None)
                    
                if success:
                    if os.path.exists(temp_out):
                        os.replace(temp_out, file_path)
                else:
                    if os.path.exists(temp_out):
                        os.remove(temp_out)
                        
        log_callback("Re-packing zip archive...")
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as z_out:
            for root, dirs, files in os.walk(temp_dir):
                for file in files:
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, temp_dir)
                    z_out.write(full_path, rel_path)
                    
        final_size = os.path.getsize(output_path)
        log_callback(f"ZIP packing complete! Final size: {final_size/(1024*1024):.2f} MB")
        return True
    except Exception as e:
        log_callback(f"Error compressing ZIP archive: {e}")
        return False
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

def compress_file(input_file, output_dir, max_size_mb=15.0, speed=1.0, image_scale=1.0, log_callback=print):
    if not os.path.isfile(input_file):
        log_callback(f"Error: Input file '{input_file}' not found.")
        return False
        
    os.makedirs(output_dir, exist_ok=True)
    filename = os.path.basename(input_file)
    _, ext = os.path.splitext(input_file.lower())
    
    log_callback(f"Processing compression for {filename} (target: {max_size_mb} MB)")
    
    success = False
    
    audio_exts = ('.mp3', '.m4a', '.wav', '.flac', '.ogg', '.aac', '.wma')
    video_exts = ('.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.wmv')
    image_exts = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff')
    
    if ext in audio_exts:
        success = compress_audio(input_file, output_dir, max_size_mb, speed, log_callback)
    elif ext in video_exts:
        success = compress_video(input_file, output_dir, max_size_mb, speed, log_callback)
    elif ext in image_exts:
        output_file = os.path.join(output_dir, filename)
        success = compress_image(input_file, output_file, max_size_mb, image_scale, log_callback)
    elif ext == '.pdf':
        output_file = os.path.join(output_dir, filename)
        success = compress_pdf(input_file, output_file, max_size_mb, log_callback)
    elif ext in ('.docx', '.pptx', '.xlsx'):
        output_file = os.path.join(output_dir, filename)
        success = compress_docx_pptx(input_file, output_file, max_size_mb, log_callback)
    elif ext == '.zip':
        output_file = os.path.join(output_dir, filename)
        success = compress_zip(input_file, output_file, max_size_mb, log_callback)
    else:
        log_callback(f"Error: Unsupported file extension '{ext}'")
        return False
        
    if success:
        out_ext = ext
        if ext in ('.wav', '.flac', '.wma'):
            out_ext = '.mp3'
        elif ext in ('.webm', '.wmv'):
            out_ext = '.mp4'
            
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
        self.root.title("Media Compressor v0.3")
        self.root.geometry("600x560")
        self.root.minsize(550, 480)
        
        self.style = ttk.Style()
        self.style.theme_use("clam")
        
        self.create_widgets()
        
        # Trace input variable to probe file info
        self.input_path_var.trace_add("write", self.on_path_changed)
        
    def create_widgets(self):
        main_frame = ttk.Frame(self.root, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Input File Selection
        lbl_input = ttk.Label(main_frame, text="Input File:", font=("Segoe UI", 10, "bold"))
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
        self.settings_frame = ttk.Frame(main_frame)
        self.settings_frame.pack(fill=tk.X, pady=(0, 10))
        
        lbl_size = ttk.Label(self.settings_frame, text="Target Size Limit (MB):", font=("Segoe UI", 10, "bold"))
        lbl_size.pack(side=tk.LEFT, padx=(0, 10))
        
        self.size_var = tk.StringVar(value="15.0")
        self.size_entry = ttk.Entry(self.settings_frame, textvariable=self.size_var, width=10)
        self.size_entry.pack(side=tk.LEFT)
        
        self.lbl_conditional_status = ttk.Label(self.settings_frame, text="", font=("Segoe UI", 9, "italic"))
        self.lbl_conditional_status.pack(side=tk.RIGHT, padx=10)
        
        # Conditional Options Container Frame
        self.conditional_container = ttk.Frame(main_frame)
        self.conditional_container.pack(fill=tk.X, pady=(0, 10))
        
        # Speed Frame (Audio/Video speed adjuster)
        self.speed_frame = ttk.LabelFrame(self.conditional_container, text="Speed Settings (Audio & Video)", padding="10")
        
        lbl_speed = ttk.Label(self.speed_frame, text="Speed Multiplier:")
        lbl_speed.pack(anchor=tk.W)
        
        self.speed_var = tk.DoubleVar(value=1.0)
        self.speed_slider = ttk.Scale(
            self.speed_frame, from_=0.5, to=3.0,
            variable=self.speed_var, command=self.update_speed_preview
        )
        self.speed_slider.pack(fill=tk.X, expand=True, pady=5)
        
        lbl_speed_val_frame = ttk.Frame(self.speed_frame)
        lbl_speed_val_frame.pack(fill=tk.X)
        
        self.lbl_speed_val = ttk.Label(lbl_speed_val_frame, text="1.0x", font=("Segoe UI", 9, "bold"))
        self.lbl_speed_val.pack(side=tk.LEFT)
        
        self.lbl_speed_preview = ttk.Label(lbl_speed_val_frame, text="Duration: 00:00 ➔ 00:00", font=("Segoe UI", 9, "italic"))
        self.lbl_speed_preview.pack(side=tk.RIGHT)
        
        # Image Resize Frame (Image dimensions scaling)
        self.image_resize_frame = ttk.LabelFrame(self.conditional_container, text="Image Resize Options", padding="10")
        
        lbl_scale = ttk.Label(self.image_resize_frame, text="Resize Scale (Dimensions):")
        lbl_scale.pack(anchor=tk.W)
        
        self.image_scale_var = tk.IntVar(value=100)
        self.image_slider = ttk.Scale(
            self.image_resize_frame, from_=10, to=100,
            variable=self.image_scale_var, command=self.update_image_preview
        )
        self.image_slider.pack(fill=tk.X, expand=True, pady=5)
        
        lbl_image_val_frame = ttk.Frame(self.image_resize_frame)
        lbl_image_val_frame.pack(fill=tk.X)
        
        self.lbl_image_scale_val = ttk.Label(lbl_image_val_frame, text="100%", font=("Segoe UI", 9, "bold"))
        self.lbl_image_scale_val.pack(side=tk.LEFT)
        
        self.lbl_image_preview = ttk.Label(lbl_image_val_frame, text="Resolution: 0x0 ➔ 0x0 px", font=("Segoe UI", 9, "italic"))
        self.lbl_image_preview.pack(side=tk.RIGHT)
        
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
        
        self.log_text = ScrolledText(main_frame, height=8, state=tk.DISABLED, font=("Consolas", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
    def browse_input(self):
        file_types = [
            ("All supported files", "*.mp3 *.m4a *.wav *.flac *.ogg *.aac *.wma *.mp4 *.mkv *.avi *.mov *.webm *.flv *.wmv *.jpg *.jpeg *.png *.gif *.webp *.bmp *.tiff *.pdf *.docx *.pptx *.xlsx *.zip"),
            ("Audio files", "*.mp3 *.m4a *.wav *.flac *.ogg *.aac *.wma"),
            ("Video files", "*.mp4 *.mkv *.avi *.mov *.webm *.flv *.wmv"),
            ("Image files", "*.jpg *.jpeg *.png *.gif *.webp *.bmp *.tiff"),
            ("PDF Documents", "*.pdf"),
            ("Office Documents", "*.docx *.pptx *.xlsx"),
            ("Zip Archives", "*.zip"),
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
        
    def update_speed_preview(self, val=None):
        try:
            speed = float(self.speed_var.get())
        except ValueError:
            speed = 1.0
        self.lbl_speed_val.config(text=f"{speed:.1f}x")
        
        if hasattr(self, "original_duration"):
            new_duration = self.original_duration / speed
            orig_str = format_duration(self.original_duration)
            new_str = format_duration(new_duration)
            self.lbl_speed_preview.config(text=f"Duration: {orig_str} ➔ {new_str}")
            
    def update_image_preview(self, val=None):
        try:
            scale_percent = int(self.image_scale_var.get())
        except ValueError:
            scale_percent = 100
        self.lbl_image_scale_val.config(text=f"{scale_percent}%")
        
        if hasattr(self, "original_width") and hasattr(self, "original_height"):
            new_w = int(self.original_width * (scale_percent / 100.0))
            new_h = int(self.original_height * (scale_percent / 100.0))
            self.lbl_image_preview.config(text=f"Resolution: {self.original_width}×{self.original_height} ➔ {new_w}×{new_h} px")
            
    def on_path_changed(self, *args):
        file_path = self.input_path_var.get().strip()
        self.start_probing(file_path)
        
    def start_probing(self, file_path):
        if not file_path or not os.path.isfile(file_path):
            self.hide_all_conditional_frames()
            return
        self.lbl_conditional_status.config(text="Probing file...", foreground="blue")
        threading.Thread(target=self.probe_metadata_thread, args=(file_path,), daemon=True).start()
        
    def probe_metadata_thread(self, file_path):
        _, ext = os.path.splitext(file_path.lower())
        
        audio_exts = ('.mp3', '.m4a', '.wav', '.flac', '.ogg', '.aac', '.wma')
        video_exts = ('.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.wmv')
        image_exts = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff')
        
        if ext in audio_exts or ext in video_exts:
            ffmpeg_path, ffprobe_path = find_ffmpeg_tools()
            try:
                duration = get_audio_duration(ffprobe_path, file_path)
                self.root.after(0, self.setup_audio_video_ui, duration)
            except Exception as e:
                self.root.after(0, self.log_probing_error, f"Probe error: {e}")
        elif ext in image_exts:
            try:
                # Open image headers only to get size quickly
                with Image.open(file_path) as img:
                    w, h = img.size
                self.root.after(0, self.setup_image_ui, w, h)
            except Exception as e:
                self.root.after(0, self.log_probing_error, f"Probe error: {e}")
        else:
            self.root.after(0, self.hide_all_conditional_frames)
            
    def hide_all_conditional_frames(self):
        self.speed_frame.pack_forget()
        self.image_resize_frame.pack_forget()
        self.lbl_conditional_status.config(text="")
        if hasattr(self, "original_duration"):
            delattr(self, "original_duration")
        if hasattr(self, "original_width"):
            delattr(self, "original_width")
            
    def log_probing_error(self, err_msg):
        self.hide_all_conditional_frames()
        self.lbl_conditional_status.config(text=err_msg, foreground="red")
        
    def setup_audio_video_ui(self, duration):
        self.hide_all_conditional_frames()
        self.original_duration = duration
        self.speed_frame.pack(fill=tk.X, expand=True, pady=5)
        self.update_speed_preview()
        
    def setup_image_ui(self, w, h):
        self.hide_all_conditional_frames()
        self.original_width = w
        self.original_height = h
        self.image_resize_frame.pack(fill=tk.X, expand=True, pady=5)
        self.update_image_preview()
        
    def start_compression_thread(self):
        input_file = self.input_path_var.get().strip()
        output_dir = self.output_path_var.get().strip()
        size_str = self.size_var.get().strip()
        
        if not input_file:
            messagebox.showerror("Error", "Please select an input file.")
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
        
        # Extract slider parameters
        speed = 1.0
        image_scale = 1.0
        
        _, ext = os.path.splitext(input_file.lower())
        audio_exts = ('.mp3', '.m4a', '.wav', '.flac', '.ogg', '.aac', '.wma')
        video_exts = ('.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.wmv')
        image_exts = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff')
        
        if ext in audio_exts or ext in video_exts:
            try:
                speed = float(self.speed_var.get())
            except ValueError:
                pass
        elif ext in image_exts:
            try:
                image_scale = int(self.image_scale_var.get()) / 100.0
            except ValueError:
                pass
                
        thread = threading.Thread(
            target=self.run_compression,
            args=(input_file, output_dir, max_size_mb, speed, image_scale),
            daemon=True
        )
        thread.start()
        
    def run_compression(self, input_file, output_dir, max_size_mb, speed, image_scale):
        def log_cb(msg):
            self.root.after(0, self.log, msg)
            
        success = compress_file(input_file, output_dir, max_size_mb, speed, image_scale, log_cb)
        
        def done():
            self.btn_compress.config(state=tk.NORMAL)
            if success:
                self.status_var.set("Success!")
                messagebox.showinfo("Success", "Compression completed successfully!")
                # Re-probe the path to refresh dimensions or durations on screen if outputting in-place
                self.start_probing(input_file)
            else:
                self.status_var.set("Failed")
                messagebox.showerror("Error", "Compression failed. See logs for details.")
                
        self.root.after(0, done)

def main():
    if len(sys.argv) > 1:
        # CLI Mode
        import argparse
        parser = argparse.ArgumentParser(description="Media Compressor CLI Tool")
        parser.add_argument("input_file", help="Path to input file")
        parser.add_argument("output_dir", nargs="?", default=r"c:\Dev\tools\Compress\DONE", help="Destination folder")
        parser.add_argument("target_size", type=float, nargs="?", default=15.0, help="Target MB size limit")
        parser.add_argument("-s", "--speed", type=float, default=1.0, help="Speed multiplier (0.5x to 3.0x) for audio/video")
        parser.add_argument("-r", "--resize", type=float, default=1.0, help="Image resize scale factor (0.1 to 1.0)")
        
        args = parser.parse_args()
        
        success = compress_file(
            args.input_file,
            args.output_dir,
            args.target_size,
            args.speed,
            args.resize
        )
        sys.exit(0 if success else 1)
    else:
        # GUI Mode
        root = tk.Tk()
        app = AudioCompressorGUI(root)
        root.mainloop()

if __name__ == "__main__":
    main()
