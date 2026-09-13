import os
import time
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog

import paramiko

from PIL import Image, ImageDraw, ImageFont
from luma.core.interface.serial import i2c
from luma.oled.device import ssd1306


OLED_ADDRESS = 0x3C
OLED_WIDTH = 128
OLED_HEIGHT = 64

SFTP_PORT = 22

serial = i2c(
    port=1,
    address=OLED_ADDRESS
)

oled = ssd1306(
    serial,
    width=OLED_WIDTH,
    height=OLED_HEIGHT
)

oled_lock = threading.Lock()

try:
    font_small = ImageFont.truetype(
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 9
    )
    font_tiny = ImageFont.truetype(
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 7
    )
    font_big = ImageFont.truetype(
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 13
    )
except:
    font_small = ImageFont.load_default()
    font_tiny = ImageFont.load_default()
    font_big = ImageFont.load_default()


ssh_client = None
sftp = None

current_path = "."
current_items = []

download_running = False


def oled_show(title, line1="", line2="", percent=None, animated=False):
    with oled_lock:
        img = Image.new("1", (OLED_WIDTH, OLED_HEIGHT), 0)
        draw = ImageDraw.Draw(img)

        draw.text(
            (2, 1),
            title[:20],
            font=font_small,
            fill=255
        )

        draw.line(
            (0, 13, 127, 13),
            fill=255
        )

        draw.text(
            (2, 17),
            line1[:21],
            font=font_small,
            fill=255
        )

        draw.text(
            (2, 29),
            line2[:21],
            font=font_tiny,
            fill=255
        )

        if percent is not None:
            p = max(0, min(100, percent))

            draw.rectangle(
                (2, 43, 125, 53),
                outline=255
            )

            width = int(119 * p / 100)

            if width > 0:
                draw.rectangle(
                    (4, 45, 4 + width, 51),
                    fill=255
                )

            draw.text(
                (45, 55),
                f"{p:.0f}%",
                font=font_tiny,
                fill=255
            )

        elif animated:
            dots = int(time.time() * 3) % 4
            text = "." * dots

            draw.text(
                (2, 43),
                text,
                font=font_big,
                fill=255
            )

        oled.display(img)


def oled_idle():
    oled_show(
        "DH SFTP",
        "Laptop File Transfer",
        "Waiting...",
        animated=True
    )


def oled_connecting(ip):
    oled_show(
        "CONNECTING",
        ip,
        "SFTP port 22",
        animated=True
    )


def oled_connected(ip):
    oled_show(
        "CONNECTED",
        ip,
        "SFTP READY"
    )


def oled_error(text):
    oled_show(
        "ERROR",
        text[:21],
        "Check connection"
    )


def oled_download(filename, percent, transferred, total):
    if total:
        mb1 = transferred / 1024 / 1024
        mb2 = total / 1024 / 1024
        line2 = f"{mb1:.1f}/{mb2:.1f} MB"
    else:
        line2 = "Unknown size"

    with oled_lock:
        img = Image.new("1", (128, 64), 0)
        draw = ImageDraw.Draw(img)

        draw.text(
            (2, 1),
            "DOWNLOADING",
            font=font_small,
            fill=255
        )

        draw.line(
            (0, 13, 127, 13),
            fill=255
        )

        name = os.path.basename(filename)

        if len(name) > 20:
            name = name[-20:]

        draw.text(
            (2, 17),
            name,
            font=font_tiny,
            fill=255
        )

        draw.text(
            (2, 29),
            line2,
            font=font_tiny,
            fill=255
        )

        p = max(0, min(100, percent))

        draw.rectangle(
            (2, 40, 125, 51),
            outline=255
        )

        width = int(119 * p / 100)

        if width > 0:
            draw.rectangle(
                (4, 42, 4 + width, 49),
                fill=255
            )

        draw.text(
            (48, 54),
            f"{p:.0f}%",
            font=font_tiny,
            fill=255
        )

        oled.display(img)


def oled_complete(filename):
    oled_show(
        "COMPLETE",
        os.path.basename(filename)[:21],
        "Download finished"
    )


def normalize_path(path):
    if not path:
        return "."

    return path


def connect_sftp(ip, username, password):
    global ssh_client
    global sftp

    try:
        oled_connecting(ip)

        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(
            paramiko.AutoAddPolicy()
        )

        ssh_client.connect(
            hostname=ip,
            port=SFTP_PORT,
            username=username,
            password=password,
            timeout=10,
            banner_timeout=10,
            auth_timeout=10
        )

        sftp = ssh_client.open_sftp()

        oled_connected(ip)

        return True, ""

    except Exception as e:
        ssh_client = None
        sftp = None

        oled_error(str(e)[:21])

        return False, str(e)


def disconnect_sftp():
    global ssh_client
    global sftp

    try:
        if sftp:
            sftp.close()
    except:
        pass

    try:
        if ssh_client:
            ssh_client.close()
    except:
        pass

    sftp = None
    ssh_client = None


def format_size(size):
    if size < 1024:
        return f"{size} B"

    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"

    if size < 1024 * 1024 * 1024:
        return f"{size / 1024 / 1024:.1f} MB"

    return f"{size / 1024 / 1024 / 1024:.2f} GB"


def get_remote_items(path):
    global sftp

    items = []

    for attr in sftp.listdir_attr(path):
        name = attr.filename

        if name in [".", ".."]:
            continue

        is_dir = False

        try:
            import stat
            is_dir = stat.S_ISDIR(attr.st_mode)
        except:
            pass

        items.append({
            "name": name,
            "path": os.path.join(path, name).replace("\\", "/"),
            "is_dir": is_dir,
            "size": attr.st_size
        })

    items.sort(
        key=lambda x: (
            not x["is_dir"],
            x["name"].lower()
        )
    )

    return items


def refresh_files():
    global current_items

    if not sftp:
        return

    try:
        current_items = get_remote_items(current_path)

        tree.delete(*tree.get_children())

        for item in current_items:
            if item["is_dir"]:
                icon = "📁"
                size = ""
                kind = "Folder"
            else:
                icon = "📄"
                size = format_size(item["size"])
                kind = "File"

            tree.insert(
                "",
                "end",
                values=(
                    icon + " " + item["name"],
                    kind,
                    size
                )
            )

        path_var.set(current_path)

    except Exception as e:
        messagebox.showerror(
            "SFTP Error",
            str(e)
        )


def go_back():
    global current_path

    if current_path in [".", "/"]:
        return

    parent = os.path.dirname(current_path)

    if not parent:
        parent = "."

    current_path = parent

    refresh_files()


def open_selected(event=None):
    global current_path

    selected = tree.selection()

    if not selected:
        return

    index = tree.index(selected[0])

    if index >= len(current_items):
        return

    item = current_items[index]

    if item["is_dir"]:
        current_path = item["path"]
        refresh_files()


def selected_file():
    selected = tree.selection()

    if not selected:
        return None

    index = tree.index(selected[0])

    if index >= len(current_items):
        return None

    item = current_items[index]

    if item["is_dir"]:
        return None

    return item


def download_file():
    global download_running

    if download_running:
        return

    item = selected_file()

    if not item:
        messagebox.showwarning(
            "Select File",
            "Please select a file."
        )
        return

    destination = filedialog.askdirectory(
        title="Choose Pi Destination Folder",
        initialdir="/home/pi"
    )

    if not destination:
        return

    filename = item["name"]

    local_path = os.path.join(
        destination,
        filename
    )

    if os.path.exists(local_path):
        answer = messagebox.askyesno(
            "File Exists",
            f"{filename}\nalready exists.\n\nOverwrite?"
        )

        if not answer:
            return

    download_running = True

    download_button.config(
        state="disabled"
    )

    refresh_button.config(
        state="disabled"
    )

    back_button.config(
        state="disabled"
    )

    progress_var.set(0)
    percent_label.config(text="0%")
    speed_label.config(text="Starting...")

    thread = threading.Thread(
        target=download_worker,
        args=(
            item["path"],
            local_path,
            item["size"],
            filename
        ),
        daemon=True
    )

    thread.start()


def download_worker(
    remote_path,
    local_path,
    total_size,
    filename
):
    global download_running

    start_time = time.time()
    last_oled = 0

    try:

        def progress_callback(transferred, total):
            nonlocal last_oled

            if total > 0:
                percent = (
                    transferred / total
                ) * 100
            else:
                percent = 0

            elapsed = time.time() - start_time

            if elapsed > 0:
                speed = (
                    transferred / elapsed
                )

                if speed >= 1024 * 1024:
                    speed_text = (
                        f"{speed / 1024 / 1024:.2f} MB/s"
                    )
                else:
                    speed_text = (
                        f"{speed / 1024:.1f} KB/s"
                    )
            else:
                speed_text = "Starting..."

            root.after(
                0,
                update_progress,
                percent,
                speed_text
            )

            now = time.time()

            if (
                now - last_oled >= 0.15
                or transferred >= total
            ):
                last_oled = now

                oled_download(
                    filename,
                    percent,
                    transferred,
                    total
                )

        sftp.get(
            remote_path,
            local_path,
            callback=progress_callback,
            prefetch=True
        )

        oled_complete(filename)

        root.after(
            0,
            download_finished,
            True,
            f"Downloaded:\n{local_path}"
        )

    except Exception as e:

        oled_error(
            str(e)[:21]
        )

        root.after(
            0,
            download_finished,
            False,
            str(e)
        )

    finally:
        download_running = False


def update_progress(percent, speed):
    progress_var.set(percent)

    percent_label.config(
        text=f"{percent:.1f}%"
    )

    speed_label.config(
        text=speed
    )


def download_finished(success, message):
    download_button.config(
        state="normal"
    )

    refresh_button.config(
        state="normal"
    )

    back_button.config(
        state="normal"
    )

    if success:
        progress_var.set(100)
        percent_label.config(text="100%")
        speed_label.config(text="Completed")

        messagebox.showinfo(
            "Download Complete",
            message
        )

    else:
        messagebox.showerror(
            "Download Error",
            message
        )


def login_window():
    login = tk.Toplevel(root)
    login.title("SFTP Login")
    login.geometry("380x240")
    login.resizable(False, False)

    login.transient(root)
    login.grab_set()

    tk.Label(
        login,
        text="Laptop IP",
        font=("Arial", 11)
    ).pack(
        pady=(18, 3)
    )

    ip_entry = tk.Entry(
        login,
        font=("Arial", 12),
        width=28
    )

    ip_entry.pack()

    ip_entry.insert(
        0,
        ip_var.get()
    )

    tk.Label(
        login,
        text="Windows Username",
        font=("Arial", 11)
    ).pack(
        pady=(10, 3)
    )

    user_entry = tk.Entry(
        login,
        font=("Arial", 12),
        width=28
    )

    user_entry.pack()

    tk.Label(
        login,
        text="Windows Password",
        font=("Arial", 11)
    ).pack(
        pady=(10, 3)
    )

    pass_entry = tk.Entry(
        login,
        font=("Arial", 12),
        width=28,
        show="*"
    )

    pass_entry.pack()

    status = tk.Label(
        login,
        text="",
        font=("Arial", 9)
    )

    status.pack(
        pady=5
    )

    def do_connect():

        ip = ip_entry.get().strip()
        username = user_entry.get().strip()
        password = pass_entry.get()

        if not ip:
            messagebox.showwarning(
                "IP Required",
                "Enter laptop IP address.",
                parent=login
            )
            return

        if not username:
            messagebox.showwarning(
                "Username Required",
                "Enter Windows username.",
                parent=login
            )
            return

        connect_button.config(
            state="disabled"
        )

        status.config(
            text="Connecting..."
        )

        def worker():

            ok, error = connect_sftp(
                ip,
                username,
                password
            )

            def finish():

                connect_button.config(
                    state="normal"
                )

                if ok:

                    ip_var.set(ip)

                    login.grab_release()
                    login.destroy()

                    global current_path
                    current_path = "."

                    refresh_files()

                    connection_status.config(
                        text=f"Connected: {ip}"
                    )

                    oled_connected(ip)

                else:

                    status.config(
                        text="Connection failed"
                    )

                    messagebox.showerror(
                        "SFTP Connection Failed",
                        error,
                        parent=login
                    )

            root.after(
                0,
                finish
            )

        threading.Thread(
            target=worker,
            daemon=True
        ).start()

    connect_button = tk.Button(
        login,
        text="OK",
        font=("Arial", 11, "bold"),
        width=12,
        command=do_connect
    )

    connect_button.pack(
        pady=5
    )

    ip_entry.focus()

    login.bind(
        "<Return>",
        lambda e: do_connect()
    )


def change_ip():
    login_window()


def on_close():
    disconnect_sftp()

    try:
        oled.clear()
    except:
        pass

    root.destroy()


root = tk.Tk()

root.title(
    "DH Laptop SFTP Transfer"
)

root.geometry(
    "850x600"
)

root.minsize(
    700,
    500
)

root.protocol(
    "WM_DELETE_WINDOW",
    on_close
)


# =========================
# TOP BAR
# =========================

top_frame = tk.Frame(
    root,
    padx=10,
    pady=8
)

top_frame.pack(
    fill="x"
)

tk.Label(
    top_frame,
    text="Laptop IP:",
    font=("Arial", 11, "bold")
).pack(
    side="left"
)


ip_var = tk.StringVar(
    value="172.18.57.102"
)

ip_entry_main = tk.Entry(
    top_frame,
    textvariable=ip_var,
    font=("Arial", 12),
    width=20
)

ip_entry_main.pack(
    side="left",
    padx=8
)


connect_top_button = tk.Button(
    top_frame,
    text="OK",
    font=("Arial", 10, "bold"),
    width=8,
    command=login_window
)

connect_top_button.pack(
    side="left"
)


connection_status = tk.Label(
    top_frame,
    text="Not Connected",
    font=("Arial", 10)
)

connection_status.pack(
    side="left",
    padx=15
)


# =========================
# PATH BAR
# =========================

path_frame = tk.Frame(
    root,
    padx=10
)

path_frame.pack(
    fill="x"
)

tk.Label(
    path_frame,
    text="Remote Path:"
).pack(
    side="left"
)

path_var = tk.StringVar(
    value="."
)

path_entry = tk.Entry(
    path_frame,
    textvariable=path_var,
    font=("Arial", 10)
)

path_entry.pack(
    side="left",
    fill="x",
    expand=True,
    padx=8
)

path_entry.bind(
    "<Return>",
    lambda e: path_from_entry()
)


def path_from_entry():
    global current_path

    if not sftp:
        return

    path = path_var.get().strip()

    if not path:
        path = "."

    try:
        sftp.stat(path)

        current_path = path

        refresh_files()

    except Exception as e:
        messagebox.showerror(
            "Path Error",
            str(e)
        )


# =========================
# FILE LIST
# =========================

list_frame = tk.Frame(
    root,
    padx=10,
    pady=10
)

list_frame.pack(
    fill="both",
    expand=True
)

columns = (
    "name",
    "type",
    "size"
)

tree = ttk.Treeview(
    list_frame,
    columns=columns,
    show="headings",
    selectmode="browse"
)

tree.heading(
    "name",
    text="Name"
)

tree.heading(
    "type",
    text="Type"
)

tree.heading(
    "size",
    text="Size"
)

tree.column(
    "name",
    width=500
)

tree.column(
    "type",
    width=100
)

tree.column(
    "size",
    width=120
)

scrollbar = ttk.Scrollbar(
    list_frame,
    orient="vertical",
    command=tree.yview
)

tree.configure(
    yscrollcommand=scrollbar.set
)

tree.pack(
    side="left",
    fill="both",
    expand=True
)

scrollbar.pack(
    side="right",
    fill="y"
)

tree.bind(
    "<Double-1>",
    open_selected
)


# =========================
# BUTTON BAR
# =========================

button_frame = tk.Frame(
    root,
    pady=8
)

button_frame.pack(
    fill="x"
)

back_button = tk.Button(
    button_frame,
    text="← Back",
    width=12,
    command=go_back
)

back_button.pack(
    side="left",
    padx=5
)


refresh_button = tk.Button(
    button_frame,
    text="⟳ Refresh",
    width=12,
    command=refresh_files
)

refresh_button.pack(
    side="left",
    padx=5
)


download_button = tk.Button(
    button_frame,
    text="⬇ Download",
    width=16,
    font=("Arial", 10, "bold"),
    command=download_file
)

download_button.pack(
    side="left",
    padx=5
)


# =========================
# PROGRESS
# =========================

progress_frame = tk.Frame(
    root,
    padx=10,
    pady=5
)

progress_frame.pack(
    fill="x"
)

progress_var = tk.DoubleVar(
    value=0
)

progress_bar = ttk.Progressbar(
    progress_frame,
    variable=progress_var,
    maximum=100
)

progress_bar.pack(
    side="left",
    fill="x",
    expand=True
)


percent_label = tk.Label(
    progress_frame,
    text="0%",
    width=7,
    font=("Arial", 10, "bold")
)

percent_label.pack(
    side="left"
)


speed_label = tk.Label(
    root,
    text="Ready",
    font=("Arial", 9)
)

speed_label.pack(
    pady=(0, 8)
)


oled_idle()

root.mainloop()
