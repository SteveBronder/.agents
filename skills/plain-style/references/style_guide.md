# Style guide

Always use present tense for facts already true.

## Voice
- Write plainly and specifically. Say what we will do and how we will do it.
- Lead with the method and the result, not with adjectives about ourselves.
- Prefer "we will build X using Y, producing Z" over "our team brings deep expertise".
- Keep paragraphs short. Use numbered steps for procedures and tables for schedules or costs.
- When a sentence lists several items that each carry their own clauses, break it into a bulleted list introduced by a colon. Do not write one long sentence joined by semicolons. Short lists of single words or phrases stay in the sentence.

## Claims
- Do not write paragraphs whose purpose is to show that the writer knows the subject. Put a background fact only where it changes the content. Do not preview results the work has not produced yet. An overview section gives the reader a map of the document. It does not argue that the writer understands the topic.
- Quantify wherever possible, for example model size or the number of scenarios.

## Structure
- Group content by kind. A section describing an analysis covers the analysis. Schedules and meetings go in their own section.
- Each section should contain only what its heading describes. If a heading no longer matches what is under it (for example after cuts), fix the heading or move the content.
- Reference material, such as a table of data sources or a list of documents reviewed, goes inside the section that uses it, usually at its end. It does not open a parent section, and it does not get its own heading such as "Overall approach".
- After any revision pass, read the whole document for structure. Small local edits accumulate. Each one keeps its own paragraph correct while the overall organization drifts.
- Do not use callout boxes or icons.

## Register

Documents should read as calm and factual. They should not read as a pitch. Do not reach for the most attention-grabbing version of a sentence. A boring, accurate sentence is preferred over a punchy one. This applies to every sentence, including the first one.

The rules below describe the most common ways LLM-written prose raises the register. Readers spot these patterns easily and take them as signs of machine writing. Avoid them.

### Rule 1. Do not use the "X: Y" sentence

A sentence that sets up a subject before a colon and then delivers the payoff after it. The colon says "pause, here comes the resolution." That is a heightened, dramatic register. Write two plain sentences instead, or one sentence with an ordinary connective.

### Rule 2. Do not frame a noun as the answer to a question

Prose that writes "what happens when X" instead of "the effects of X", or "where the literature falls short" instead of "gaps in the literature". Other examples are "what this buys you" for "benefits" and "what rides along" for "side effects". There is almost always an existing plain noun for the thing. Use it. The question-framing is a device for grabbing attention and is one of the most recognizable marks of machine writing.

### Rule 3. Do not use lists of three unless they are required

Lists of three are ruled out unless every item must be named. This applies to short in-sentence lists as much as long ones. One example is "with no server, database, or user accounts". Another is a paragraph that paired "Python, an open-source programming language", "Stan, an open-source statistical modeling language", and "HTML and JavaScript". Name one or two things, or say what the thing is in a sentence.

Machine-written prose reaches for a three-item list by instinct, in nearly every paragraph, because three items have a satisfying rhythm. Watch for that instinct. When a list of three is unavoidable, do not mechanically split it into "X and Y. Also Z." That is worse than the list.

### Rule 4. Do not use candor as a selling device

Sentences that comment on their own frankness, or that turn a limitation into a selling point. "We say so directly." This is a sales move dressed as honesty. State limitations and qualifications as plain facts, then stop.

### Rule 5. Be wary of giving people's verbs to things

Machine-written prose often gives an abstract thing an action verb that belongs to a person. Examples include "the data tell us", "the model wants", "the report argues", and "the interviews will test". The effect is a slightly punchy, animated register. Prefer a plain, neutral verb such as "the data show" or "the report presents". This is a caution. Some of these phrasings are ordinary usage and fine in moderation ("the table shows", "the contract requires"). Watch for them when several appear close together, or when the verb makes the thing sound like it has intentions.

### Rule 6. Never use the "X, Y-ed" tagline

A noun phrase followed by a comma and a clipped participle that delivers a small payoff. "They share one set of public data sources, listed in Section 2.2." "French cooking, demystified." "Comfort, redefined." Another example from a draft is "The baseline, against which the other scenarios are compared." It became "The baseline against which the other scenarios are compared." The comma adds nothing and makes the sentence less grammatical. It is there only for punch. This is the register of ad copy and book subtitles, and it is banned outright. Write a plain sentence instead, such as "The data sources are listed in Section 2.2."

Ordinary participle clauses that carry information are fine ("Cells too small to report reliably will be combined or flagged"). The banned form is the tacked-on flourish after a comma.

### Rule 7. Do not pitch

Do not explain to the reader why our design is clever, and do not answer a question they have not asked. "The work is descriptive and comes first, so that the reader sees the population before the model is built on the same data" is a pitch because it sells the sequencing. Say what the work is and how it connects, and stop. "This portion of the project is purely descriptive. It helps contextualize the population trends which are used in the scenario model in later tasks." Watch especially for "so that" and "which means" clauses that justify a choice. Readers familiar with AI writing notice this quickly.

### Rule 8. Less polish is fine

Slick, fully connected prose reads as machine-written. Short plain sentences, even slightly choppy ones, are better than smooth savvy ones. Do not merge short sentences to improve flow, and do not polish a co-author's plain sentences. Example: "The Summary Analysis Report will be written in plain, professional language, with the Data Visualizations integrated into the text, each with a short narrative." became "The Summary Analysis Report will be written in plain, professional language. Data Visualizations integrated into the text."

### Rule 9. Do not write in a know-it-all voice

Do not show off specialist knowledge the reader does not need, such as statute sections or named thresholds. It reads as an AI that knows everything. Each specific detail is also a claim that can turn out to be wrong. Describe the approach at the level of "the programs' statutory rules (like income limits)" and stop.

Example: a paragraph covered the SSI earned-income disregard, the SSDI substantial gainful activity threshold, the trial work period, 93 months of Medicare, section 1619(b), calibration targets, and each Nevada tax base. It became "Program participation effects will be based on the programs' statutory rules (like income limits) as well as observed patterns of program take-up among households in different economic situations. Tax effects will work similarly."

### Rule 10. Explain central methods in plain words

When a method is central, give the reader a sentence of background instead of a dense summary.

Before:

> The model will represent Nevada's population as a large sample of individual people and households, change the employment status of some of those people, and add up the resulting changes in earnings, program participation, and tax revenue.

After:

> Microsimulation is a modeling approach where a researcher starts with a baseline projection of a population with detailed characteristics, then changes some of those characteristics and simulates the downstream effects of those changes. In this case, the model will represent Nevada's population as a large sample of individual people and households. It will then simulate how household-level indicators like earnings and taxes change when the employment status of some of those people changes.

Also avoid tidy enumerations that restate a point in parallel short sentences ("Households gain earnings... Public budgets are affected... The Nevada economy is affected..."). One plain sentence is enough.

### Rule 11. Never use contrastive negation

Banned outright: "It is an X, not a Y." "It's not Y, it's X." "Not just X, but Y." "X rather than Y" when used to set up a contrast for effect. It is one of the most recognizable marks of machine writing. Say what the thing is and stop. If a scope exclusion matters, state the boundary directly. Example: "It is a document review, not an audit of VR's information technology systems, and requires no site visits." became "This portion does not require site visits."

### Rule 12. Hedge lists of contents

When listing what a document or output will contain, introduce the list with "items like the following" or "such as" unless every item is required. This shows the kind of thing planned without binding the writer to each item. Keep each item short and general, and do not stack several specifics into one item. Example: "Labor market outcomes: labor force participation, employment, hours, earnings, occupation, and industry." became "Labor market outcomes, such as employment rates, hours worked, earnings, and industry/occupation."

### Rule 13. Use the working vocabulary of your field

Prose that has been flattened into generic plain English also reads as machine-written. AI-text detectors such as Pangram flag it even after the other style passes. Put back the ordinary working vocabulary of the field. These are the words a researcher uses without thinking about them. Examples from economics include "counterfactual employment scenarios", "socio-economic trends", "the public-use microdata sample", "disaggregated analysis", "demographic cuts", "downstream effects", "knock-on effects", "scenario deltas, i.e., projected changes relative to the baseline scenario", and "developed in concert with".

This is different from the consultant jargon banned elsewhere in this guide ("sits inside", "gates", "cadence", "size" as a verb). Consultant jargon replaces an ordinary word to sound sharp. Field vocabulary is the ordinary word for a researcher in that field. Use it where it fits, and explain it once if a general reader might not know it.

Before and after:

- "an Employment Impact Model that runs scenarios developed with the agency" became "an Employment Impact Model that runs counterfactual employment scenarios developed in concert with the agency".
- "The report will be built from the American Community Survey" became "The report will be based principally on the public-use microdata sample of the American Community Survey".
- "enough for cuts by disability type, age group, and region" became "generally sufficient for disaggregated analysis by demographic cuts like disability type or age".
- "For each of the other scenarios, the Model Output Summary will report results relative to the baseline, such as:" became "For non-baseline scenarios, the Model Output Summary will report \"scenario deltas\", i.e., projected changes relative to the baseline scenario. These projected effects will include metrics like:"

### Rule 14. Qualify claims the way a careful researcher does

Add small, honest qualifiers where a draft states an empirical expectation flatly. Examples include "based principally on", "generally sufficient", "Possible/example calculations", and "how employment patterns among residents with disabilities differ, if at all, from those at the national level". A researcher does not know the result before doing the work and writes that way. This is different from hedging a whole sentence into vagueness. Keep the commitment (the output or the data source) firm and qualify the empirical expectation.

Rule 9 applies here as well. Cut details such as a list of survey years or the length of a projection period. Cut closing sentences that summarize how the pieces of a list connect, such as "The descriptive report comes first. The model then produces...". Summary sentences that restate the structure of a list the reader just read are a strong machine-writing signal.

### Rule 15. Do not hang a clause off a noun and point back at it

This pattern is a noun, then a short clause with a verb modifying it, then a pronoun ("it", "them") that points back to something earlier in the sentence. It usually arrives after a comma as a punchy closing "and" clause. It is common on machine-written websites, as in "your workplace and the customers that drive it". Example from a draft: "System dynamics is a modeling approach that represents a region as a set of quantities that build up or run down over time, called stocks, and the rates that change them, called flows." The trouble is "and the rates that change them". Say the thing directly in a sentence built some other way.

The short form "X and its Y" counts too. "Calibrated system dynamics model and its documentation" should be "Calibrated system dynamics model, with documentation". The "its" adds nothing but punch. Other examples include "with its source", "its results", "document its assumptions", and "its registration is active". Use "its", "their", or "them" only when the sentence cannot do without it.

### Rule 16. Use fewer commas and let sentences wander a little

Machine prose chops a sentence into short comma-separated pieces such as appositives ("called stocks") and tacked-on clauses. Write some longer sentences that unfold through subordinate clauses and arrive at their point. Vary the shapes so that two paragraphs are rarely built the same way. The aim is a structurally stranger sentence with the same substance. Do not make the vocabulary ornate or the writing harder to follow. The register stays calm and professional.

Lean only slightly toward longer sentences. Split a sentence that runs past about 40 words, as long as the pieces do not become clipped fragments.

### Rule 17. Negate the verb, not the noun

Do not use "no" in front of a noun as the negation ("would incur no software license costs", "no test touches it", "No sidecar rides along", "requires no site visits", "with no server"). Machine prose uses this construction constantly. It reads as odd. Negate the verb in the ordinary way. "The NEK Collaborative would not incur any software license costs." "The simulator does not need a server." The same goes for "little" and "nothing" used the same way ("has little to secure").

### Rule 18. Avoid the "X, and Y" sentence with a punchy second half, and avoid figurative verbs

A sentence states a fact, then adds ", and" plus a short second clause that lands like a payoff. Machine prose does this constantly. It often comes with a figurative verb where a plain one exists ("carries through", "enters the work", "drives", "rides along", "flows into").

Before: "Bayesian calibration produces a range of plausible values for each parameter, and that uncertainty carries through to the ranges of outcomes shown in the simulator."

After: "Bayesian calibration produces a range of plausible values for each parameter. This uncertainty leads to us showing a range of outcomes in the simulator."

When writing, check each sentence for punch. If it is punchy, rewrite it.

The same goes for ", so ..." endings that sell a benefit. "Results are reported year by year, so the effects of a change in one part of the region on the others can be traced over the following years." fails four ways:

- a ", so" payoff clause
- a figurative verb ("traced")
- a back-reference ("the others")
- a repeat ("year by year" and "over the following years")

It also explains why the design is good instead of saying what it does. It was cut.

### Rule 19. Do not write "an X for every Y"

Do not write "a source and note for every value", "a fixed price for every task", or "a record for every change". The "for every" (or emphatic "for each") makes a completeness claim with a flourish. Say it plainly, as in "with sources and notes" or "the price of each task is fixed". This rule also catches lists of three in descriptions of outputs. "Calibrated, documented system dynamics model, with a record of structure, data sources, and assumptions" became "Calibrated system dynamics model, with documentation".

## Commitments and detail

- **Cut detail the reader does not need.** Explain enough for the reader to trust the method. Example: "A person who answers yes to any of them is counted as having a disability" was cut from a description of the American Community Survey.
- **Do not spell out what is already implied.** "The model's code as a documented project, with instructions that let staff rerun the scenarios after the project ends" became "the model's code as a documented project".
- **Do not explain the reason for a procedural step.** Say what is being done and stop.
- **Cut orientation sentences that add nothing.** A section heading followed directly by its subsections is fine. "Sections 2.1 to 2.4 describe the four analytical tasks" was deleted.

### Before and after examples

**Before**

> The Bureau of Vocational Rehabilitation (VR) wants to know what happens when more Nevada residents with disabilities work: to the households involved, to the public programs that support them, and to the Nevada economy.

**After**

> The Bureau of Vocational Rehabilitation (VR) is seeking estimates of the economic and budgetary effects of increased employment among the disabled population of Nevada.

What was wrong. The before sentence breaks three rules at once. It is an "X: Y" sentence (Rule 1). It writes "what happens when" instead of "the effects of" (Rule 2). It closes with a list of three (Rule 3). The first item, "the households involved", is a subset of the budgetary and economic effects, so the list pads two things out to three. The after sentence says the same thing in one plain clause using the ordinary noun "effects". If distributional effects on households need mentioning, they go in a short follow-up sentence.

**Before**

> VR sits inside the Department of Employment, Training and Rehabilitation (DETR)...

**After**

> VR is part of the Department of Employment, Training and Rehabilitation (DETR)...

What was wrong. "Sits inside" is snappy jargon standing in for an ordinary verb. Use the plain verb.

**Before**

> We will build one microsimulation model of Nevada's population and use it for every quantitative deliverable, from the population profile to the ten-year baseline projection.

**After**

> The core analytical tool underlying each of the quantitative deliverables will be a custom-built microsimulation model of Nevada's population.

What was wrong. The "from the X to the Y" range construction is advertising copy. It sweeps the reader across a span for effect. The after sentence names the tool and its role. It is also calmer because its subject is the tool instead of "we".

**Before**

> For each scenario the Model Output Summary will report, as an illustrative list: additional Nevada residents...

**After**

> For each scenario, the Model Output Summary will report metrics like the following: additional Nevada residents...

What was wrong. "As an illustrative list" is an awkward interjected qualifier. "Metrics like the following" says the same thing in ordinary words and sits naturally before a list colon.

**Before**

> We will present these as indicative estimates and state their assumptions: fixed spending patterns, no price or wage response, and no displacement of existing workers.

**After**

> (deleted)

What was wrong. This is a point about substance, but the instinct behind it is a style instinct. The sentence lists methodological caveats in advance to appear careful. A description of planned work does not need to itemize the assumptions of a multiplier calculation. That material belongs in the analysis itself. Do not pad a document with caveats to signal rigor.

## Other patterns to avoid

- **Snappy jargon verbs and phrases** where an ordinary word exists. "Sits inside" for "is part of". "Gates" for "blocks". "Cadence" for "schedule". "Rides along" for "accompanies". Do not use "size" as a verb ("we will size this scenario"). Say "the magnitude of this scenario will be based on".
- **The "from the X to the Y" range.** This is advertising copy. Name the things or the role directly instead.
- **Pre-emptive caveat lists.** Listing assumptions or limitations to signal rigor. Save them for the analysis itself unless the reader asks for them.

## Punctuation

- **Use the Oxford comma.** In a list of three or more items, put a comma before the final "and" or "or", as in "SSI, SSDI, and Medicaid". The exception is an official name whose owner writes it without one, such as the Nevada "Department of Employment, Training and Rehabilitation". Copy official names exactly.
- **Do not use semicolons.** This includes tables and headings. Split the sentence or use a conjunction.
- **Use only ASCII characters.** This includes code blocks and front matter. Use straight quotes, "-" for a hyphen or a range, "..." for an ellipsis, and "->" for an arrow. Rewrite a sentence that needs an em dash, using a comma, parentheses, or two sentences. Do not use emoji.
