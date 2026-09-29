# ICA Automation

## Install

### From GitHub

1. Open the repository's **Releases** page: https://github.com/Samyajit-adusa/ica__status_checker/releases/latest
2. Download `ica_automation-windows.zip` from **Assets**.
3. Extract the ZIP into a folder you can modify, such as `%LOCALAPPDATA%\ICA Automation`.
4. Open `ica_automation.exe` from the extracted folder.

### From PowerShell

Paste this into PowerShell to download the latest release, verify its SHA-256 checksum, extract it, and start it:

```powershell
$dir = "$env:LOCALAPPDATA\ICA Automation"; $zip = "$env:TEMP\ica_automation-windows.zip"; $sum = "$zip.sha256"; New-Item -ItemType Directory -Force $dir | Out-Null; wget "https://github.com/Samyajit-adusa/ica__status_checker/releases/latest/download/ica_automation-windows.zip" -OutFile $zip; wget "https://github.com/Samyajit-adusa/ica__status_checker/releases/latest/download/ica_automation-windows.zip.sha256" -OutFile $sum; if ((Get-FileHash $zip -Algorithm SHA256).Hash.ToLower() -ne (Get-Content $sum).Split()[0].ToLower()) { Remove-Item $zip, $sum -Force; throw "Download verification failed." }; Expand-Archive -LiteralPath $zip -DestinationPath $dir -Force; Remove-Item $zip, $sum -Force; Start-Process "$dir\ica_automation.exe"
```

The app checks for new releases automatically. Use its `Install v<version>` button to download, verify, and apply future updates.

Older one-file installations migrate themselves to the faster folder-based package the next time they install an update.
