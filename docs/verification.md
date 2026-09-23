# Verification and limitations

## Automated checks

Run `./scripts/test.sh` on a Mac with Apple Command Line Tools. Tests cover:

- Original EPUB bytes, Finder tags and extended attributes.
- Source replacement/modification during processing, missing metadata, symlinks, size bounds.
- Clean names inside the archive, collisions, Unicode filename lengths.
- Preservation of separate files with identical contents but different attributes.
- Shortcut file-path input, shell quoting, and portable generation.
- Installer reapplication, settings preservation, rollback on replacement failure, shared locking, and refusal to overwrite unrelated apps.
- Matching the correct Kindle document, exact title/author verification, and explicit upload confirmation.

Automated tests do not establish that an Amazon upload succeeded. They do not grant permissions or use your Amazon account.

## Manual release check

1. Apply setup from a clean checkout with a temporary destination and review mode.
2. Import the generated shortcut and check Finder and Services Quick Actions. Enable Finder once if macOS left it unchecked.
3. Enable required permissions explicitly in macOS.
4. Select a disposable, valid EPUB with known title/author and run the generated Quick Action.
5. Confirm original bytes and attributes, cleaned archive name, Yellow tag, and correctly filled Kindle fields.
6. Cancel to check that no automatic submission happens in review mode.
7. Enable auto mode and run once. Observe `File sent`, `last-result.json` = `sent`, and the correct library title/author.
8. Reapply setup and verify configuration survives. Check that another run is rejected while the first is active.

## Compatibility

The build targets macOS 13+. It uses the Kindle Mac app extension identified as `com.amazon.Lassen.SendToKindleExtension` and English interface labels. Other Kindle apps, operating systems, and localized interfaces are not supported by this release. Compatibility with every macOS 13+ release is not implied by the deployment target.

### Version 0.1.0 release evidence

- Local verification: 19 Python tests and 9 Swift model checks passed.
- The macOS GitHub Actions build and tests passed.
- Setup built and installed the app, signed the generated shortcut, and preserved settings on reapplication.
- The signed shortcut imported successfully. Finder registration required enabling its checkbox once.
- On macOS 26.6 with Kindle 7.59, the packaged app opened the native share form and filled the correct title and author in review mode. The archived test EPUB retained its original SHA-256 and received the Yellow tag.
- On September 23, 2026, the generated Finder Quick Action completed the automatic flow with the installed release helper: moved the test EPUB into the configured archive, preserved its original SHA-256, applied Yellow, filled title/author, and sent it without manual form edits or a manual Send click.
- The helper recorded `sent` only after detecting Kindle’s `File sent` confirmation. Kindle library search subsequently showed exactly one result: **Book to Kindle Setup Check**, author **Book to Kindle**.
- The original source was removed after archiving; the confirmed job’s temporary share copy was cleaned up, and its local result record persisted.
- The final rebuild invalidated the earlier Accessibility grant. Toggling the old entry was insufficient; removing it and adding the installed app from `~/Applications/Book to Kindle.app` restored access. No helper rebuild was needed for this repair.

The full-flow validation was completed after the initial source ZIP was packaged. The code in that ZIP was the code tested; its earlier verification note is superseded by this document and the updated GitHub release notes.

## Review changes

The public implementation removes a Homebrew-specific Python path, personal archive defaults, machine-specific folder bookmarks, and the Shortcuts share chooser dependency. Review led to bounded ZIP processing, stable snapshots, source-change checks, preservation of per-file attributes, archive filename cleanup, explicit send outcomes, and staged app installation under a shared lock.

The helper relies on Kindle’s visible UI, rather than a documented Amazon upload API. If the expected form changes, it stops without retrying Send. A response from the share-service callback alone is not treated as successful delivery.
