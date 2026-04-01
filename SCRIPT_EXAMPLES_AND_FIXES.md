# DETAILED SCRIPT EXAMPLES & SPECIFIC FIXES

This document provides concrete examples from actual scripts with recommended rewrites.

---

## EXAMPLE 1: BLOCKING ISSUE — Empty Scene Descriptions (ID 1)

### Current Script:
```
Title: My Boss Made Me Follow Every Rule... So I Did 😈
Hook: My micromanaging boss demanded I follow every single company policy
      so I maliciously complied and cost the company thousands
Script: [full story about following policies, flooding Sarah's inbox, etc.]
Scene_descriptions: []  ← EMPTY
```

### Problem:
Video editor has NO IDEA what to create. Is this animated? Live action? Voiceover with graphics?

### Solution: Add detailed scene descriptions

```json
[
  {
    "search_keywords": "office worker at desk stressed",
    "image_prompt": "Busy office environment, person at desk looking frustrated,
                     papers and computer visible, fluorescent lighting,
                     realistic documentary style",
    "ken_burns": "zoom_in",
    "duration": 4,
    "text_overlay": "My boss said 'follow EVERY policy'"
  },
  {
    "search_keywords": "employee handbook book",
    "image_prompt": "Close-up of open employee handbook, pages filled with text,
                     hands flipping through pages, office desk background,
                     dramatic lighting highlighting the handbook",
    "ken_burns": "zoom_in",
    "duration": 3,
    "text_overlay": "Turns out there's a policy that says..."
  },
  {
    "search_keywords": "email overflowing inbox",
    "image_prompt": "Computer screen showing inbox with hundreds of unread emails,
                     notification badges, stressed professional in background,
                     warm office lighting",
    "ken_burns": "pan_right",
    "duration": 5,
    "text_overlay": "60 emails a day she had to approve"
  },
  {
    "search_keywords": "person leaving office happy",
    "image_prompt": "Professional walking out of office building with satisfied
                     expression, sunlight, modern office building exterior,
                     clean and bright",
    "ken_burns": "zoom_out",
    "duration": 4,
    "text_overlay": "I got promoted to team lead"
  }
]
```

---

## EXAMPLE 2: FABRICATED CLAIMS (ID 11 - CRYPTO)

### Current Script (PROBLEMATIC):
```
"Wall Street analysts just leaked internal research that's got everyone talking.
While Bitcoin hovers around seventy thousand dollars, they're quietly positioning
for something bigger. A micro-cap altcoin trading at three cents that institutional
money is secretly accumulating. The data shows BlackRock subsidiary purchased twelve
million tokens last month through shell companies. Goldman Sachs derivatives desk
increased their exposure by four hundred percent since September."
```

### Problems:
1. **"Wall Street analysts just leaked"** — Which analysts? No source.
2. **"BlackRock subsidiary purchased... through shell companies"** — This is fabricated. No evidence.
3. **"Goldman Sachs derivatives desk increased... four hundred percent"** — Unverifiable claim.
4. Presents speculation as documented fact.

### Solution Option A: Add Speculation Framing
```
"Some Wall Street traders are speculating about a micro-cap altcoin trading at
three cents. While I've seen rumors that institutional money might be accumulating
positions, I can't verify these claims. Some online sources suggest BlackRock or
Goldman Sachs might be interested, but this is speculation based on on-chain analysis,
not confirmed data. Do your own research before investing."
```

### Solution Option B: Remove entirely and replace with verifiable claims
```
"On-chain analysis shows that whale addresses have been accumulating this token.
But before you jump in, understand that altcoin prices are highly volatile.
Look at verified metrics like trading volume and market cap before making any decisions."
```

### Better approach: Be honest about data sources
```
"According to DefiLlama's public data, this token's TVL increased 40% last month.
That suggests *something* is happening, but it could be retail interest, not
institutional money. The truth is, we can only see on-chain metrics, not who's actually
buying. Always verify claims yourself before investing."
```

---

## EXAMPLE 3: WEAK CTA / FORMULAIC ENDING (ID 1)

### Current Ending:
```
"Sometimes the best revenge is just doing exactly what you're told. What would
you do in this situation? Drop your thoughts below and follow for more workplace
drama stories."
```

### Problems:
1. Generic question that could apply to any story
2. "Drop your thoughts below" appears in multiple scripts
3. CTA doesn't create meaningful engagement
4. Viewers have already seen this pattern

### Better Endings (pick one):

**Option A: Specific question based on story details**
```
"So here's the question: Was I right to weaponize the handbook against her, or did
I cross a line? Would you have done the same thing, or handled it differently?
Comment below — and if you've had a micromanaging boss, drop your worst story."
```

**Option B: Create debate hook**
```
"But here's where opinions split: Some people say I got my revenge, others say I
damaged the team's productivity just to prove a point. Where do you stand? Should
employees have the right to maliciously comply with rules?"
```

**Option C: Invite specific stories**
```
"If you've ever been ordered to 'follow the rules,' let me know how that turned out.
I'm collecting these stories for a compilation video, so comment your best workplace
policy revenge story below."
```

---

## EXAMPLE 4: FILLER LANGUAGE (ID 10 - AI TOOLS)

### Current Script (Padded):
```
"I just watched AI write 500 lines of perfect code in 30 seconds, and I'm
questioning everything I know about software development. This coding assistant
called Cursor AI is absolutely destroying traditional development workflows.

Here's what happened when I tested it against my team of senior developers.
I gave both the AI and my team the exact same task: build a complete task
management app with user authentication, database integration, and responsive
design. My developers estimated 3 weeks. Cursor AI had a working prototype
in 45 minutes. This is insane!"
```

### Issues:
- "500 lines of perfect code" — No code is perfect. Hyperbole.
- "is absolutely destroying" — Repeated in next sentence with "Here's what happened"
- "This is insane!" — Emotional filler, no new info

### Tightened Version (20% shorter, more impact):
```
"I tested Cursor AI against my dev team. Same task: build a complete task management
app with authentication, database, and responsive design. My developers estimated
3 weeks. Cursor AI had a working prototype in 45 minutes. The code worked on first
try—no bugs, no cleanup needed."
```

**Cuts:** Repeated shock statements, vague emotional language. Keeps: Specific comparison, concrete result.

---

## EXAMPLE 5: LOGICAL INCONSISTENCY (ID 4 - REDDIT STORIES)

### Current Script (BROKEN):
```
"First, they order two hundred dollars worth of pizza from five different restaurants.
I'm talking supreme, meat lovers, Hawaiian, the works. Then they leave for a fake
weekend trip but actually hide in their car outside. Within hours, the roommate invites
over like eight friends for a massive pizza party...

The next morning, they waltz back in acting completely shocked. The roommate tries
playing dumb but here's the kicker. They'd already filed a theft report with campus
security and sent all the evidence to their parents."
```

### Problem:
**When did they file the theft report?**
- Timeline says they ordered pizza, hid in car, watched the party
- "Next morning they waltz back in"
- But they claim they "already filed" the report
- This doesn't add up. Did they file it before the party? After? When?

### Fixed Version:
```
"First, they order two hundred dollars worth of pizza. Then they leave for a fake
weekend trip but actually hide in their car outside. The roommate invites over friends
for a massive pizza party, posting stories the whole time.

Before the party even starts, our mastermind had already filed a theft report with
campus security—documenting all the previous stolen food with photos and receipts.
The next morning, they waltz back in acting shocked. When security arrives to
investigate, they have everything on camera: the roommate eating the pizza,
posting about the party, confessing to the theft."
```

**What changed:** Clarified the timeline. Filing report happens BEFORE the party, making the "trap" logical.

---

## EXAMPLE 6: GENERIC PATTERN RECOGNITION (TRUE_CRIME)

All 6 true_crime scripts follow this identical structure:

### ID 9 Structure:
1. "What if one lick could solve a three-decade-old murder?"
2. Sarah Chen, 22, found dead in 1987
3. Case went cold for years
4. New evidence (DNA from letter envelope)
5. Arrest and resolution
6. "Justice has no expiration date"

### ID 12 Structure:
1. "In 2019, investigators in Portland made a chilling discovery"
2. Three victims found in homes
3. They had Amazon reviews in common
4. Police search library computers
5. Suspect vanishes before arrest
6. "Be careful what you share online"

### ID 15 Structure:
1. "What if the key was strapped to the victim's wrist?"
2. Sarah Chen disappeared on hike
3. Case went cold for two years
4. New technology (smartwatch data)
5. Reveals details, case remains open
6. "Sometimes the smallest device holds biggest secrets"

### The Pattern:
**Setup → Cold case → Technology → Breakthrough → Lesson**

**Every. Single. Script.**

Viewers recognize this by video #2. Disengagement increases.

### Solution: Vary the structure

**ID 9 (Current format): Tech → Evidence → Arrest**
**New format: Interview-driven narrative**
```
"Detective Maria Johnson spent 20 years on unsolved cases. Then one day,
she noticed something others missed. Three cold cases, three letters to police.
But the killers made one mistake: they licked the envelopes. What happened
when she tested them? [Story unfolds from detective's perspective]"
```

**Or: Suspect-POV narrative**
```
"The killer thought he was clever. Taunting police with letters, sure they'd
never catch him. But he didn't know that DNA science was racing ahead. Here's
what he didn't count on... [Describe how technology caught up to the crime]"
```

---

## EXAMPLE 7: SMARTWATCH IMPOSSIBILITY (ID 15 - TRUE_CRIME)

### Current Script (TECHNICALLY FALSE):
```
"Sarah's smartwatch was still there, somehow protected from the elements. When
investigators powered it up, they found something incredible—GPS coordinates,
heart rate data, and activity logs from her final day.

But here's where it gets chilling. Motion sensors detected someone else moving
around her location for nearly an hour afterward."
```

### Problem:
**Smartwatches CANNOT detect "someone else moving around." They record the wearer's motion.**

The watch sensors track:
- **Heart rate** (from wearer's wrist)
- **GPS** (wearer's location)
- **Accelerometer** (wearer's movement)

They do NOT detect:
- ✗ Other people's presence
- ✗ Movement in the surrounding area
- ✗ "Motion in the vicinity"

This is technically impossible and breaks credibility.

### Fixed Version:
```
"Sarah's smartwatch was still there, somehow protected from the elements. When
investigators powered it up, they found something incredible—GPS coordinates,
heart rate data, and activity logs from her final day.

The watch recorded her final heartbeat at 4:23 PM. But investigators discovered
something more disturbing: GPS trails showed she had left the main hiking path
and followed another person's route into the ravine. Whoever led her off the trail
was someone she trusted enough to follow into unmarked wilderness."
```

**What changed:** Removed impossible motion detection. Used real smartwatch capabilities (GPS, heart rate) to tell the story.

---

## EXAMPLE 8: AFFILIATE DISCLOSURE (AI_TOOLS)

### Current Approach (Weak):
```
[Full script praising Cursor AI, specific pricing, features...]

"Some links in the description may be affiliate links. But seriously,
if you're still manually writing every line of code in 2024, you're
working ten times harder than you need to."
```

### Problem:
- Disclosure comes at END, after the sales pitch
- Buried in closing statement
- Viewers already emotionally invested in "recommendation" by then
- Looks like afterthought

### Better Approach:
```
Full Disclosure: I use Cursor AI and earn commission if you click my link.
That said, here's my honest take:

[Script continues with genuine assessment, acknowledging tradeoffs]

"I genuinely switched to Claude for development work. Here's why: [specific reasons]"
```

Or fully transparent:
```
"I tested 7 AI coding tools. Full disclosure: I have affiliate partnerships
with 3 of them, so I'm earning if you click their links. With that in mind,
here's what I actually use for my own coding: [honest recommendation]"
```

**Why it matters:** Viewers respect honesty. The affiliate relationship is fine; hiding it isn't.

---

## EXAMPLE 9: HOOK VARIATION (Multiple niches)

### Current Hooks (Repetitive):
- reddit_stories ID 1: "My micromanaging boss demanded I follow every single company policy..."
- reddit_stories ID 2: "My sister stole my wedding dress and wore it to her own wedding first"
- reddit_stories ID 3: "My mother-in-law threw away my deceased mom's precious jewelry collection..."

All follow pattern: **"My [person] [did bad thing] so I [took revenge]"**

### Better Hook Variation:

**Narrative hook (current ID 1):**
"My micromanaging boss demanded I follow every single company policy..."

**Character hook (current ID 2):**
"Who steals their sister's wedding dress? My sister did."

**Emotional hook (current ID 3):**
"Losing my mom hurt enough. Then my mother-in-law deleted what was left of her."

**Consequence hook (new approach):**
"One email created a chain reaction that cost the company thousands."

**Question hook (new approach):**
"Would you follow a rule if it meant destroying your boss?"

Each hook leads into the same story but uses different psychological triggers.

---

## SUMMARY OF FIXES BY PRIORITY

### BLOCKING (Do immediately):
1. **Fill scene descriptions for reddit_stories** (3 hours)
   - Provide visual guidance to editors
   - Use template from Example 1 above

2. **Remove fabricated claims from crypto_finance** (1-2 hours)
   - Edit ID 11, 17, 21
   - Add "alleged," "rumor," "speculation" framing
   - Or remove entirely and replace with verifiable data

3. **Verify true_crime case names and facts** (2-3 hours)
   - Research ID 9, 12, 15, 20, 23
   - Fix technically impossible claims (smartwatch motion sensor)
   - Note which are real vs. fabricated

### HIGH IMPACT (Do next week):
4. Vary closing CTAs (using Example 3 as template)
5. Reduce formula repetition in true_crime (use Example 6 approach)
6. Remove filler language (apply Example 4 tightening approach)
7. Add upfront affiliate disclosure (Example 8 approach)

---

**Total estimated remediation time: 6-8 hours**
**Expected quality improvement: 4.5/10 → 6.5-7/10**
