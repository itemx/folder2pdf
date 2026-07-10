Folder2PDF - borderless image folder -> single PDF, via Windows right-click
============================================================================

WHY CUSTOM
No off-the-shelf right-click tool does "folder -> single borderless PDF, natural
filename order, local, free". Existing tools either emit one PDF per image
(oneclickpdf, FileConverter #586) or force a paper size = white margins (ImBatch,
Print to PDF). img2pdf sets page size = image pixel size (zero margin) and embeds
JPEG losslessly. This wraps it.

FILES
  folder2pdf.py   core (packaged into the exe)
  build.ps1       build single portable exe (needs Python once, on build machine)
  The exe registers/unregisters its own right-click menu (HKCU, no admin) -
  no separate install script.

BUILD (once, on a machine with Python 3.9+)
  powershell -ExecutionPolicy Bypass -File build.ps1
  -> dist\Folder2PDF.exe   (portable; no Python needed on target machines)

INSTALL (per target machine; copy the exe to a permanent path first)
  copy dist\Folder2PDF.exe C:\Tools\Folder2PDF\
  C:\Tools\Folder2PDF\Folder2PDF.exe --register
  (self-locating: registers entries pointing at its own path, HKCU, no admin)

USAGE (Windows 11: Shift+Right-click or "Show more options")
  1. Right-click a FOLDER          -> "Merge to PDF" -> all images in it, sorted
  2. Right-click empty space in a folder -> same, current folder
  3. Select IMAGE FILES, right-click -> merged into ONE PDF, sorted by name
  4. Run the exe with NO arguments (double-click) -> a window opens; drag image
     files or folders onto it (or use the "Add images" button), then pick where
     to save. The window also has Register/Remove menu buttons and a language
     picker.
  Output (modes 1-3): <foldername>.pdf, auto _1, _2 on collision.
    - folder / folder-background mode -> written to the PARENT folder
    - selected-image-files mode       -> written to the images' OWN folder
  Output (mode 4): you choose via a Save As dialog (default name/location =
     the first image's folder + <foldername>.pdf).

MULTI-SELECT NOTE (important)
Classic Windows context-menu verbs invoke the exe once PER selected file.
The exe aggregates all invocations (named mutex + shared list + 900ms quiet-
period leader election) and the last process emits a single combined PDF.
The verb sets MultiSelectModel=Document so it shows on multi-selection; without
it Windows hides command-line verbs when >1 file is selected.
Windows caps once-per-file verbs at ~15 items: select more than that and the
entry disappears. For 15+ images, right-click the FOLDER instead (single
process, no timing dependency, no cap).

ORDERING
Natural sort by filename (Photo2 < Photo10). Deterministic regardless of the
order Windows spawns the per-file processes.

FORMATS
jpg jpeg png tif tiff bmp webp gif. JPEG/opaque images embed losslessly (no
re-encode). Alpha/transparent images are flattened onto white and embedded as
lossless PNG. Animated GIF/WebP: first frame only (one page).

LANGUAGE
UI is localized in English, Japanese, and Chinese. It auto-detects the Windows
UI language on first run; pick a language in the drop window to override it. The
choice is saved to %LOCALAPPDATA%\Folder2PDF\lang.txt and applies to every mode
(drop window, progress dialog, and right-click messages) on the next launch.

UNINSTALL
  Folder2PDF.exe --unregister
  (removes the HKCU registry entries only; never deletes any file)
