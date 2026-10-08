# Word choice and confusable pairs

Substitutions and traps that account for most "the English needs work" referee comments.

## Overused and empty words

| Avoid | Use instead | Note |
|---|---|---|
| utilize, utilization | use | "utilize" adds no meaning |
| novel | delete | the reader judges novelty |
| significant | large / substantial | unless it means statistically significant |
| very, quite, rather, somewhat | delete or quantify | intensifiers weaken |
| clearly, obviously | delete | asserts agreement instead of earning it |
| interestingly, surprisingly | delete | let the reader react |
| importantly, notably | delete | the sentence should show importance |
| robust | precise term: repeatable across n conditions | says nothing alone |
| state-of-the-art | name the current best method | vague |
| paradigm, framework | model / hypothesis / method | unless genuinely a framework |
| leverage | use / exploit | business jargon |
| elucidate | explain / determine | often padded |
| demonstrate | show | fine in moderation; do not overuse as a hedge-neutral verb |
| shed light on | explain / identify | cliché |
| plays a key role | state the role | empty |
| a growing body of evidence | cite two or three papers | vague authority |
| it is well known | cite | unattributed consensus |
| in recent years | give the year range or cite | imprecise |
| due to the fact that | because | wordy |
| in order to | to | wordy |
| the fact that | that | wordy |
| a number of | specify | vague |
| several | give the count | vague |
| many studies | cite or count | vague |

## Confusable pairs

| Pair | Distinction |
|---|---|
| affect / effect | *affect* verb ("X affects Y"); *effect* noun ("the effect of X") |
| comprise / compose | the whole *comprises* the parts; the whole *is composed of* the parts; never "is comprised of" |
| fewer / less | *fewer* for count nouns, *less* for mass nouns |
| number / amount | *number* for count nouns, *amount* for mass nouns |
| between / among | *between* for two or specified pairs, *among* for a group |
| compared with / compared to | *compared with* for quantitative comparison, *compared to* for analogy |
| different from | not "different than"; "different to" is British and less formal |
| correlation / causation | "is associated with" for correlation; "causes" only with manipulation |
| dose / dosage | *dose* is the quantity given; *dosage* is the regimen |
| incidence / prevalence | *incidence* is new cases per time; *prevalence* is existing cases at a time |
| sensitivity / specificity | of the test; *positive predictive value* depends on prevalence |
| accuracy / precision | *accuracy* is closeness to truth; *precision* is repeatability |
| validity / reliability | *validity* measures the right thing; *reliability* measures it consistently |
| significant / substantial | statistical vs practical magnitude |
| that / which | *that* for restrictive clauses (no comma), *which* for non-restrictive (comma) |
| since / because | *since* is temporal; use *because* for causation in formal prose |
| while / whereas | *while* temporal; *whereas* contrast |
| among / amongst | use *among*; *amongst* is dated |
| data / datum | *data* plural in formal writing; *datum* singular |
| criteria / criterion | *criteria* plural; *criterion* singular |
| phenomena / phenomenon | *phenomena* plural; *phenomenon* singular |
| indices / indexes | *indices* for mathematical/statistical; *indexes* for books |
| principal / principle | *principal* main; *principle* rule |
| complementary / complimentary | *complementary* completes; *complimentary* free |
| discrete / discreet | *discrete* separate; *discreet* tactful |
| i.e. / e.g. | *i.e.* that is (restates); *e.g.* for example (illustrates); both take a following comma |
| respectively | only with a one-to-one ordered pairing; name the pairs when three or more |
| versus | spell out in running text unless in a figure label |

## Precision upgrades

| Vague | Precise |
|---|---|
| increased | give the magnitude, units and the comparison |
| improved performance | name the metric and the delta |
| a large effect | give the effect size and CI |
| correlated | give *r* or *ρ*, n, and the CI |
| no difference | report the test, the CI, and whether the design could detect an effect |
| approximately | give the tolerance, or the value with its uncertainty |
| high/low expression | give the fold change and the reference |
| normal / healthy | define the criterion |
| significant relationship | *r* = …, *P* = …, n = … |
| we observed a trend | report the statistic or say the evidence is inconclusive |

## Phrases to delete on sight

- "It is important to note that…"
- "It is worth mentioning that…"
- "In this study, we…" (say what you did)
- "As can be seen from…"
- "The reason is because…"
- "Due to the fact that…"
- "In the present study, the authors…" (you are the authors)
- "Future work will be needed to…" (state the concrete test)
- "This result is consistent with previous findings" (say which, and how)
- "The results are shown in Table 1" (state what they are)
- "A total of 12 samples were…" (*total* is redundant)

## Editing procedure

1. Search the manuscript for each word in the first table; delete or replace with a quantity.
2. Search for each confusable pair; check the direction of the distinction.
3. Replace every imprecise claim with a number, or downgrade the claim.
4. Run `scripts/academic_lint.py`; rules `DIC*`, `HDG*` and `REG*` encode most of this file.
