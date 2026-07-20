# IMPACT-2026 Text Campaigns — Names, Message Text, and Theme Codes

The 12 text campaigns sent by IMPACT Community Action between January and
March 2026 — the only cohort with uniform application attribution (used by the
f06 hazard model). Message bodies are verbatim from
`empower_development.campaigns.message_body`. Theme codes were backfilled on
2026-07-15 by inheriting labels from verbatim-identical, already-coded 2025
campaigns (see `scripts/backfill_impact2026_message_types_tool.py`).

The 12 campaigns use only **4 distinct message bodies**; each body was sent as
two "Section" audience splits, and two bodies were reused on a second send
date.

## Campaign index

| Sent | Campaign name | Message | Themes |
|---|---|---|---|
| 2026-01-10 | EmpowerSaves WCP Text2 Section 1 - IMPACT 2026-01-10 | A — Extreme heat / prequalified | urgency_deadline, personalized_qualified, relief_reassurance |
| 2026-01-10 | EmpowerSaves WCP Text2 Section 2 - IMPACT 2026-01-10 | A — Extreme heat / prequalified | urgency_deadline, personalized_qualified, relief_reassurance |
| 2026-01-23 | EmpowerSaves OH Text75 Winter Section1 - IMPACT 2026-01 | B — Temperatures rise / StayCool | informational, motivational_struggle, relief_reassurance |
| 2026-01-23 | EmpowerSaves OH Text76 Winter Section2 - IMPACT 2026-01 | B — Temperatures rise / StayCool | informational, motivational_struggle, relief_reassurance |
| 2026-02-04 | EmpowerSaves OH Text77 WCP Section1 - IMPACT 2026-02 | A — Extreme heat / prequalified | urgency_deadline, personalized_qualified, relief_reassurance |
| 2026-02-04 | EmpowerSaves OH Text78 WCP Section2 - IMPACT 2026-02 | A — Extreme heat / prequalified | urgency_deadline, personalized_qualified, relief_reassurance |
| 2026-02-27 | EmpowerSaves OH Text79 Cold Section1 - IMPACT 2026-03 | B — Temperatures rise / StayCool | informational, motivational_struggle, relief_reassurance |
| 2026-02-27 | EmpowerSaves OH Text80 Cold Section2 - IMPACT 2026-03 | B — Temperatures rise / StayCool | informational, motivational_struggle, relief_reassurance |
| 2026-03-27 | EmpowerSaves OH Text81 EndsSoon Section1 - IMPACT 2026-04 | C — Time running out / savings | urgency_deadline, savings_financial, relief_reassurance |
| 2026-03-27 | EmpowerSaves OH Text82 EndsSoon Section2 - IMPACT 2026-04 | C — Time running out / savings | urgency_deadline, savings_financial, relief_reassurance |
| 2026-03-31 | EmpowerSaves OH Text83 LastDay Section1 - IMPACT 2026-04 | D — Final day | urgency_deadline, relief_reassurance |
| 2026-03-31 | EmpowerSaves OH Text84 LastDay Section2 - IMPACT 2026-04 | D — Final day | urgency_deadline, relief_reassurance |

## Message A — "Extreme heat / prequalified" (WCP)

**Used by:** WCP Text2 Section 1 & 2 (2026-01-10), Text77 & Text78 (2026-02-04)
**Themes:** urgency_deadline, personalized_qualified, relief_reassurance
(inherited from 2025 Text31–34 SummerCrisisProgram)

> NAME, this extreme heat isn't just uncomfortable—it's expensive. Your energy
> bills are about to spike, and they'll stay high all summer unless you act
> now. The good news? You're already prequalified for Ohio's Summer Crisis
> Program, which offers immediate financial help to lower your bills and keep
> your home safe and cool. But funds are limited. Don't wait—get connected
> with an intake specialist today. From IMPACT. Apply here:
> https://bit.ly/3H2UDi1 Reply STOP to opt out.

## Message B — "Temperatures rise / StayCool"

**Used by:** Text75 & Text76 (2026-01-23), Text79 & Text80 (2026-02-27)
**Themes:** informational, motivational_struggle, relief_reassurance
(inherited from 2025 Text19–22 StayCool)

> Hello, FIRST NAME... As temperatures rise across Ohio, we want to ensure
> that no family has to choose between staying cool and paying other essential
> bills. The Ohio Summer Crisis Program is now accepting applications, and we
> encourage eligible households to enroll as soon as possible. This is real
> financial relief! From IMPACT Community Action. Apply here:
> https://tinyurl.com/Stay-Cool-IMPACT Reply STOP to opt out.

## Message C — "Time running out / savings" (EndsSoon)

**Used by:** Text81 & Text82 (2026-03-27)
**Themes:** urgency_deadline, savings_financial, relief_reassurance
(inherited from 2025 Text63–68 Time_Running_Out)

> Evening (6-8) - \<VD_FirstName\>, time is running out! The Ohio Summer
> Crisis Program ends soon. This is your easiest path to real financial
> relief. Based on your home's energy use, you could save about
> $\<VD_MonthlySavings\>/month on energy costs. Don't miss out— applications
> close 9/30! https://tinyurl.com/Act-Now-COAD From COAD.

## Message D — "Final day" (LastDay)

**Used by:** Text83 & Text84 (2026-03-31)
**Themes:** urgency_deadline, relief_reassurance
(inherited from 2025 Text71–74 Final_Day)

> \<VD_FirstName\>, today is your FINAL DAY to enroll in Ohio's Summer Crisis
> Program. This is the quickest and easiest way towards lasting financial
> assistance. After tomorrow, it won't be as easy. Click here to apply:
> http://bit.ly/4nW6Wg3 From COAD. Text STOP to opt out.

## Notes and oddities

- **Season mismatch:** Messages A and B use summer copy ("extreme heat",
  "staying cool") but were sent in January–February. Worth flagging to the
  program team; it also complicates interpreting a "theme × weather"
  interaction.
- **Sender mismatch:** Messages C and D are signed "From COAD" and use
  COAD-branded links, although the campaigns are attributed to IMPACT
  Community Action.
- **Analysis caveat:** only 4 theme profiles exist across the 12 campaigns,
  and the urgency-heavy messages (C, D) coincide exactly with the late-March
  wave-end sends — theme effects are partially confounded with the dominant
  wave-timing effect in f06. All four profiles include `relief_reassurance`,
  so that code has zero contrast in this cohort.
