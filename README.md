# ICA Automation

## Install

### From GitHub

1. Open the repository's **Releases** page: https://github.com/Samyajit-adusa/ica__status_checker/releases/latest
2. Download `ica_automation.exe` from **Assets**.
3. Save it in a folder you can modify, such as `%LOCALAPPDATA%\ICA Automation`, then open the file.

### From PowerShell

Paste this into PowerShell to download the latest release, verify its SHA-256 checksum, and start it:

```powershell
$dir = "$env:LOCALAPPDATA\ICA Automation"; New-Item -ItemType Directory -Force $dir | Out-Null; $exe = "$dir\ica_automation.exe"; $sum = "$exe.sha256"; wget "https://github.com/Samyajit-adusa/ica__status_checker/releases/latest/download/ica_automation.exe" -OutFile $exe; wget "https://github.com/Samyajit-adusa/ica__status_checker/releases/latest/download/ica_automation.exe.sha256" -OutFile $sum; if ((Get-FileHash $exe -Algorithm SHA256).Hash.ToLower() -ne (Get-Content $sum).Split()[0].ToLower()) { Remove-Item $exe, $sum -Force; throw "Download verification failed." }; Remove-Item $sum -Force; Start-Process $exe
```

The app checks for new releases automatically. Use its `Install v<version>` button to download, verify, and apply future updates.

## Releases

Push a version tag matching `APP_VERSION` in `app.py` to build and publish a Windows release:

```powershell
git tag v1.0.1
git push origin v1.0.1
```

The GitHub Actions workflow produces `ica_automation.exe` and a SHA-256 checksum. The installed application checks the latest GitHub Release on startup. When a newer version is available, select `Install v<version>`; the download is verified against the release checksum, then the application restarts with the replacement executable.

The executable must be installed in a folder the current Windows user can modify. Installing it under `Program Files` requires administrator permission and will prevent unattended replacement.