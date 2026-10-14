# Music Engine — Engineering Backlog & Task Specifications

This directory contains the canonical specifications, architectural requirements, bug reports, and implementation guides for extending, fixing, and optimizing **Music Engine**.

When an agent or developer is assigned to work on the project, consult this index, select the target task by priority, read its detailed specification file, and execute the implementation following the project directives.

---

## 🎯 Mandatory Directives for AI Agents & Contributors

Before implementing any task, review the project rules defined in `CONTEXT.md`:
1. **Code & Commits in English Only:** All code, function/class names, variables, comments, log output, and git commits must strictly be in English.
2. **Data Privacy & `.gitignore` Enforcement:** Never commit runtime databases (`*.sqlite`), personal `.env`, audio files (`*.opus`, `*.m4a`), cookies, or cache to Git.
3. **Documentation Sync:** Whenever changes affect CLI commands, database schema, or configuration options, update `CONTEXT.md`, `README.md`, and the relevant docs in `docs/en/` and `docs/es/`.
4. **Non-Breaking Architecture:** Preserve backward compatibility with existing databases and configuration files.

---

## 📋 Task Registry & Priority Matrix

| Priority | ID | Task Name | Target Files | Status | Spec File |
| :---: | :---: | :--- | :--- | :---: | :--- |
| **P0** | **TASK-01** | **Fix Critical Bugs in Downloader & Sync Manager** | `src/downloader.py`, `src/sync.py` | ✅ Completed | [`01_CRITICAL_BUGS.md`](01_CRITICAL_BUGS.md) |
| **P1** | **TASK-02** | **Implement Automated Test Suite (PyTest)** | `tests/`, `pytest.ini`, `requirements.txt` | ⏳ Ready | [`02_TEST_SUITE.md`](02_TEST_SUITE.md) |
| **P1** | **TASK-03** | **ListenBrainz MSID Cache & Loved Tracks Resolver** | `src/telemetry.py`, `database/schema.sql` | ⏳ Ready | [`03_TELEMETRY_MSID_CACHE.md`](03_TELEMETRY_MSID_CACHE.md) |
| **P2** | **TASK-04** | **Curator Local Radio Context & Scalability** | `src/curator_llm.py` | ⏳ Ready | [`04_CURATOR_LOCAL_RADIO_OPTIMIZATION.md`](04_CURATOR_LOCAL_RADIO_OPTIMIZATION.md) |
| **P2** | **TASK-05** | **System Health Audit (`doctor` command) & Syncthing Cleaner** | `src/cli.py`, `src/sync.py`, `src/engine.py` | ⏳ Ready | [`05_SYNCTHING_CONFLICTS_AND_HEALTH_DOCTOR.md`](05_SYNCTHING_CONFLICTS_AND_HEALTH_DOCTOR.md) |
| **P3** | **TASK-06** | **Audio Loudness Normalization (ReplayGain / EBU R128)** | `src/downloader.py`, `config/config.yaml.template` | ⏳ Ready | [`06_REPLAYGAIN_LOUDNESS_NORMALIZATION.md`](06_REPLAYGAIN_LOUDNESS_NORMALIZATION.md) |
| **P3** | **TASK-07** | **Dynamic Affinity Scoring for Conveyor Lifecycle** | `src/engine.py`, `database/schema.sql` | ⏳ Ready | [`07_SMART_CONVEYOR_SCORING.md`](07_SMART_CONVEYOR_SCORING.md) |

---

## 🛠️ Recommended Execution Order

1. **Step 1:** Execute **TASK-01** to fix runtime crashes in download and sync pipelines.
2. **Step 2:** Execute **TASK-02** to establish the automated test harness so subsequent changes are regression-tested.
3. **Step 3:** Execute **TASK-03** to eliminate the 500-scrobble pagination bottleneck in telemetry.
4. **Step 4:** Execute **TASK-04** and **TASK-05** for scalability, diagnostics, and folder hygiene.
5. **Step 5:** Execute **TASK-06** and **TASK-07** for advanced audio normalization and smart conveyor mechanics.
