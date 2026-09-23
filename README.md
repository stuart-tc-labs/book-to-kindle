# Book to Kindle

**Select an EPUB in Finder. Archive it, clean its filename, add a Yellow tag, and send it to Kindle—with the book’s title and author filled in automatically.**

A small, local macOS helper plus a Finder Quick Action. The installer builds the app and generates the shortcut from source. No Homebrew, API keys, email configuration, or hosted service is required.

```text
Downloads/My messy download.epub
                 │
                 ▼
Documents/Books/Book Title — Author.epub  • Yellow tag
                 │
                 ▼
Send to Kindle → fill title and author → verify → Send → confirm
```

## Get started

1. Install the [Kindle Mac app](https://apps.apple.com/app/kindle/id302584613) and sign in. Its **Send to Kindle** share extension must be available.
2. Install Apple’s Command Line Tools if you do not already have them:

   ```sh
   xcode-select --install
   ```

3. [Download the source ZIP](https://github.com/stuart-tc-labs/book-to-kindle/releases/latest/download/book-to-kindle-source.zip), unzip it, and double-click **install.command**. Alternatively, clone and apply:

   ```sh
   git clone https://github.com/stuart-tc-labs/book-to-kindle.git
   cd book-to-kindle
   ./install.command
   ```

4. Finish the macOS setup prompts:
   - Click **Add Shortcut** in Shortcuts. On an update, choose **Replace** rather than keeping a duplicate.
   - Open the shortcut’s **Details** and enable **Use as Quick Action → Finder** if unchecked. macOS can leave Finder disabled after import, even though the generated shortcut declares it.
   - Enable **Shortcuts → Settings → Advanced → Allow Running Scripts**.
   - Enable **Book to Kindle** in **System Settings → Privacy & Security → Accessibility**.
   - Approve access to your selected files when macOS asks.
5. Select one EPUB in Finder, then choose **Quick Actions → Book to Kindle**. For a hotkey, open the shortcut’s **Details → Add Keyboard Shortcut**; **Control–Option–K** is a suggestion, provided it is unused on your Mac.

Leave the Mac awake and unlocked while a book is sending. Allow the first launch a moment to open Kindle’s form; do not repeatedly trigger the shortcut.

**Supported scope:** macOS 13 or later, one EPUB per run, and Kindle’s **English** share interface. The source builds for your Mac’s architecture. This is an early release; Kindle interface changes can require updates. See [verification and limitations](docs/verification.md) for the platforms actually tested.

## Choose your archive folder or review before sending

The default archive is **`~/Documents/Books`**. To choose another location:

```sh
./scripts/apply.sh --destination "$HOME/Documents/My Library/Books"
```

Automatic sending is the default. To fill the fields and let you review them before clicking Send:

```sh
./scripts/apply.sh --mode review
```

To return to automatic sending:

```sh
./scripts/apply.sh --mode auto
```

Reapplying preserves existing settings unless you supply replacements. `--no-open` builds and installs without opening the setup windows. It does **not** silently import shortcuts or grant permissions.

## What happens to the file?

- The helper reads the EPUB’s embedded title and author. It normalizes whitespace and simple `Surname, Given` names; correctly marked translators are excluded from the author field.
- It archives the **original EPUB bytes**, with a filename such as `Book Title — Author.epub`. Filesystem-unsafe characters are replaced, and long names are shortened.
- Existing Finder tags and file metadata are preserved; a **Yellow** tag is added. Yellow means **archived**, not confirmed delivered.
- Filename collisions receive a numbered suffix. Separate source files are not deduplicated: identical book bytes may still have different tags or other metadata.
- The source is removed only after the archive’s bytes are verified and the source is checked for modification or replacement. Do not run this on a download still being written.
- A separate, byte-identical temporary copy is shared. Its unique filename identifies the correct Kindle form; the identifier is removed from the title before sending.
- The helper verifies both fields, clicks Send once, and reports success only after Kindle displays **File sent**. That means Amazon accepted the file; delivery to individual devices may take longer.

An EPUB’s metadata can be incorrect. The helper cannot infer the correct author from a misleading credit or repair a garbled title. Use review mode when metadata needs inspection. This project does not download books or remove DRM.

## What is programmatic?

`install.command` runs the complete apply process:

1. Build the Swift app and bundle the standard-library Python EPUB processor.
2. Generate the shortcut definition with `scripts/generate_shortcut.py`.
3. Sign it using Apple’s `shortcuts sign --mode anyone` command.
4. Install the app at `~/Applications/Book to Kindle.app` and persist your configuration.
5. Open the signed shortcut for import and the app’s permission setup.

The shortcut is a small, quoted shell launcher. It has no personal paths, folder bookmarks, or hand-edited sharing actions. The app opens Kindle’s native sharing service directly.

**The remaining clicks are intentional:** macOS controls shortcut import, script execution, Accessibility, file access, Finder Quick Action registration, and keyboard shortcuts. Setup does not edit the Shortcuts database, grant itself permissions, or replace existing hotkeys. [Apple documents shortcut signing](https://support.apple.com/guide/shortcuts-mac/run-shortcuts-from-the-command-line-apd455c82f02/mac) and [Quick Action keyboard setup](https://support.apple.com/guide/shortcuts-mac/run-a-shortcut-while-working-on-your-mac-apd163eb9f95/mac).

## Privacy and permissions

Book parsing and archiving happen locally. The helper has no analytics, server, credentials, or direct network upload code. Kindle’s extension sends the selected book to your Amazon account. Apple receives the generated shortcut for validation during signing; the shortcut contains launcher code, not your ebooks.

Accessibility lets the app fill and press controls in its own Kindle share window. The code scopes its UI search to its own process and checks the temporary book identifier before acting. macOS grants this permission broadly, so review the source before enabling it.

The app is compiled and ad-hoc signed locally, not distributed as a notarized binary. No administrator password is required by the installer, and it does not change Gatekeeper settings. macOS may ask you to re-enable Accessibility after an update.

## Updates, recovery, and removal

For a Git checkout:

```sh
git pull --ff-only
./install.command
```

For a ZIP install, download the new version and run its `install.command`. The installer preserves configuration, stages and verifies the replacement app, keeps the previous app as a local backup, and refuses to replace an unrelated app. If setup is interrupted, rerun it. Each successful upgrade retains a `Previous-*.app` backup in `~/Applications/.Book to Kindle Backups/`; older backups can be removed when no longer needed.

If sending fails or times out, the book remains archived. **Check Kindle’s library before retrying**: a timeout after Send can mean the upload succeeded without a confirmation being observed. Selecting an already archived book retries delivery; it may create another Kindle copy if it was already sent.

Local files:

| Location | Purpose |
| --- | --- |
| `~/Applications/Book to Kindle.app` | Built helper and bundled Python source |
| `~/Library/Application Support/Book to Kindle Shortcut/config.json` | Destination and mode |
| `~/Library/Application Support/Book to Kindle Shortcut/last-result.json` | Most recent book outcome |
| `~/Library/Application Support/Book to Kindle Shortcut/results/` | Per-book outcome records |
| `~/Library/Caches/Book to Kindle Shortcut/` | Temporary share copies; confirmed sends are cleaned up |
| `dist/Book to Kindle.shortcut` | Generated, signed shortcut in your checkout |

Result records contain book titles, authors, archive paths, and hashes. They stay on your Mac. Failed or interrupted share copies remain for troubleshooting; when the helper is closed, you can remove its cache folder without affecting archived books.

To uninstall, remove **Book to Kindle** from Shortcuts, move the app to Trash, disable its Accessibility permission, and optionally remove the support/cache folders and `~/Applications/.Book to Kindle Backups/`. Your archive folder and Kindle library are not touched.

## Troubleshooting

- **“Select exactly one EPUB”**: select one `.epub` in Finder before running the Quick Action. Running from Shortcuts itself offers a file picker.
- **No Quick Action**: check the shortcut’s Details has **Use as Quick Action → Finder** enabled. The generated definition declares this setting, but macOS may require enabling it once after import.
- **Script execution blocked**: enable Allow Running Scripts in Shortcuts’ Advanced settings.
- **Permission missing after an update**: quit the helper and re-enable **Book to Kindle** in Accessibility. If macOS keeps an obsolete entry, remove it and add the app from `~/Applications` again.
- **Kindle extension unavailable**: open Kindle, sign in, and check that Send to Kindle appears in macOS sharing extensions. The standalone legacy Send to Kindle app is not the supported target.
- **Unexpected form or language**: this release recognizes English Kindle labels. It stops instead of guessing which controls to press.
- **Missing title/author**: correct the EPUB metadata first; the source is left in place.
- **Large or invalid EPUB**: limits are 200 MiB compressed, 512 MiB expanded, 10,000 ZIP entries, and bounded XML metadata. Corrupt, duplicate-entry, or ZIP-encrypted archives are rejected.
- **“Another book…”**: finish the active send or close its error dialog. The same lock prevents an installation from replacing the app during a send.

## Development

```sh
./scripts/test.sh
```

This builds a local app, runs the Python integration/installer tests, and runs Swift model checks. CI uses a macOS runner; it does not sign in to Kindle, grant Accessibility, or upload a book. Native share integration needs the manual checks in [verification.md](docs/verification.md).

| Source | Responsibility |
| --- | --- |
| `src/books.py` | EPUB validation, metadata, verified archive, tags, share snapshot |
| `src/App.swift` | App lifecycle, sharing service, send state, status records |
| `src/Accessibility.swift` | Bounded AX traversal and control access |
| `src/SendJob.swift` | Job/config models and field verification |
| `scripts/generate_shortcut.py` | Shortcut definition as code |
| `scripts/apply.py`, `scripts/install.py` | Apply lock, signing, configuration, app replacement |

[MIT license](LICENSE). Not affiliated with Amazon or Apple.
