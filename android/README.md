# MeetPoint Android development client — 0.4.1

This native Java/WebView shell uses the existing MeetPoint/PointCommun server. The 0.4.1 fix enables web media playback for later invitation sounds (the page still requires the user's sound opt-in) and implements a same-origin image document picker for PNG/JPEG/WebP. It also explicitly colors the server URL text for readable input. No backend, database or web UI files are part of this update.

The new application ID is `fr.meetpoint.app.debug`. The earlier installed development client was signed with another unavailable development key, so this build installs alongside it rather than replacing it. Enter the same server URL and log in with your existing account. Accounts, meetings and photos stay on the same server; no database migration or new account is needed. The web session/server URL must be entered again because Android app storage is separate.

The debug client accepts HTTP for a same-network demonstration and HTTPS for a reachable server. It has no SSL bypass, JavaScript bridge or background push implementation. Foreground in-app popup sounds are supported; app-closed/lock-screen delivery is not provided. Real GPS generally requires a secure origin and permissions.

## Build

Android Studio/Gradle: SDK35, AGP8.7.3, Gradle8.9, Java17. `./gradlew :app:assembleDebug`. The retained `debug-signing/meetpoint-debug.keystore` is only a DEVELOPMENT test key with standard known password `android`, alias `meetpointdebug`. It is not suitable for production releases. Preserve it for updates of this development app. Gradle's debug signing config uses this key.

Manual verified build without Gradle:

```bash
python3 android/tools/build_manual.py --sdk /path/to/sdk-extract --out MeetPoint-Android-fix.apk
```

The SDK directory must contain `android-35/android.jar` from Google's official `platform-35_r02.zip` and `android-15/` from `build-tools_r35_linux.zip`. Java17, Python3 and keytool are required. Java compilation uses the compiler module directly, so a separate javac launcher is not required.

## Validation

Java source compiled, D8 generated classes.dex, aapt2 linked localized resources/manifest, zipalign aligned the APK, and apksigner verified v2/v3 signatures. aapt2 verified application ID, versionCode4, versionName0.4.1, minSdk26 and targetSdk35. No physical-device runtime test was available.

APK SHA-256: `b335e6d4c72ee7f86c24663e641359e40f40fd13b8d14be6a4ece225017c9a11`


## Address field layout update — 0.4.2

Replaced the fixed 52-physical-pixel address field height with wrap-content, a 48dp minimum, dp-scaled padding and centered 16sp text. This avoids clipping text on high-density devices. Rebuilt with versionCode 5 and the same development signing certificate as 0.4.1, allowing installation as an update. Compilation, resource linking, D8, alignment and v2/v3 signatures passed. Physical-device rendering remains to be tested.
