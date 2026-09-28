from __future__ import annotations

import build_evidence_audit_packets as base


# Input-shape adapter only. All evidence resolution and packet construction
# remain in the previously used official Pass 2 builder.
base.ALIASES = tuple(f"Candidate {letter}" for letter in "ABCD")


if __name__ == "__main__":
    base.main()
