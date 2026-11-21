"""
UniversalPortableMaker - turns (almost) any Windows program into a portable version.

Accepted sources:
  - .exe, .bat/.cmd, .ps1, .py/.pyw, .jar, .js (Node), .vbs
  - a whole FOLDER (you pick which file inside it is the main program)
  - archives: .zip, .tar/.gz/.tgz/.bz2/.xz (built in); .7z/.rar/.iso (via 7-Zip)
  - .msi (extracted without installing, via 'msiexec /a')
  - NSIS-style .exe installers (by ticking the option, via 7-Zip)

The result is a launcher .exe (or folder) that carries the program inside it.
When opened, it creates <Name>_Data next to itself and redirects AppData,
Documents, Temp, etc. there. Everything stays on the USB drive.

Requirements to GENERATE: Windows + Python 3.9+ (PyInstaller is installed automatically).
The generated launcher runs on any Windows PC without Python.
Run this as a .py script (do not compile the generator itself).
"""
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import uuid
import zipfile
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

KINDS = {
    ".exe": "exe", ".bat": "bat", ".cmd": "bat", ".ps1": "ps1",
    ".py": "py", ".pyw": "py", ".jar": "jar", ".js": "node", ".vbs": "vbs",
}
CONSOLE_DEFAULT = {"bat", "ps1", "py", "node"}
TAR_EXT = (".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tar.xz")
SEVENZ_EXT = (".7z", ".rar", ".iso", ".cab", ".wim")

# ---------------------------------------------------------------------------
# Generated launcher code. __CONFIG__ is replaced at generation time.
# ---------------------------------------------------------------------------
STUB = r'''
import os, sys, shutil, subprocess, ctypes

CFG = __CONFIG__


def fail(msg):
    try:
        ctypes.windll.user32.MessageBoxW(0, msg, CFG["name"], 0x10)
    except Exception:
        print(msg)
    sys.exit(1)


def find_runtime(app, name):
    bundled = {
        "python": ["python/python.exe", "Python/python.exe", "runtime/python.exe", "python.exe"],
        "java": ["jre/bin/java.exe", "jdk/bin/java.exe", "java/bin/java.exe", "runtime/bin/java.exe"],
        "node": ["node/node.exe", "node.exe"],
    }[name]
    for c in bundled:
        p = os.path.join(app, *c.split("/"))
        if os.path.isfile(p):
            return p
    for cmd in {"python": ["python", "py"], "java": ["java"], "node": ["node"]}[name]:
        p = shutil.which(cmd)
        if p:
            return p
    fail(
        "This program needs '%s', which was not found.\n\n"
        "Install it on this PC, or place its portable version inside the program "
        "folder before generating the launcher." % name
    )


def build_cmd(kind, entry, app):
    args = CFG["args"]
    if kind == "exe":
        cmd = [entry]
    elif kind == "bat":
        cmd = ["cmd", "/c", entry]
    elif kind == "ps1":
        cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", entry]
    elif kind == "py":
        py = find_runtime(app, "python")
        if entry.lower().endswith(".pyw"):
            pw = os.path.join(os.path.dirname(py), "pythonw.exe")
            if os.path.isfile(pw):
                py = pw
        cmd = [py, entry]
    elif kind == "jar":
        cmd = [find_runtime(app, "java"), "-jar", entry]
    elif kind == "node":
        cmd = [find_runtime(app, "node"), entry]
    elif kind == "vbs":
        cmd = ["wscript", entry]
    else:
        fail("Unknown type: " + kind)
    return cmd + args


def main():
    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    root = os.path.join(exe_dir, CFG["name"] + "_Data")
    data = os.path.join(root, "Data")
    prof = os.path.join(data, "Profile")
    temp = os.path.join(data, "Temp")

    for sub in (
        os.path.join(prof, "AppData", "Roaming"),
        os.path.join(prof, "AppData", "Local"),
        os.path.join(prof, "Documents"),
        os.path.join(prof, "Desktop"),
        os.path.join(prof, "Downloads"),
        temp,
        os.path.join(data, "ProgramData"),
    ):
        os.makedirs(sub, exist_ok=True)

    payload = os.path.join(sys._MEIPASS, "payload")
    if CFG["onefile"]:
        # extract once to the USB drive (re-copy if the launcher was regenerated)
        app = os.path.join(root, "App")
        marker = os.path.join(app, ".ready")
        current = ""
        if os.path.isfile(marker):
            with open(marker) as f:
                current = f.read().strip()
        if current != CFG["build_id"]:
            shutil.copytree(payload, app, dirs_exist_ok=True)
            with open(marker, "w") as f:
                f.write(CFG["build_id"])
    else:
        app = payload  # folder mode: already on the USB drive

    entry = os.path.join(app, *CFG["entry"].split("/"))
    if not os.path.isfile(entry):
        fail("Main file not found:\n" + entry)

    env = os.environ.copy()
    env.update({
        "USERPROFILE": prof,
        "HOME": prof,
        "APPDATA": os.path.join(prof, "AppData", "Roaming"),
        "LOCALAPPDATA": os.path.join(prof, "AppData", "Local"),
        "TEMP": temp,
        "TMP": temp,
        "PROGRAMDATA": os.path.join(data, "ProgramData"),
        "HOMEDRIVE": prof[:2] if prof[1:2] == ":" else "",
        "HOMEPATH": prof[2:] if prof[1:2] == ":" else prof,
    })

    try:
        rc = subprocess.Popen(
            build_cmd(CFG["kind"], entry, app), cwd=os.path.dirname(entry), env=env
        ).wait()
    except OSError as e:
        if getattr(e, "winerror", None) == 740:
            fail("This program requires administrator privileges.\n"
                 "Run the launcher with 'Run as administrator'.")
        fail("Could not run the program:\n%s" % e)

    if CFG["clean_temp"]:
        for n in os.listdir(temp):
            p = os.path.join(temp, n)
            try:
                shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
            except Exception:
                pass
    sys.exit(rc)


if __name__ == "__main__":
    main()
'''


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def find_python():
    if not getattr(sys, "frozen", False):
        return sys.executable
    return shutil.which("python") or shutil.which("py")


def find_7z():
    for n in ("7z", "7za", "7zz"):
        p = shutil.which(n)
        if p:
            return p
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
        if base:
            p = os.path.join(base, "7-Zip", "7z.exe")
            if os.path.isfile(p):
                return p
    return None


def exe_is_console(path):
    """True if the .exe is a console application (reads the PE header)."""
    try:
        with open(path, "rb") as f:
            f.seek(0x3C)
            off = int.from_bytes(f.read(4), "little")
            f.seek(off)
            if f.read(4) != b"PE\0\0":
                return False
            f.seek(off + 24 + 68)
            return int.from_bytes(f.read(2), "little") == 3
    except Exception:
        return False


def safe_name(s):
    return re.sub(r"[^\w\-]+", "_", s).strip("_") or "App"


def safe_tar_extract(path, dest):
    dest_real = os.path.realpath(dest)
    with tarfile.open(path) as tf:
        members = []
        for m in tf.getmembers():
            target = os.path.realpath(os.path.join(dest, m.name))
            if not target.startswith(dest_real) or m.issym() or m.islnk():
                continue
            members.append(m)
        tf.extractall(dest, members=members)


def scan_entries(payload):
    found = []
    for dp, _dn, fn in os.walk(payload):
        for f in fn:
            ext = os.path.splitext(f)[1].lower()
            if ext in KINDS:
                rel = os.path.relpath(os.path.join(dp, f), payload).replace(os.sep, "/")
                found.append(rel)
            if len(found) > 500:
                break
    found.sort(key=lambda r: (not r.lower().endswith(".exe"), r.count("/"), r.lower()))
    return found


class Maker(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Universal Portable Maker")
        self.geometry("620x720")
        self.stage_dir = tempfile.mkdtemp(prefix="upm_stage_")
        self.payload = os.path.join(self.stage_dir, "payload")

        self.src = tk.StringVar()
        self.is_installer = tk.BooleanVar(value=False)
        self.entry = tk.StringVar()
        self.args = tk.StringVar()
        self.name = tk.StringVar()
        self.out_dir = tk.StringVar(value=os.path.dirname(os.path.abspath(__file__)))
        self.mode = tk.StringVar(value="onefile")
        self.console = tk.BooleanVar(value=False)
        self.clean_temp = tk.BooleanVar(value=False)

        # source
        f = tk.Frame(self)
        f.pack(fill="x", padx=10, pady=(10, 0))
        tk.Label(f, text="1) Source (file, folder, zip, msi...):", anchor="w").pack(fill="x")
        tk.Entry(f, textvariable=self.src, state="readonly").pack(side="left", fill="x", expand=True)
        tk.Button(f, text="File...", command=self.pick_file).pack(side="left", padx=(5, 0))
        tk.Button(f, text="Folder...", command=self.pick_dir).pack(side="left", padx=(5, 0))
        tk.Checkbutton(
            self, variable=self.is_installer,
            text="The source is an .exe installer (try extracting with 7-Zip)",
        ).pack(anchor="w", padx=10)

        # main program
        f = tk.Frame(self)
        f.pack(fill="x", padx=10, pady=(8, 0))
        tk.Label(f, text="2) Main program to run:", anchor="w").pack(fill="x")
        self.combo = ttk.Combobox(f, textvariable=self.entry, state="readonly")
        self.combo.pack(fill="x")
        self.combo.bind("<<ComboboxSelected>>", lambda e: self.auto_console())

        self._field("3) Arguments (optional):", self.args)
        self._field("4) App name:", self.name)

        f = tk.Frame(self)
        f.pack(fill="x", padx=10, pady=(8, 0))
        tk.Label(f, text="5) Save to (USB drive):", anchor="w").pack(fill="x")
        tk.Entry(f, textvariable=self.out_dir).pack(side="left", fill="x", expand=True)
        tk.Button(f, text="...", width=4, command=self.pick_out).pack(side="left", padx=(5, 0))

        tk.Radiobutton(self, variable=self.mode, value="onefile",
                       text="Single file (.exe) - briefly uses the PC's Temp when opening"
                       ).pack(anchor="w", padx=10, pady=(8, 0))
        tk.Radiobutton(self, variable=self.mode, value="onedir",
                       text="Folder (faster, does not use the PC's Temp)").pack(anchor="w", padx=10)
        tk.Checkbutton(self, variable=self.console,
                       text="Show console window (terminal apps)").pack(anchor="w", padx=10)
        tk.Checkbutton(self, variable=self.clean_temp,
                       text="Clean the USB Temp folder when the app closes").pack(anchor="w", padx=10)

        self.btn = tk.Button(self, text="Generate portable version", height=2,
                             command=self.start, state="disabled")
        self.btn.pack(fill="x", padx=10, pady=10)
        self.log = scrolledtext.ScrolledText(self, height=12, state="disabled", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # ----- ui helpers
    def _field(self, label, var):
        f = tk.Frame(self)
        f.pack(fill="x", padx=10, pady=(8, 0))
        tk.Label(f, text=label, anchor="w").pack(fill="x")
        tk.Entry(f, textvariable=var).pack(fill="x")

    def say(self, text):
        def w():
            self.log.config(state="normal")
            self.log.insert("end", text + "\n")
            self.log.see("end")
            self.log.config(state="disabled")
        self.after(0, w)

    def on_close(self):
        shutil.rmtree(self.stage_dir, ignore_errors=True)
        self.destroy()

    def pick_file(self):
        p = filedialog.askopenfilename(title="Choose the source file")
        if p:
            self.load_source(p)

    def pick_dir(self):
        p = filedialog.askdirectory(title="Choose the program folder")
        if p:
            self.load_source(p)

    def pick_out(self):
        p = filedialog.askdirectory()
        if p:
            self.out_dir.set(p)

    def auto_console(self):
        rel = self.entry.get()
        if not rel:
            return
        kind = KINDS.get(os.path.splitext(rel)[1].lower())
        if kind == "exe":
            self.console.set(exe_is_console(os.path.join(self.payload, *rel.split("/"))))
        else:
            self.console.set(kind in CONSOLE_DEFAULT)

    # ----- step 1: prepare the source
    def load_source(self, path):
        self.src.set(path)
        base = os.path.basename(path.rstrip("\\/"))
        stem = base
        for e in TAR_EXT:
            if base.lower().endswith(e):
                stem = base[: -len(e)]
                break
        else:
            if os.path.isfile(path):
                stem = os.path.splitext(base)[0]
        self.name.set(safe_name(stem))
        self.btn.config(state="disabled")
        self.combo.config(values=[])
        self.entry.set("")
        threading.Thread(target=self.stage, args=(path,), daemon=True).start()

    def run(self, cmd, cwd=None):
        p = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, errors="replace")
        for line in p.stdout:
            self.say(line.rstrip())
        return p.wait()

    def stage(self, src):
        try:
            self.say(f"Preparing: {src}")
            shutil.rmtree(self.payload, ignore_errors=True)
            os.makedirs(self.payload)
            low = src.lower()

            if os.path.isdir(src):
                shutil.copytree(src, self.payload, dirs_exist_ok=True)
            elif low.endswith(".zip"):
                with zipfile.ZipFile(src) as z:
                    z.extractall(self.payload)
            elif low.endswith(TAR_EXT):
                safe_tar_extract(src, self.payload)
            elif low.endswith(".msi"):
                cmdline = f'msiexec /a "{src}" /qn TARGETDIR="{self.payload}"'
                self.say("Extracting MSI without installing...")
                if self.run(cmdline) != 0:
                    raise RuntimeError("msiexec failed (requires Windows; try running as administrator).")
            elif low.endswith(SEVENZ_EXT) or (self.is_installer.get() and low.endswith(".exe")):
                z = find_7z()
                if not z:
                    raise RuntimeError("7-Zip not found. Install it from 7-zip.org to extract this type.")
                self.say("Extracting with 7-Zip...")
                if self.run([z, "x", "-y", f"-o{self.payload}", src]) != 0:
                    raise RuntimeError("7-Zip could not extract this file. Inno Setup installers "
                                       "need 'innoextract'.")
            else:
                shutil.copy2(src, self.payload)

            entries = scan_entries(self.payload)
            if not entries:
                raise RuntimeError("No runnable program found in the source.")
            self.after(0, lambda: self.staged(entries))
        except Exception as e:
            self.say(f"ERROR: {e}")
            self.after(0, lambda: messagebox.showerror("Error", str(e)))

    def staged(self, entries):
        self.combo.config(values=entries)
        self.entry.set(entries[0])
        self.auto_console()
        self.btn.config(state="normal")
        self.say(f"{len(entries)} program(s) found. Check item 2, then generate.")

    # ----- step 2: generate
    def start(self):
        if not self.entry.get():
            messagebox.showwarning("Warning", "Choose the main program.")
            return
        self.btn.config(state="disabled")
        threading.Thread(target=self.build, daemon=True).start()

    def build(self):
        work = tempfile.mkdtemp(prefix="upm_build_")
        try:
            py = find_python()
            if not py:
                raise RuntimeError("Python not found in PATH.")
            if self.run([py, "-m", "PyInstaller", "--version"]) != 0:
                self.say("Installing PyInstaller...")
                if self.run([py, "-m", "pip", "install", "pyinstaller"]) != 0:
                    raise RuntimeError("Failed to install PyInstaller.")

            rel = self.entry.get()
            kind = KINDS[os.path.splitext(rel)[1].lower()]
            name = safe_name(self.name.get())
            onefile = self.mode.get() == "onefile"
            cfg = {
                "name": name,
                "entry": rel,
                "kind": kind,
                "args": self.args.get().split() if self.args.get().strip() else [],
                "onefile": onefile,
                "clean_temp": self.clean_temp.get(),
                "build_id": uuid.uuid4().hex,
            }
            stub = os.path.join(work, "stub.py")
            with open(stub, "w", encoding="utf-8") as f:
                f.write(STUB.replace("__CONFIG__", repr(cfg)))

            out_name = f"{name}_Portable"
            self.say("Generating launcher (this may take a while)...")
            code = self.run([
                py, "-m", "PyInstaller",
                "--onefile" if onefile else "--onedir",
                "--console" if self.console.get() else "--noconsole",
                "--clean", "--name", out_name,
                "--add-data", f"{self.payload}{os.pathsep}payload",
                "--distpath", os.path.join(work, "dist"),
                "--workpath", os.path.join(work, "build"),
                "--specpath", work,
                stub,
            ], cwd=work)
            if code != 0:
                raise RuntimeError("PyInstaller failed. See the log above.")

            out = self.out_dir.get()
            os.makedirs(out, exist_ok=True)
            if onefile:
                final = os.path.join(out, out_name + ".exe")
                shutil.copy2(os.path.join(work, "dist", out_name + ".exe"), final)
            else:
                final = os.path.join(out, out_name)
                shutil.copytree(os.path.join(work, "dist", out_name), final, dirs_exist_ok=True)
                final = os.path.join(final, out_name + ".exe")
            self.say(f"\nDONE: {final}")
            self.after(0, lambda: messagebox.showinfo("Done", f"Generated:\n{final}"))
        except Exception as e:
            self.say(f"\nERROR: {e}")
            self.after(0, lambda: messagebox.showerror("Error", str(e)))
        finally:
            shutil.rmtree(work, ignore_errors=True)
            self.after(0, lambda: self.btn.config(state="normal"))


if __name__ == "__main__":
    Maker().mainloop()
