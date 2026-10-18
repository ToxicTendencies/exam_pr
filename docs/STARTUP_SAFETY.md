# Startup safety

The Android shell is deliberately minimal. Startup does only the following:

1. Create `WebView`.
2. Enable JavaScript and DOM storage.
3. Allow local asset files.
4. Block network requests.
5. Load `file:///android_asset/index.html`.

No system color chooser or native JS bridge is required for startup.

The distributed APK uses the native DEX/resource shell from the user-confirmed working v9 build, with only the manifest package/label/version and web assets changed. This choice was made because no physical Android runtime is available in the build environment.
