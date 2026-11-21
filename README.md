# Universal Portable Maker

Turn Windows programs into **portable versions** that keep all their data on your USB drive.

Pick an `.exe`, a folder, a `.zip`, an `.msi`, or a script, and the tool generates a launcher that runs the app with `AppData`, `Documents`, `Temp`, and `ProgramData` redirected to a folder next to it. Take the USB drive to another PC and the app opens with the same settings and files.

## Features

- Simple graphical interface (Tkinter, no extra dependencies for the generator)
- Accepts many source types (see the table below)
- Automatically detects whether the app is a console or a windowed program
- Two output modes: **single file** or **folder**
- Option to clean the `Temp` folder when the app closes
- Command-line arguments support
- The generated launcher **does not need Python** on the target PC

## Supported source types

| Source | How it is handled |
|---|---|
| `.exe` | Run directly |
| `.bat`, `.cmd` | Run through `cmd /c` |
| `.ps1` | Run through PowerShell |
| `.py`, `.pyw` | Run with Python (from the PC or an embedded portable one) |
| `.jar` | Run with Java (from the PC or an embedded portable one) |
| `.js` | Run with Node.js (from the PC or an embedded portable one) |
| `.vbs` | Run through `wscript` |
| Folder | You choose the main program inside it |
| `.zip`, `.tar`, `.tar.gz`, `.tgz`, `.tar.bz2`, `.tar.xz` | Extracted automatically |
| `.7z`, `.rar`, `.iso`, `.cab`, `.wim` | Extracted with [7-Zip](https://www.7-zip.org/) |
| `.msi` | Extracted **without installing**, via `msiexec /a` |
| `.exe` installer (NSIS and similar) | Extracted with 7-Zip (tick the option in the interface) |

## Requirements

To **generate** the launcher:

- Windows
- Python 3.9 or newer (with Tkinter, included in the official installer)
- [PyInstaller](https://pyinstaller.org/) (installed automatically if missing)
- 7-Zip (only for `.7z`, `.rar`, `.iso`, and installers)

To **use** the generated launcher: just Windows.

## Usage

```bash
git clone https://github.com/LucasRanieridaSilva/universal-portable-maker.git
cd universal-portable-maker
python UniversalPortableMaker.py
```

1. Click **File...** or **Folder...** and choose the source.
2. Check the suggested **main program** (you can change it in the list).
3. Set the name, the arguments (optional), and the output folder, preferably your USB drive.
4. Choose the output mode and click **Generate portable version**.

Result:

```
USB drive/
├── MyApp_Portable.exe       <- the launcher
└── MyApp_Data/              <- created on first run
    ├── App/                 <- extracted program (single-file mode)
    └── Data/
        ├── Profile/         <- USERPROFILE, AppData, Documents, Desktop, Downloads
        ├── Temp/            <- TEMP and TMP
        └── ProgramData/
```

## Output modes

| Mode | Advantage | Drawback |
|---|---|---|
| **Single file** | One `.exe`, easy to copy | On launch, PyInstaller briefly extracts a copy into the PC's `Temp` (deleted when the app closes) |
| **Folder** | Faster and does not use the PC's `Temp` | You have to carry the whole folder |

In neither mode does the app's data stay on the PC.

## How it works

The generator creates a small Python launcher, bundles the original program inside it with PyInstaller, and stores the configuration (main program, arguments, type). When run, the launcher:

1. creates the `<Name>_Data` structure next to itself;
2. overrides the environment variables `USERPROFILE`, `HOME`, `APPDATA`, `LOCALAPPDATA`, `TEMP`, `TMP`, `PROGRAMDATA`, `HOMEDRIVE`, and `HOMEPATH`;
3. starts the program with those variables and waits for it to finish.

## Scripts with a portable runtime

`.py`, `.jar`, and `.js` scripts need the matching runtime. To make them 100% portable, put the portable version **inside the source folder** before generating. The launcher looks in these paths before falling back to whatever is installed on the PC:

| Runtime | Paths searched |
|---|---|
| Python | `python/python.exe`, `Python/python.exe`, `runtime/python.exe`, `python.exe` |
| Java | `jre/bin/java.exe`, `jdk/bin/java.exe`, `java/bin/java.exe`, `runtime/bin/java.exe` |
| Node.js | `node/node.exe`, `node.exe` |

## Limitations

- **Windows Registry:** programs that write to the Registry are not redirected.
- **Hardcoded paths:** programs that use absolute paths (such as `C:\Users\John`) bypass the redirection.
- **Installers:** only those that 7-Zip can extract work. Inno Setup installers need [innoextract](https://constexpr.org/innoextract/).
- **Administrator:** programs that require administrator privileges only run if the launcher is opened as administrator.
- **Antivirus:** executables generated with PyInstaller are sometimes flagged as suspicious (false positive). If that happens, add an exception.
- **File system:** format the USB drive as **exFAT** or **NTFS**. FAT32 does not support files larger than 4 GB.
- **Operating system:** the generator and the launchers are for Windows.

## Responsible use

Only use this tool with software you have the right to copy and redistribute. Respect the licenses of the programs you convert.

## Contributing

Contributions are welcome. Open an issue to report problems or suggest improvements, or send a pull request.

Ideas for the future:

- Windows Registry redirection (export/import keys on open and close)
- Custom icon for the launcher
- Interface to set extra environment variables
- Linux and macOS support

## License

Distributed under the [MIT](https://opensource.org/license/mit) license. You may use, copy, modify, distribute, and even sell this program, as long as you keep the copyright notice and the license in copies. See the `LICENSE` file.
