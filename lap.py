#!/usr/bin/env python3

import os
import subprocess
import shutil
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

LAPTOP_IP = "172.18.57.102"
LAPTOP_USER = "NEW SMART PC"

MOUNT_ROOT = "/tmp/lap_mount"
PI_ROOT = "/home/pi"

class LaptopFileManager:
    def __init__(self, root):
        self.root = root
        self.root.title("DH Laptop File Manager")
        self.root.geometry("900x600")

        self.current_path = None
        self.mounts = {}

        os.makedirs(MOUNT_ROOT, exist_ok=True)

        self.build_ui()
        self.load_shares()

    def build_ui(self):
        top = tk.Frame(self.root)
        top.pack(fill="x", padx=8, pady=8)

        tk.Label(
            top,
            text=f"Laptop: {LAPTOP_IP}",
            font=("Arial", 12, "bold")
        ).pack(side="left")

        tk.Button(
            top,
            text="Refresh",
            command=self.load_shares
        ).pack(side="right", padx=5)

        tk.Button(
            top,
            text="Back",
            command=self.go_back
        ).pack(side="right", padx=5)

        self.path_label = tk.Label(
            self.root,
            text="Shares",
            anchor="w"
        )
        self.path_label.pack(fill="x", padx=10)

        frame = tk.Frame(self.root)
        frame.pack(fill="both", expand=True, padx=8, pady=5)

        self.tree = ttk.Treeview(
            frame,
            columns=("type", "size"),
            show="tree headings"
        )

        self.tree.heading("#0", text="Name")
        self.tree.heading("type", text="Type")
        self.tree.heading("size", text="Size")

        self.tree.column("#0", width=550)
        self.tree.column("type", width=120)
        self.tree.column("size", width=150)

        scroll = ttk.Scrollbar(
            frame,
            orient="vertical",
            command=self.tree.yview
        )

        self.tree.configure(yscrollcommand=scroll.set)

        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self.tree.bind("<Double-1>", self.double_click)

        bottom = tk.Frame(self.root)
        bottom.pack(fill="x", padx=8, pady=8)

        tk.Button(
            bottom,
            text="Download",
            width=15,
            command=self.download_selected
        ).pack(side="left", padx=5)

        tk.Button(
            bottom,
            text="Open",
            width=15,
            command=self.open_selected
        ).pack(side="left", padx=5)

        tk.Button(
            bottom,
            text="Refresh",
            width=15,
            command=self.refresh
        ).pack(side="left", padx=5)

        self.status = tk.Label(
            self.root,
            text="Ready",
            anchor="w"
        )
        self.status.pack(fill="x", padx=10, pady=(0, 8))

    def clear_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

    def load_shares(self):
        self.clear_tree()
        self.current_path = None
        self.path_label.config(text="Laptop Shares")
        self.status.config(text="Connecting...")

        try:
            cmd = [
                "smbclient",
                "-L",
                f"//{LAPTOP_IP}",
                "-U",
                LAPTOP_USER
            ]

            result = subprocess.run(
                cmd,
                input="\n",
                text=True,
                capture_output=True
            )

            output = result.stdout

            shares = []

            for line in output.splitlines():
                parts = line.split()

                if len(parts) >= 2:
                    name = parts[0]
                    typ = parts[1]

                    if typ == "Disk":
                        if not name.endswith("$"):
                            shares.append(name)

                        elif name in ("C$", "E$", "D$", "F$", "G$"):
                            shares.append(name)

            if not shares:
                self.status.config(
                    text="No shares found. Check SMB/password."
                )
                return

            for share in sorted(set(shares)):
                self.tree.insert(
                    "",
                    "end",
                    text=share,
                    values=("Drive/Folder", "")
                )

            self.status.config(
                text=f"{len(set(shares))} shares found"
            )

        except Exception as e:
            messagebox.showerror("Error", str(e))

    def get_selected(self):
        selection = self.tree.selection()

        if not selection:
            return None

        item = selection[0]
        name = self.tree.item(item, "text")

        return name

    def mount_share(self, share):
        if share in self.mounts:
            return self.mounts[share]

        mount_point = os.path.join(
            MOUNT_ROOT,
            share.replace("$", "_")
        )

        os.makedirs(mount_point, exist_ok=True)

        if os.path.ismount(mount_point):
            self.mounts[share] = mount_point
            return mount_point

        cmd = [
            "sudo",
            "mount",
            "-t",
            "cifs",
            f"//{LAPTOP_IP}/{share}",
            mount_point,
            "-o",
            f'username={LAPTOP_USER},vers=3.0'
        ]

        result = subprocess.run(
            cmd,
            text=True,
            capture_output=True
        )

        if result.returncode != 0:
            messagebox.showerror(
                "Mount Error",
                result.stderr
            )
            return None

        self.mounts[share] = mount_point

        return mount_point

    def show_directory(self, path):
        self.clear_tree()
        self.current_path = path

        self.path_label.config(
            text=path
        )

        try:
            entries = list(Path(path).iterdir())

            dirs = sorted(
                [x for x in entries if x.is_dir()],
                key=lambda x: x.name.lower()
            )

            files = sorted(
                [x for x in entries if x.is_file()],
                key=lambda x: x.name.lower()
            )

            for entry in dirs:
                self.tree.insert(
                    "",
                    "end",
                    text=entry.name,
                    values=("Folder", "")
                )

            for entry in files:
                try:
                    size = entry.stat().st_size
                    size_text = self.format_size(size)
                except:
                    size_text = ""

                self.tree.insert(
                    "",
                    "end",
                    text=entry.name,
                    values=("File", size_text)
                )

            self.status.config(
                text=f"{len(entries)} items"
            )

        except PermissionError:
            messagebox.showerror(
                "Permission",
                "Permission denied."
            )

        except Exception as e:
            messagebox.showerror(
                "Error",
                str(e)
            )

    def double_click(self, event):
        item = self.tree.selection()

        if not item:
            return

        name = self.tree.item(
            item[0],
            "text"
        )

        typ = self.tree.item(
            item[0],
            "values"
        )[0]

        if self.current_path is None:
            mount = self.mount_share(name)

            if mount:
                self.show_directory(mount)

            return

        if typ == "Folder":
            new_path = os.path.join(
                self.current_path,
                name
            )

            self.show_directory(new_path)

        elif typ == "File":
            self.download_selected()

    def go_back(self):
        if self.current_path is None:
            return

        parent = os.path.dirname(
            self.current_path.rstrip("/")
        )

        mount_root = os.path.dirname(
            self.current_path
        )

        if parent == MOUNT_ROOT:
            self.load_shares()
        else:
            self.show_directory(parent)

    def open_selected(self):
        item = self.tree.selection()

        if not item or self.current_path is None:
            return

        name = self.tree.item(
            item[0],
            "text"
        )

        path = os.path.join(
            self.current_path,
            name
        )

        if os.path.isdir(path):
            self.show_directory(path)

        elif os.path.isfile(path):
            subprocess.Popen(
                ["xdg-open", path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

    def download_selected(self):
        item = self.tree.selection()

        if not item or self.current_path is None:
            messagebox.showwarning(
                "Select File",
                "Select a file first."
            )
            return

        name = self.tree.item(
            item[0],
            "text"
        )

        typ = self.tree.item(
            item[0],
            "values"
        )[0]

        if typ != "File":
            messagebox.showwarning(
                "Select File",
                "Please select a file."
            )
            return

        source = os.path.join(
            self.current_path,
            name
        )

        self.destination_window(source, name)

    def destination_window(self, source, filename):
        win = tk.Toplevel(self.root)
        win.title("Download Destination")
        win.geometry("600x450")
        win.transient(self.root)
        win.grab_set()

        tk.Label(
            win,
            text="Select Raspberry Pi destination",
            font=("Arial", 12, "bold")
        ).pack(pady=10)

        tree = ttk.Treeview(
            win,
            columns=("path",),
            show="tree"
        )

        tree.pack(
            fill="both",
            expand=True,
            padx=10,
            pady=5
        )

        root_item = tree.insert(
            "",
            "end",
            text="/home/pi",
            values=("/home/pi",)
        )

        def add_dirs(parent, path):
            try:
                dirs = sorted(
                    [
                        x for x in Path(path).iterdir()
                        if x.is_dir()
                        and not x.name.startswith(".")
                    ],
                    key=lambda x: x.name.lower()
                )

                for d in dirs:
                    child = tree.insert(
                        parent,
                        "end",
                        text=d.name,
                        values=(str(d),)
                    )

                    add_dirs(
                        child,
                        str(d)
                    )

            except:
                pass

        add_dirs(
            root_item,
            PI_ROOT
        )

        tree.item(
            root_item,
            open=True
        )

        button_frame = tk.Frame(win)
        button_frame.pack(
            fill="x",
            padx=10,
            pady=10
        )

        progress = ttk.Progressbar(
            win,
            mode="determinate"
        )
        progress.pack(
            fill="x",
            padx=10,
            pady=5
        )

        status = tk.Label(
            win,
            text="Ready"
        )
        status.pack(
            pady=5
        )

        def do_download():
            selected = tree.selection()

            if not selected:
                messagebox.showwarning(
                    "Destination",
                    "Select a destination folder."
                )
                return

            destination = tree.item(
                selected[0],
                "values"
            )[0]

            target = os.path.join(
                destination,
                filename
            )

            if os.path.exists(target):
                answer = messagebox.askyesno(
                    "File Exists",
                    f"{filename} already exists.\nReplace it?"
                )

                if not answer:
                    return

            try:
                total = os.path.getsize(source)

                progress["value"] = 0
                progress["maximum"] = total

                copied = 0
                chunk = 1024 * 1024

                with open(
                    source,
                    "rb"
                ) as src, open(
                    target,
                    "wb"
                ) as dst:

                    while True:
                        data = src.read(chunk)

                        if not data:
                            break

                        dst.write(data)

                        copied += len(data)

                        progress["value"] = copied

                        percent = (
                            copied / total * 100
                            if total
                            else 100
                        )

                        status.config(
                            text=f"Downloading... {percent:.1f}%"
                        )

                        win.update_idletasks()

                status.config(
                    text="Download completed"
                )

                messagebox.showinfo(
                    "Completed",
                    f"Downloaded successfully:\n\n{target}"
                )

                win.destroy()

            except Exception as e:
                messagebox.showerror(
                    "Download Error",
                    str(e)
                )

        tk.Button(
            button_frame,
            text="CANCEL",
            width=12,
            command=win.destroy
        ).pack(
            side="right",
            padx=5
        )

        tk.Button(
            button_frame,
            text="OK - DOWNLOAD",
            width=18,
            command=do_download
        ).pack(
            side="right",
            padx=5
        )

    def refresh(self):
        if self.current_path:
            self.show_directory(
                self.current_path
            )
        else:
            self.load_shares()

    @staticmethod
    def format_size(size):
        units = [
            "B",
            "KB",
            "MB",
            "GB",
            "TB"
        ]

        value = float(size)

        for unit in units:
            if value < 1024:
                return f"{value:.1f} {unit}"

            value /= 1024

        return f"{value:.1f} PB"


def main():
    root = tk.Tk()

    app = LaptopFileManager(root)

    root.mainloop()


if __name__ == "__main__":
    main()
