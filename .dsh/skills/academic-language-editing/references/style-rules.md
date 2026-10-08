# Style rules

The full rulebook behind `scripts/academic_lint.py`. Each rule id appears in the linter output, so
a finding can be traced back to the rationale here.

## Sentences

| Rule | Problem | Fix |
|---|---|---|
| `LEN001` | Sentence above ~30 words | Split at the first independent clause boundary |
| — | Two independent clauses joined by "and" | Split when the halves are logically separate |
| — | Dangling modifier ("Using X, the result was…") | Name the actor: "Using X, we found…" |
| — | Nested negation ("not unlikely", "not inconsistent with") | State the positive claim |
| — | Misplaced "only" | Place it immediately before the word it limits |

## Verbs, tense and voice

See `tense-and-voice.md` for the matrix. Quick rules:

- One tense per function; do not alternate between past and present inside a single Results paragraph.
- Passive is legitimate when the actor is unknown, irrelevant, or genuinely generic; it is a defect
  when it hides who did the work in the Introduction, Results or Discussion.
- No first-person hedging (`we believe`, `we feel`) — state the claim and give the evidence.
- No anthropomorphising assays (`the gel shows`, `the antibody recognises`) unless the convention of
  the field explicitly permits it.

## Hedging calibration

| Strength | Verbs | Use when |
|---|---|---|
| Strong | demonstrates, establishes, shows, rules out | design eliminates the alternatives |
| Moderate | indicates, suggests, is consistent with, supports | evidence is strong but indirect |
| Weak | may, might, appears to, is compatible with | exploratory or single-line evidence |

Never stack (`may possibly suggest`). Never promote (`proves`) — empirical work does not prove.
Causal verbs (`causes`, `leads to`, `affects`) require a design that manipulates the cause.

## Diction

| Rule | Instead of | Use |
|---|---|---|
| `DIC001` | utilise | use |
| `DIC002` | in order to | to |
| `DIC003` | due to the fact that | because |
| `DIC004` | a large number of | give the count or proportion |
| `DIC005` | prior to | before |
| `DIC006` | subsequent to | after |
| `DIC007` | in the event that | if |
| `DIC008` | with regard to / in terms of | regarding / for / in |
| `DIC011` | the fact that | that |
| `DIC012` | plays an important role | say what it does |
| `DIC013` | is able to | can |
| `REG005` | notably, / importantly, | delete, or say why it matters |
| `REG009` | surprisingly, / interestingly, | report the fact, let the reader react |

## Nominalizations

| Rule | Instead of | Use |
|---|---|---|
| `NOM001` | perform an analysis of | analyse |
| `NOM002` | the implementation of | implementing / we implemented |
| `NOM003` | make a decision | decide |
| `NOM004` | is in agreement with | agrees with |
| `NOM005` | has the ability to | can |

Test: find the verb hidden in the noun and promote it to the predicate.

## Register to remove

- `HDG002` obviously, clearly, undoubtedly, of course, as is well known.
- `HDG005` it is important/interesting/worth noting that; it should be noted that.
- `REG001` delve into.
- `REG002` in today's rapidly evolving, ever-evolving, in the realm of, landscape of, tapestry.
- `REG003` it is worth noting that, needless to say.
- `REG004` a testament to, stands as a.
- `REG006` contractions (can't, doesn't, it's).
- `REG007` a lot of, lots of, pretty, huge, big.
- `REG008` exclamation marks.
- `REG010` I think, in my opinion.
- `HDG008` novel, first ever, unprecedented, groundbreaking — let the reader judge.

## Cohesion

- Each paragraph opens with a topic sentence that links to the previous paragraph.
- Connective vocabulary is small and consistent: however, therefore, in contrast, consequently.
  Vary only when the logical relation changes.
- `COH005` no bare "this" as a sentence subject — name the referent.
- `COH003` no "as mentioned above" — repeat the essential point.
- `COH007` no more than three sentences with identical openings.

## Typography, units and statistics

| Rule | Problem | Fix |
|---|---|---|
| `TYP001` | `5mL` | `5 mL` (non-breaking space in print) |
| `TYP002` | `uL`, `ug`, `um` | `µL`, `µg`, `µm` (U+00B5) |
| `TYP003` | `3 x 4` | `3 × 4` (U+00D7) |
| `TYP004/5` | `P<0.05`, `p<0.05` | italic, uppercase *P* |
| `TYP012` | `25° C`, `C°` | `25 °C` |
| `TYP014` | `et al` | `et al.` |
| — | Numbers at sentence start | Spell out |
| — | `1`–`9` in running text | Spell out unless a unit follows (`5 mL`) |
| — | Hyphenation | Compound modifier before a noun (`dose-dependent effect`), open after (`the effect was dose dependent`) |
| — | Ranges | En dash, no spaces (`10–20 mg`) |
| — | Dashes | Em dash unspaced for interruption; en dash for ranges |
| — | Species and gene names | Follow the nomenclature committee and the journal's italics rules; check every instance with `grep` |

## Terminology consistency

Freeze one term per concept and use it everywhere — text, figures, legends, tables, and the
abstract. Rotating synonyms reads as different concepts. Build the term list when you start editing:

| Concept | Frozen term | Rejected variants |
|---|---|---|
| the analysed collection | dataset | data set, data-set |
| the process under study | treatment | therapy, intervention, condition |
| the measured variable | wing length | wing size, wing dimension |
| the time window | exposure period | exposure duration, exposure window |

Also check: abbreviations defined once and used consistently; the same gene/protein capitalization
across text and figures; the same unit and the same number of decimal places for the same quantity.
