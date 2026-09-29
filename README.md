# ICA Automation

## Releases

Push a version tag matching `APP_VERSION` in `app.py` to build and publish a Windows release:

```powershell
git tag v1.0.1
git push origin v1.0.1
```

The GitHub Actions workflow produces `ica_automation.exe` and a SHA-256 checksum. The installed application checks the latest GitHub Release on startup. When a newer version is available, select `Install v<version>`; the download is verified against the release checksum, then the application restarts with the replacement executable.

The executable must be installed in a folder the current Windows user can modify. Installing it under `Program Files` requires administrator permission and will prevent unattended replacement.