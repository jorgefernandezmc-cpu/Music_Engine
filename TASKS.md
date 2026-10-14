# Music Engine — Development Backlog & Actionable Tasks

This document links to the engineering backlog, bug fixes, performance optimizations, and planned architectural enhancements for **Music Engine**.

All detailed technical specifications, root causes, line-number references, and step-by-step implementation guides are located in the [`tasks/`](tasks/README.md) directory.

---

## 🧭 Quick Task Index

| Priority | ID | Task Name | Key Target Files | Status | Specification |
| :---: | :---: | :--- | :--- | :---: | :--- |
| **P0** | **TASK-01** | **Fix Critical Bugs in Downloader & Sync Manager** | `src/downloader.py`, `src/sync.py` | ✅ Completed | [📄 View Spec](tasks/01_CRITICAL_BUGS.md) |
| **P1** | **TASK-02** | **Implement Automated Test Suite (PyTest)** | `tests/`, `pytest.ini` | ✅ Completed | [📄 View Spec](tasks/02_TEST_SUITE.md) |
| **P1** | **TASK-03** | **ListenBrainz MSID Cache & Loved Tracks Resolver** | `src/telemetry.py`, `database/schema.sql` | ✅ Completed | [📄 View Spec](tasks/03_TELEMETRY_MSID_CACHE.md) |

| **P2** | **TASK-04** | **Curator Local Radio Context & Scalability** | `src/curator_llm.py` | ✅ Completed | [📄 View Spec](tasks/04_CURATOR_LOCAL_RADIO_OPTIMIZATION.md) |

| **P2** | **TASK-05** | **System Health Audit (`doctor` command) & Syncthing Cleaner** | `src/cli.py`, `src/sync.py`, `src/engine.py` | ✅ Completed | [📄 View Spec](tasks/05_SYNCTHING_CONFLICTS_AND_HEALTH_DOCTOR.md) |

| **P3** | **TASK-06** | **Audio Loudness Normalization (ReplayGain / EBU R128)** | `src/downloader.py`, `config/config.yaml.template` | ✅ Completed | [📄 View Spec](tasks/06_REPLAYGAIN_LOUDNESS_NORMALIZATION.md) |

| **P3** | **TASK-07** | **Dynamic Affinity Scoring for Conveyor Lifecycle** | `src/engine.py`, `database/schema.sql` | [📄 View Spec](tasks/07_SMART_CONVEYOR_SCORING.md) |

---

## 📌 Implementation Directives for AI Agents

1. **Strict English Standard:** All newly authored Python code, classes, docstrings, log lines, and git commits must be in English.
2. **Never Commit User Data:** Do not commit databases (`*.sqlite`), personal tokens in `.env`, or audio files (`.opus`, `.m4a`).
3. **Verify with Tests:** For each task, write or run corresponding tests in `tests/` before completing the task.
4. **Update Documentation:** Whenever database schema, CLI flags, or lifecycle behaviors change, update `CONTEXT.md` and `README.md`.
