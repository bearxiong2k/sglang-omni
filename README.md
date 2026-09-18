# OmniTyper conservative usability comparison

Baseline: `524a3843`. Reviewed change: `da730319`.

Unedited native window captures with matching system appearance and Swift package builds (linked SDK 14.0). Production views use isolated sample data. Keyboard fixture commands set notices and scroll to the model card without an automation pointer. No microphone or external text API is used. Purple title-bar indicators belong to macOS screen capture.

## Console controls and shortcut display

| Before | After |
| --- | --- |
| ![Before](settings-before.jpg) | ![After](settings-after.jpg) |

## Notifications at the top of Settings

| Before | After |
| --- | --- |
| ![Before](notifications-before.jpg) | ![After](notifications-after.jpg) |

## Notifications after scrolling

| Before | After |
| --- | --- |
| ![Before](scrolled-before.jpg) | ![After](scrolled-after.jpg) |

## Speech-model retention

| Before | After |
| --- | --- |
| ![Before](model-before.jpg) | ![After](model-after.jpg) |

## Recording popup

The existing header can be dragged without taking input focus. Stop and Cancel retain compact spacing with larger rectangular targets. These interaction changes are described in text, without a static popup comparison.
