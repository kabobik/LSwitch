Title: Simplify config model and remove admin panel (user-only config)

Summary

This PR simplifies LSwitch by removing the administrative UI and global `/etc` configuration workflow, making the following changes:

- Remove admin panel, secret trigger, and admin .desktop. GUI is now user-only and operates on `~/.config/lswitch/config.json`.
- If no user config exists, the application will create a default config on first run.
- Remove all automatic attempts to write/apply global config from the GUI. Any system-wide management should be done out-of-band (e.g., via packaging scripts or separate admin tools).
- Protect the runtime: GUI will no longer perform device-level operations or reload the daemon automatically, reducing the risk of input device locking.
- Update tests: removed admin-related tests; added tests validating user-only config creation and safe behavior.

Rationale

Previous admin functionality introduced complex flows and caused risky behavior (e.g., input device capture and unexpected SIGHUPs), leading to rare but severe failures. This change simplifies the model, improves safety, and makes the behavior predictable for users.

Notes for reviewers

- All tests pass in headless mode (with `LSWITCH_TEST_DISABLE_MONITORS=1` and `QT_QPA_PLATFORM=offscreen`).
- If a future need arises for system-wide admin management, it should be implemented as an explicit separate CLI tool or package hook (not mixed into the GUI).
