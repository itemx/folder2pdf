#!/usr/bin/env python3
"""
folder2pdf.py  ->  packaged as Folder2PDF.exe (PyInstaller --onefile --noconsole)

Borderless (page size = image pixel size), lossless-where-possible, single PDF.
Filename natural sort. Three invocation modes:

  Folder2PDF.exe "C:\path\folder"      # folder verb  (%1)  -> whole folder
  Folder2PDF.exe "C:\path"             # background   (%V)  -> current folder
  Folder2PDF.exe "C:\path\img_001.jpg" # per-file     (%1)  -> aggregation mode

In per-file mode Windows spawns one process per selected file. Processes
coordinate via a named mutex + shared list + quiet-period leader election so
exactly ONE combined PDF is produced.
"""

import sys
import os
import re
import io
import time
import ctypes

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp", ".gif"}

MB_ICONINFO = 0x40
MB_ICONERROR = 0x10

QUIET_MS = 900          # inactivity window before a leader claims the batch
POLL_MS = 150
MUTEX_WAIT_MS = 5000

_k32 = ctypes.windll.kernel32
_u32 = ctypes.windll.user32


def _detect_lang():
    try:
        prim = _k32.GetUserDefaultUILanguage() & 0x3FF  # PRIMARYLANGID
    except Exception:
        return "en"
    return {0x04: "zh", 0x11: "ja"}.get(prim, "en")  # Chinese / Japanese else English


STRINGS = {
    "en": {
        "no_images": "No images found.",
        "missing_dnd": "tkinterdnd2 missing in the packaged exe.",
        "not_folder": "Not a folder:\n{path}",
        "failed": "Failed:\n{err}",
        "register_failed": "Register failed:\n{err}",
        "menu_installed": "Right-click menu installed.\n{exe}\n\n"
                          "Windows 11: 'Show more options' / Shift+right-click.",
        "menu_removed": "Right-click menu removed. Files left untouched.",
        "merging": "Merging {n} image(s) to PDF…",
        "cancelling": "Cancelling…",
        "cancel_btn": "Cancel",
        "drop_here": "Drag image files or folders here\n\nor use the buttons below",
        "drop_none": "No images found — try again\n\nDrag image files or folders here",
        "save_as_title": "Save PDF as",
        "choose_images_title": "Choose images",
        "images_label": "Images",
        "add_images_btn": "Add images…",
        "register_btn": "Register right-click menu",
        "unregister_btn": "Remove right-click menu",
    },
    "ja": {
        "no_images": "画像が見つかりません。",
        "missing_dnd": "パッケージ内に tkinterdnd2 がありません。",
        "not_folder": "フォルダーではありません:\n{path}",
        "failed": "失敗しました:\n{err}",
        "register_failed": "登録に失敗しました:\n{err}",
        "menu_installed": "右クリックメニューを登録しました。\n{exe}\n\n"
                          "Windows 11:「その他のオプションを表示」/ Shift+右クリック。",
        "menu_removed": "右クリックメニューを削除しました。ファイルは変更していません。",
        "merging": "{n} 個の画像を PDF に結合しています…",
        "cancelling": "キャンセルしています…",
        "cancel_btn": "キャンセル",
        "drop_here": "画像ファイルまたはフォルダーをここにドラッグ\n\nまたは下のボタンを使用",
        "drop_none": "画像が見つかりません — もう一度お試しください\n\n"
                     "画像ファイルまたはフォルダーをここにドラッグ",
        "save_as_title": "PDF を保存",
        "choose_images_title": "画像を選択",
        "images_label": "画像",
        "add_images_btn": "画像を追加…",
        "register_btn": "右クリックメニューを登録",
        "unregister_btn": "右クリックメニューを削除",
    },
    "zh": {
        "no_images": "找不到圖片。",
        "missing_dnd": "打包的 exe 缺少 tkinterdnd2。",
        "not_folder": "不是資料夾:\n{path}",
        "failed": "失敗:\n{err}",
        "register_failed": "註冊失敗:\n{err}",
        "menu_installed": "右鍵選單已註冊。\n{exe}\n\n"
                          "Windows 11:「顯示更多選項」/ Shift+右鍵。",
        "menu_removed": "右鍵選單已移除。未刪除任何檔案。",
        "merging": "正在將 {n} 張圖片合併為 PDF…",
        "cancelling": "取消中…",
        "cancel_btn": "取消",
        "drop_here": "把圖片檔或資料夾拖到這裡\n\n或用下方按鈕選擇",
        "drop_none": "找不到圖片，再試一次\n\n把圖片檔或資料夾拖到這裡",
        "save_as_title": "儲存 PDF 為",
        "choose_images_title": "選擇圖片",
        "images_label": "圖片",
        "add_images_btn": "加入圖片…",
        "register_btn": "註冊右鍵選單",
        "unregister_btn": "移除右鍵選單",
    },
}

LANG = _detect_lang()


def t(key, **kw):
    s = STRINGS.get(LANG, STRINGS["en"]).get(key, STRINGS["en"][key])
    return s.format(**kw) if kw else s


def notify(title, msg, error=False):
    try:
        _u32.MessageBoxW(0, msg, title, MB_ICONERROR if error else MB_ICONINFO)
    except Exception:
        pass


def natural_key(name):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


def is_image(path):
    return os.path.splitext(path)[1].lower() in IMAGE_EXTS


def collect_folder(folder):
    out = []
    for e in os.listdir(folder):
        full = os.path.join(folder, e)
        if os.path.isfile(full) and is_image(full):
            out.append(full)
    out.sort(key=lambda p: natural_key(os.path.basename(p)))
    return out


def collect_dropped(paths):
    """Flatten dropped files + folders into one natural-sorted, deduped image
    list. A dropped folder expands to the images inside it."""
    imgs = []
    for p in paths:
        p = os.path.abspath(p)
        if os.path.isdir(p):
            imgs.extend(collect_folder(p))
        elif os.path.isfile(p) and is_image(p):
            imgs.append(p)
    seen, uniq = set(), []
    for p in imgs:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    uniq.sort(key=lambda x: natural_key(os.path.basename(x)))
    return uniq


def unique_output(parent, base):
    p = os.path.join(parent, base + ".pdf")
    i = 1
    while os.path.exists(p):
        p = os.path.join(parent, f"{base}_{i}.pdf")
        i += 1
    return p


def prepare_payload(path):
    """
    Return element for img2pdf: raw path (lossless, no re-encode) for images with
    no alpha; flattened in-memory PNG bytes for alpha/transparent images
    (img2pdf rejects alpha). Mode is read lazily by Pillow (cheap, no full decode).
    """
    from PIL import Image
    with Image.open(path) as im:
        animated = getattr(im, "n_frames", 1) > 1  # img2pdf rejects multi-frame
        needs_flatten = im.mode in ("RGBA", "LA", "PA") or (
            im.mode == "P" and "transparency" in im.info
        )
        if not needs_flatten and not animated:
            return path
        im.seek(0)  # ponytail: first frame only; animated GIF -> single page
        bg = Image.new("RGB", im.size, (255, 255, 255))
        rgba = im.convert("RGBA")
        bg.paste(rgba, mask=rgba.split()[-1])
        buf = io.BytesIO()
        bg.save(buf, format="PNG")   # lossless
        return buf.getvalue()


def build_pdf_with_progress(image_paths, out_path):
    """One page per image (img2pdf) merged with pikepdf, behind a tkinter
    progress dialog with Cancel. Per-image assembly instead of a single
    img2pdf.convert is what makes a real progress bar and mid-run cancel
    possible. Returns (status, err); status in {"done","cancelled","error"}.
    ponytail: holds every source page in memory until save — fine for the
    hundreds-of-images ceiling; stream to a temp file if that ever bites."""
    import threading, queue, tkinter as tk
    from tkinter import ttk
    import img2pdf, pikepdf

    cancel = threading.Event()
    q = queue.Queue()
    n = len(image_paths)

    def worker():
        try:
            out = pikepdf.Pdf.new()
            sources = []  # keep each 1-page Pdf alive until save()
            for i, p in enumerate(image_paths):
                if cancel.is_set():
                    q.put(("cancelled", None)); return
                src = pikepdf.open(io.BytesIO(img2pdf.convert(prepare_payload(p))))
                sources.append(src)
                out.pages.extend(src.pages)
                q.put(("progress", i + 1))
            if cancel.is_set():
                q.put(("cancelled", None)); return
            out.save(out_path)
            q.put(("done", None))
        except Exception as e:
            q.put(("error", str(e)))

    root = tk.Tk()
    root.title("Folder to PDF")
    root.resizable(False, False)
    root.attributes("-topmost", True)
    frm = ttk.Frame(root, padding=16)
    frm.grid()
    label = ttk.Label(frm, text=t("merging", n=n))
    label.grid(sticky="w")
    bar = ttk.Progressbar(frm, length=340, maximum=n, mode="determinate")
    bar.grid(pady=8)
    count = ttk.Label(frm, text=f"0 / {n}")
    count.grid(sticky="w")
    result = {"status": "cancelled", "err": None}

    def do_cancel():
        cancel.set()
        btn.configure(state="disabled")
        label.configure(text=t("cancelling"))
    btn = ttk.Button(frm, text=t("cancel_btn"), command=do_cancel)
    btn.grid(pady=(8, 0))
    root.protocol("WM_DELETE_WINDOW", do_cancel)  # window X = cancel, no partial file

    def poll():
        try:
            while True:
                kind, val = q.get_nowait()
                if kind == "progress":
                    bar["value"] = val
                    count.configure(text=f"{val} / {n}")
                else:
                    result["status"], result["err"] = kind, val
                    root.destroy()
                    return
        except queue.Empty:
            pass
        root.after(80, poll)

    threading.Thread(target=worker, daemon=True).start()
    root.after(80, poll)
    root.mainloop()
    return result["status"], result["err"]


def render(image_paths, out_dir, base):
    if not image_paths:
        notify("Folder to PDF", t("no_images"), error=True)
        return 1
    out = unique_output(out_dir, base or "merged")
    status, err = build_pdf_with_progress(image_paths, out)
    if status == "error":
        notify("Folder to PDF", t("failed", err=err), error=True)
        return 4
    return 0  # done or cancelled: dialog was the feedback; no file left on cancel


# ---------- folder / background mode ----------

def run_folder(folder):
    folder = os.path.abspath(folder)
    if not os.path.isdir(folder):
        notify("Folder to PDF", t("not_folder", path=folder), error=True)
        return 2
    imgs = collect_folder(folder)
    return render(imgs, os.path.dirname(folder), os.path.basename(folder) or "merged")


# ---------- per-file aggregation mode ----------

def _appdir():
    d = os.path.join(os.environ.get("LOCALAPPDATA", os.environ.get("TEMP", ".")),
                     "Folder2PDF")
    os.makedirs(d, exist_ok=True)
    return d


class _Mutex:
    def __init__(self, name):
        self.h = _k32.CreateMutexW(None, False, name)

    def __enter__(self):
        _k32.WaitForSingleObject(self.h, MUTEX_WAIT_MS)  # 0=signaled, 0x80=abandoned
        return self

    def __exit__(self, *a):
        _k32.ReleaseMutex(self.h)
        _k32.CloseHandle(self.h)


def run_file(file_path):
    file_path = os.path.abspath(file_path)
    if not (os.path.isfile(file_path) and is_image(file_path)):
        return 0  # silently ignore non-image invocation

    d = _appdir()
    acc = os.path.join(d, "pending.lst")

    with _Mutex("Global\\Folder2PDF_acc"):
        # ponytail: drop a stale batch left by a crashed/cancelled run before
        # appending, else its old images silently merge into this PDF. QUIET_MS
        # is 900ms; >60s of no appends is unambiguously a dead batch.
        if os.path.exists(acc) and (time.time() - os.path.getmtime(acc)) > 60:
            try:
                os.remove(acc)
            except OSError:
                pass
        with open(acc, "a", encoding="utf-8") as f:
            f.write(file_path + "\n")

    # quiet-period leader election.
    # ponytail: 900ms quiet window is the ceiling — a process Windows spawns
    # >900ms after the leader claims emits its own second PDF. Fine for normal
    # selections; right-click the folder for hundreds. Upgrade: batch session token.
    while True:
        time.sleep(POLL_MS / 1000.0)
        try:
            mtime = os.path.getmtime(acc)
        except FileNotFoundError:
            return 0  # another process already claimed + processed
        if (time.time() - mtime) * 1000.0 < QUIET_MS:
            continue  # still receiving appends
        claim = os.path.join(d, f"batch_{os.getpid()}_{int(time.time()*1000)}.lst")
        try:
            os.replace(acc, claim)  # atomic; only one process wins
        except (FileNotFoundError, PermissionError, OSError):
            return 0  # not leader (already claimed) or transient lock
        # leader: read, dedupe, natural sort
        with open(claim, "r", encoding="utf-8") as f:
            paths = [ln.strip() for ln in f if ln.strip()]
        try:
            os.remove(claim)
        except OSError:
            pass
        seen, uniq = set(), []
        for p in paths:
            if p not in seen and os.path.isfile(p):
                seen.add(p)
                uniq.append(p)
        uniq.sort(key=lambda p: natural_key(os.path.basename(p)))
        out_dir = os.path.dirname(uniq[0]) if uniq else d
        base = os.path.basename(out_dir) or "merged"
        return render(uniq, out_dir, base)


# ---------- bare launch: drag-and-drop window ----------

def run_drop_window():
    """No args: show a window to drop image files/folders onto, ask where to
    save, then merge. Explorer drag-drop needs tkinterdnd2 (plain tk can't)."""
    import tkinter as tk
    from tkinter import ttk, filedialog
    try:
        from tkinterdnd2 import TkinterDnD, DND_FILES
    except ImportError:
        notify("Folder to PDF", t("missing_dnd"), error=True)
        return 3

    picked = {"imgs": None, "out": None}
    root = TkinterDnD.Tk()
    root.title("Folder to PDF")
    root.geometry("440x300")
    root.attributes("-topmost", True)
    zone = tk.Label(root, text=t("drop_here"), relief="ridge", borderwidth=2)
    zone.pack(fill="both", expand=True, padx=16, pady=(16, 8))

    def choose_and_go(imgs):
        if not imgs:
            zone.configure(text=t("drop_none"))
            return
        d = os.path.dirname(imgs[0])
        out = filedialog.asksaveasfilename(
            parent=root, title=t("save_as_title"), initialdir=d,
            initialfile=(os.path.basename(d) or "merged") + ".pdf",
            defaultextension=".pdf", filetypes=[("PDF", "*.pdf")])
        if not out:
            return  # cancelled the save dialog -> stay, allow another drop
        picked["imgs"], picked["out"] = imgs, out
        root.destroy()  # leave mainloop; progress dialog runs next

    # register the drop target on zone too: it fills the window, so the pointer
    # is over zone (not root) on drop. Registering only root => no-drop cursor.
    def on_drop(e):
        choose_and_go(collect_dropped(root.tk.splitlist(e.data)))
    for w in (root, zone):
        w.drop_target_register(DND_FILES)
        w.dnd_bind("<<Drop>>", on_drop)

    def browse():
        pats = " ".join("*" + e for e in sorted(IMAGE_EXTS))
        files = filedialog.askopenfilenames(
            parent=root, title=t("choose_images_title"),
            filetypes=[(t("images_label"), pats)])
        if files:
            choose_and_go(collect_dropped(files))
    ttk.Button(root, text=t("add_images_btn"), command=browse).pack(pady=(0, 4))
    reg = ttk.Frame(root)
    reg.pack(pady=(0, 12))
    ttk.Button(reg, text=t("register_btn"), command=register).pack(side="left", padx=4)
    ttk.Button(reg, text=t("unregister_btn"), command=unregister).pack(side="left", padx=4)

    root.mainloop()

    if not picked["imgs"]:
        return 0  # window closed without choosing
    status, err = build_pdf_with_progress(picked["imgs"], picked["out"])
    if status == "error":
        notify("Folder to PDF", t("failed", err=err), error=True)
        return 4
    return 0


# ---------- self register / unregister of the right-click menu (HKCU) ----------

VERB = "Folder2PDF"
LABEL = "Merge to PDF (Folder2PDF)"


def _exe_path():
    # frozen: the exe itself; dev run: this script
    return sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__)


def _refresh_shell():
    try:
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)  # SHCNE_ASSOCCHANGED
    except Exception:
        pass


def _verb_bases():
    """(registry base under HKCU, arg token) for every place the verb lives."""
    bases = [("Software\\Classes\\Directory", "%1"),               # a folder
             ("Software\\Classes\\Directory\\Background", "%V")]    # folder background
    for e in sorted(IMAGE_EXTS):                                    # selected image files
        bases.append((f"Software\\Classes\\SystemFileAssociations\\{e}", "%1"))
    return bases


def register():
    import winreg
    exe = _exe_path()
    try:
        for base, tok in _verb_bases():
            shell = f"{base}\\shell\\{VERB}"
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, shell) as k:
                winreg.SetValueEx(k, None, 0, winreg.REG_SZ, LABEL)
                winreg.SetValueEx(k, "Icon", 0, winreg.REG_SZ, f'"{exe}",0')
                # Document: show on multi-select, invoke once per file (see run_file)
                winreg.SetValueEx(k, "MultiSelectModel", 0, winreg.REG_SZ, "Document")
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, shell + "\\command") as k:
                winreg.SetValueEx(k, None, 0, winreg.REG_SZ, f'"{exe}" "{tok}"')
    except OSError as e:
        notify("Folder to PDF", t("register_failed", err=e), error=True)
        return 4
    _refresh_shell()
    notify("Folder to PDF", t("menu_installed", exe=exe))
    return 0


def unregister():
    import winreg
    for base, _ in _verb_bases():
        shell = f"{base}\\shell\\{VERB}"
        for sub in (shell + "\\command", shell):  # child first: DeleteKey needs empty key
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, sub)
            except FileNotFoundError:
                pass
    _refresh_shell()
    notify("Folder to PDF", t("menu_removed"))
    return 0


def main():
    args = sys.argv[1:]
    if args and args[0].lower().lstrip("-/") == "register":
        return register()
    if args and args[0].lower().lstrip("-/") == "unregister":
        return unregister()
    if not args:
        return run_drop_window()
    target = os.path.abspath(args[0].strip().rstrip('"'))
    if os.path.isdir(target):
        return run_folder(target)
    return run_file(target)


if __name__ == "__main__":
    sys.exit(main())
