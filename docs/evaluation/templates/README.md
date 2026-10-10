# Local evaluation package templates

`annotations.example.json` and `manifest.example.json` are illustrative templates with placeholders; they are not valid evaluation inputs until the source export, JD, rubric, split assignments, two blinded HR/IT annotations, adjudication, and predictions are complete. See the [protocol](../independent-human-evaluation-design.md) and [annotator guide](../human-evaluation-annotator-guide.md).

Create source blobs only from canonical sanitized CV/JD text under an institution-approved local storage location. Their names are content hashes; the identity map and original filenames stay outside the package. Never commit a populated manifest/package or copy it into issue trackers, chat, logs, or external model/tracing services.
