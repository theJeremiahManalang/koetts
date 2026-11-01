# Event-driven hosted operation dispatch

Hosted queue changes create durable Firestore dispatch signals in the same transaction as the operation transition; Eventarc delivers those signals to the private API, which claims work from authoritative operation state. Scheduled coordination remains for crash reconciliation and missed-signal repair, not normal dispatch. Signals are treated as duplicate, unordered wake-ups, so existing fences, capacity transactions, and budget admission remain authoritative.
