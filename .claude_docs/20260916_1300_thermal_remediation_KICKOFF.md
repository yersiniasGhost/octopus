# Kickoff prompt — paste after clearing context

Replace `<TASK>` with the task id (`Task 0`, `T-00`, `T-01` … `T-14`) and paste.

---

```
We are working through a thermal-slope remediation on the octopus project,
branch feature/campaign-weather. I have cleared context, so read these first:

  .claude_docs/20260916_1300_thermal_slope_remediation_runbook.md   <- execution runbook, start here
  .claude_docs/20260916_1113_thermal_slope_remediation_todo.md      <- findings and evidence

Today I want to do exactly one task: <TASK>

Ground rules:
- source venv/bin/activate before any Python.
- Do NOT start any other task. If you find a problem belonging to a different
  task, write it down and tell me — do not fix it.
- Take the checkpoint the runbook specifies for this task BEFORE any write, using
  src/scripts/backup_mongo_collections_tool.py. No checkpoint, no write.
- Write the tests first, then the script. Every write script is --dry-run by
  default and needs --execute to touch data.
- Show me the dry-run output and wait for my go-ahead before executing.
- Verify with scripts/audit_thermal_load_coverage_tool.py, never an ad-hoc query.
- New scripts: scripts/ with a _tool suffix, plus an entry in
  .claude_docs/script_descriptions.md. Reusable ones: src/scripts/ plus
  .claude_docs/tools.md.
- Commit when the task's "Done when" is satisfied.

Start by confirming the current state matches the runbook's baseline table
(Appendix, "Baseline numbers to check against"), then tell me your plan for
<TASK> before writing anything.
```

---

## Shorter variant, once you are a few tasks in

```
Continuing the thermal-slope remediation, branch feature/campaign-weather.
Read .claude_docs/20260916_1300_thermal_slope_remediation_runbook.md and do
<TASK> only, following its checkpoint / test / dry-run / execute / verify
sequence. Confirm the baseline audit first, show me the dry run, and wait for
my go-ahead before executing.
```

## Recommended order

1. **Task 0** — baseline backup and rollback drill. Nothing else runs until this passes.
2. **T-12** — small code fix; landing it early stops T-07 and T-09 manufacturing bad zero slopes.
3. **T-01** — gas preservation. The only item that destroys data.
4. **T-02** → **T-03** → **T-04** → **T-05** → **T-06** — remaining P0 blockers.
5. **T-00** — weather data. Blocks everything that computes; can be worked in parallel since it is
   mostly data acquisition rather than code.
6. **T-10** → **T-08** → **T-07** — provenance, Montgomery's key, then compute the 60,733.
7. **T-09** — refresh the 646,375 stale parcels.
8. **T-11**, **T-13** — quality cleanup.
9. **T-14** — separate project, scope it on its own.

## Session-start sanity check

```bash
source venv/bin/activate
git branch --show-current
python src/scripts/backup_mongo_collections_tool.py list
python scripts/audit_thermal_load_coverage_tool.py --check all
```
