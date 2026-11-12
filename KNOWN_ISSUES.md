# Known issues

- The launcher itself does not provide any game executable or ROM; title availability depends on user-selected local files.
- USA, Exotica, and Velocity are disabled. The launcher does not establish that they are playable.
- Optional artwork is absent. The code uses a built-in/programmatic fallback when a configured image is missing.
- PySide6 was unavailable in the preparation environment. GUI launch and GUI tests were not verified.
- Headless tests do not verify visual rendering or real-game launch behavior.
- The optional PyInstaller packaging recipe was not run. `Launcher/CruisnXtreme.spec` now uses the provisional identifier `org.cruisnxtreme.launcher` at the owner’s direction. It has not been registered or checked for global uniqueness, and no bundle was produced.
- The World SHA-256 is a factual ROM-revision compatibility identifier, not a ROM copy or grant of rights in the game.

- Staging adjustments from the prior reviewed source snapshot: README wording now identifies the experimental source-only preview, World-first availability, Velocity test status, and unverified packaging; the spec uses the owner-requested provisional bundle identifier. These intentional changes alter the original manifest hashes for those files.
