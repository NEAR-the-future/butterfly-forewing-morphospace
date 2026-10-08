# Tense and voice matrix

Tense in scientific English encodes *the status of the knowledge*, not the time of writing. Get the
function right and the manuscript reads as fluent scientific prose.

## The matrix

| Content | Tense | Voice | Example |
|---|---|---|---|
| Established knowledge, accepted mechanism | Present | either | `Wing shape scales with body size.` |
| Prior work by others | Past (or present perfect for an ongoing area) | active preferred | `Smith et al. showed that…` / `It has been shown that…` |
| Your methods, what you did | Past | active preferred | `We measured 120 wings.` |
| Methods steps where the actor is irrelevant | Past | passive | `Samples were incubated at 37 °C for 2 h.` |
| Your results, what you observed | Past | active or passive | `Wing length increased by 12% (P = 0.004).` |
| Reference to a figure, table, or equation | Present | active | `Figure 1 shows…` / `Equation 1 states…` |
| Interpretation of your results | Present | active | `These data indicate that…` |
| Mechanism you propose | Present | either | `We propose that X activates Y.` |
| Implications, general truths from your work | Present | either | `This suggests that temperature constrains…` |
| Limitations of the design | Present or past | active | `Our design cannot distinguish X from Y.` |
| What a cited method does in general | Present | active | `The assay detects…` |
| What you did with a cited method | Past | active | `We applied the assay described by…` |

## Rules that prevent tense errors

1. **One tense per function within a paragraph.** A Results paragraph that alternates between `we
   find` and `we found` reads as careless. Choose past for your observations and stay there.
2. **Do not use the present for your own completed measurements.** `Wing length increases by 12%` in
   a Results section claims a general law rather than your observation.
3. **Do not use the past for standing facts.** `Wing shape scaled with body size` in an Introduction
   implies the relationship has stopped.
4. **Figure and table references are always present tense.** `Figure 2 shows`, never `Figure 2 showed`.
5. **The abstract follows the same rules as the body.** It is not a separate tense system.
6. **Methods never hedge.** `Samples were possibly incubated` destroys reproducibility. If you do not
   know a parameter, say `the incubation time was not recorded`.

## Voice

Use **active** when the actor matters:

- Introduction and Discussion reasoning: `We propose…`, `We argue…`
- Results: `We observed…`, `We found…` — or a passive clause when the observation is the topic:
  `A 12% increase in wing length was observed`.
- Any statement of what *you* chose: `We excluded three samples because…`

Use **passive** when the actor is genuinely irrelevant or unknown:

- Standard procedures: `Cells were lysed in RIPA buffer.`
- When the object of the sentence is the topic of the paragraph: `The wings were photographed against
  a white background.`
- Clinical and pharmacological conventions where the patient or sample is the topic.

Never use passive to hide responsibility for a choice that affects the interpretation. Reviewers
read `outliers were removed` as an evasion; write `we removed three samples that exceeded the
pre-registered threshold`.

## Common non-native-speaker patterns and their fixes

| Pattern | Problem | Fix |
|---|---|---|
| `In this paper, we study…` | Acceptable but weak | State the finding: `Here we show…` |
| `It is well known that…` | Unattributed consensus claim | Cite the source or delete |
| `We can see that…` | Conversational | `The data show…` |
| `As we all know…` | Not academic | Delete |
| `In the following, we will…` | Roadmap without information | Delete or state the finding |
| `The result is very significant` | `significant` is a statistical term | Say `large` or give the *P* value |
| `respectively` with three or more items | Ambiguous pairing | Name the pairs |
| `on the other hand` without a first hand | Dangling contrast | Use `however` or supply both sides |
| `From the figure, we can find…` | Two vague verbs | `Figure 1 shows…` |
| `As shown in Figure 1, …` at the start of every sentence | Repetitive | Vary or integrate the citation |
| `data is` | Number disagreement | `data are` |
| `one of the most important` | Unsupported ranking | Give the evidence for importance |
| `et al` without a full stop | Typographic | `et al.` |
| `Table 1 shows the results of the experiment` | Content-free | State what the table shows |

## Editing procedure

1. Mark every finite verb in the section and label its function (established, prior work, our
   method, our result, interpretation).
2. Check each label against the matrix.
3. Fix voice only where the actor matters.
4. Read the section aloud for tense consistency at paragraph level.
5. Re-run `scripts/academic_lint.py` and confirm the tense and register findings are cleared.
