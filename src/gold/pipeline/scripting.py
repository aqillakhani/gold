"""ScriptWriter: uses Claude API to write full video scripts."""

from __future__ import annotations

import json
import logging
import random
import re
from pathlib import Path

import anthropic
from jinja2 import Environment, FileSystemLoader

from ..config import Config
from ..utils.retry import retry

logger = logging.getLogger(__name__)

# Structure variation templates — randomized per script to avoid "templated content" flags
HOOK_STYLES = [
    "Start with a shocking statistic or number from a credible source.",
    "Start with a provocative question that creates a genuine curiosity gap.",
    "Start with a mini-story teaser — hint at the outcome without revealing it.",
    "Start with a bold controversial statement that viewers will want to argue with.",
    "Start with a 'What if...' hypothetical scenario grounded in reality.",
    "Start by addressing the viewer directly with a relatable situation they've experienced.",
    "Start mid-action — drop the viewer into the most intense moment, then rewind.",
    "Start with a short personal anecdote or confession that builds trust.",
    "Start with a comparison or contrast that surprises: 'Most people think X, but actually...'",
    "Start with a time-stamped urgency: reference a recent event or deadline.",
    "Start with a challenge to the viewer: 'Try this right now and see what happens.'",
    "Start by debunking a common myth with evidence.",
]

STRUCTURE_STYLES = [
    "Linear narrative: tell the story chronologically from start to finish.",
    "Inverted pyramid: reveal the most shocking detail first, then explain how it happened.",
    "Problem-solution: present a problem, build tension, then reveal the answer.",
    "List format: cover 3-5 key points with quick transitions between them.",
    "Mystery reveal: set up clues throughout, build to a surprising conclusion.",
    "Debate format: present two sides of an argument, then give your take.",
    "Before/after transformation: show the contrast between starting point and result.",
    "Escalating stakes: start small, each point bigger than the last, end with the biggest.",
    "Conversation style: write as if explaining to a skeptical friend over coffee.",
    "Countdown: rank items from least to most impactful, building anticipation.",
    "Case study: deep dive on ONE specific example with concrete details and numbers.",
    "Myth-busting: systematically dismantle common misconceptions with evidence.",
]

CTA_STYLES = [
    "End with a specific question that begs for comments (not generic 'what do you think').",
    "End with a cliffhanger teasing a specific follow-up topic.",
    "End with the call to action woven naturally into the final sentence of the story.",
    "End abruptly at a peak moment — no explicit CTA, let curiosity drive follows.",
    "End by asking viewers to share their own similar experience with a specific prompt.",
    "End with a surprising twist or recontextualization of everything they just heard.",
    "End with a concrete actionable step the viewer can take right now.",
    "End by revealing you left out one critical detail — follow for the rest.",
    "End with a moral or lesson learned, stated simply and directly.",
]

# Anti-AI patterns: phrases to explicitly ban from scripts
BANNED_PHRASES = [
    "in this video", "today we'll discuss", "without further ado",
    "buckle up", "let's dive in", "game-changer", "mind-blowing",
    "you won't believe", "the secret is", "here's the thing though",
    "but wait, there's more", "spoiler alert", "plot twist",
    "stay tuned", "smash that like button", "ring that bell",
]


class ScriptWriter:
    def __init__(self, config: Config):
        self.config = config
        self.client = anthropic.Anthropic(api_key=config.env("ANTHROPIC_API_KEY"))
        self.model = config.get("api.anthropic.model", "claude-sonnet-4-20250514")

        templates_dir = config.root / "templates"
        if templates_dir.exists():
            self.jinja_env = Environment(
                loader=FileSystemLoader(str(templates_dir)),
                autoescape=False,
            )
        else:
            self.jinja_env = None

    @retry(max_retries=2, base_delay=2.0, exceptions=(anthropic.APIError,))
    async def write_script(self, niche_id: str, idea: dict) -> dict:
        """Write a full video script from an idea.

        Returns dict with: hook, voiceover_script, scenes, captions (per platform), hashtags.
        """
        niche_config = self.config.niches.get(niche_id, {})
        tone = niche_config.get("tone", "engaging")
        target_duration = niche_config.get("target_duration", 40)
        has_voiceover = niche_config.get("has_voiceover", True)
        cta = niche_config.get("cta", {})
        hashtags = niche_config.get("hashtags", [])

        # Try to use a Jinja2 template if available
        prompt = self._build_prompt(niche_id, idea, niche_config)

        # Use higher token limit for long-form scripts
        target_duration = niche_config.get("target_duration", 40)
        max_tokens = 8192 if target_duration >= 300 else 4096

        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=(
                "You are a JSON-only response bot. Return ONLY valid JSON with no markdown, "
                "no code fences, no comments. Escape all double quotes inside string values "
                'with backslash (e.g. \\"like this\\"). Never use unescaped quotes in strings. '
                "For image_prompt fields, be extremely specific about composition, lighting, "
                "camera angle, color palette, and style. Each image should be visually distinct. "
                "Avoid text IN the generated image — Flux cannot render readable text. "
                "Never use vague terms like 'professional' or 'high quality' — specify exact "
                "visual elements: subject, position, background color, accent colors, style."
            ),
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text.strip()
        # Strip markdown code fences
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        # Try direct parse first, then progressively fix common LLM JSON issues
        script = self._parse_json_robust(text)

        logger.info("Script written for: %s", idea.get("title", "untitled"))
        return script

    @staticmethod
    def _parse_json_robust(text: str) -> dict:
        """Parse JSON from LLM output, handling common formatting issues.

        Handles: markdown fences, trailing commas, unescaped newlines in strings,
        unescaped inner double quotes (dialogue), single quotes, JS comments,
        and control characters.
        """
        # 1. Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 2. Extract outermost JSON object
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError(f"No JSON object found in response: {text[:200]}")

        json_text = text[start:end + 1]

        # 3. Remove control characters (except \n, \r, \t) that break JSON
        json_text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', json_text)

        # 4. Fix trailing commas before } or ]
        json_text = re.sub(r',\s*([}\]])', r'\1', json_text)

        # 5. Fix missing opening quotes in arrays/values
        # Common LLM mistake: dropping opening quote, e.g. , #hashtag" → , "#hashtag"
        json_text = re.sub(r',(\s*)(#[^"]*")', r',\1"\2', json_text)

        try:
            return json.loads(json_text)
        except json.JSONDecodeError:
            pass

        # 6. Remove JS-style comments
        json_text = re.sub(r'//[^\n]*', '', json_text)

        try:
            return json.loads(json_text)
        except json.JSONDecodeError:
            pass

        # 6. Fix unescaped quotes inside string values using a state machine.
        # This handles dialogue like: "she said "no way" and left"
        # The key insight: a closing quote for a JSON string value is ALWAYS
        # followed (after optional whitespace) by one of: , } ] or is at the
        # very end. An inner quote is followed by a letter, space+letter, etc.
        def fix_inner_quotes(s):
            result = []
            in_string = False
            expect_key_or_value = True  # Are we expecting a key or value?
            i = 0
            while i < len(s):
                c = s[i]

                # Handle escape sequences inside strings
                if in_string and c == '\\' and i + 1 < len(s):
                    result.append(c)
                    result.append(s[i + 1])
                    i += 2
                    continue

                if c == '"':
                    if not in_string:
                        in_string = True
                        result.append(c)
                        i += 1
                    else:
                        # Is this the REAL end of the string?
                        # Look ahead past whitespace for a structural character
                        j = i + 1
                        while j < len(s) and s[j] in ' \t':
                            j += 1

                        if j >= len(s):
                            # End of text — close string
                            in_string = False
                            result.append(c)
                            i += 1
                        elif s[j] in (',', '}', ']', ':'):
                            # Structural char follows — this is a real closing quote
                            in_string = False
                            result.append(c)
                            i += 1
                        elif s[j] == '\n' or s[j] == '\r':
                            # Newline follows — check if next non-whitespace line
                            # starts with a structural pattern like "key": or } or ]
                            rest_stripped = s[j:].lstrip()
                            if rest_stripped.startswith('}') or rest_stripped.startswith(']'):
                                # Closes object/array — real close
                                in_string = False
                                result.append(c)
                                i += 1
                            elif rest_stripped.startswith('"'):
                                # Could be a new key "key": or inner quote "word"
                                # Check if it matches "key": pattern (has colon after closing quote)
                                key_match = re.match(r'"[^"]*"\s*:', rest_stripped)
                                if key_match:
                                    # This is a new key — real close
                                    in_string = False
                                    result.append(c)
                                    i += 1
                                else:
                                    # Likely an inner quote
                                    result.append('\\"')
                                    i += 1
                            else:
                                # Inner quote before a newline in continued text
                                result.append('\\"')
                                i += 1
                        else:
                            # Something else follows (letter, digit, space+letter)
                            # This is an inner quote — escape it
                            result.append('\\"')
                            i += 1
                else:
                    # Fix unescaped literal newlines INSIDE strings
                    if in_string and c == '\n':
                        result.append('\\n')
                    elif in_string and c == '\r':
                        pass  # skip \r
                    elif in_string and c == '\t':
                        result.append('\\t')
                    else:
                        result.append(c)
                    i += 1

            return ''.join(result)

        try:
            fixed = fix_inner_quotes(json_text)
            fixed = re.sub(r',\s*([}\]])', r'\1', fixed)
            return json.loads(fixed)
        except json.JSONDecodeError:
            pass

        # 7. Nuclear option: try to fix with single-quote replacement too
        try:
            fixed = re.sub(r"(?<![\\])'", '"', json_text)
            fixed = fix_inner_quotes(fixed)
            fixed = re.sub(r',\s*([}\]])', r'\1', fixed)
            return json.loads(fixed)
        except json.JSONDecodeError:
            pass

        # 8. Key-boundary extraction: find string values by locating known
        # JSON keys and extracting text between them. This handles cases where
        # dialogue quotes in long strings (like voiceover_script) confuse the
        # state machine.
        try:
            return ScriptWriter._extract_by_key_boundaries(json_text)
        except (json.JSONDecodeError, ValueError):
            pass

        # 9. Last resort: log the problematic text for debugging
        logger.error(
            "All JSON parse attempts failed. Text (first 500 chars): %s",
            json_text[:500],
        )
        # One final attempt with the original extracted text
        return json.loads(json_text)

    @staticmethod
    def _extract_by_key_boundaries(json_text: str) -> dict:
        """Extract JSON fields by finding known key boundaries.

        When the state-machine quote fixer fails (e.g. voiceover dialogue like
        'she said "I quit," and left' where the comma+quote looks structural),
        this method finds each top-level string key, extracts the raw value text
        between key boundaries, escapes inner quotes, and reconstructs valid JSON.
        """
        # Known script keys (in typical order)
        known_keys = [
            "hook_text", "voiceover_script", "scenes", "captions",
            "hashtags", "thumbnail_prompt", "slide_texts", "title",
            "music_tags", "music_speed", "chapters", "shorts_hooks",
        ]

        # Find positions of all known keys in the text
        key_positions: list[tuple[int, str]] = []
        for key in known_keys:
            pattern = f'"{key}"\\s*:'
            for m in re.finditer(pattern, json_text):
                key_positions.append((m.start(), key))

        if not key_positions:
            raise ValueError("No known keys found")

        key_positions.sort(key=lambda x: x[0])

        result: dict = {}
        for idx, (pos, key) in enumerate(key_positions):
            # Find the colon after the key
            colon = json_text.index(":", pos + len(key) + 2)
            value_start = colon + 1

            # Skip whitespace
            while value_start < len(json_text) and json_text[value_start] in " \t\n\r":
                value_start += 1

            if value_start >= len(json_text):
                continue

            first_char = json_text[value_start]

            if first_char in ("[", "{"):
                # Array or object — find matching bracket
                depth = 1
                in_str = False
                j = value_start + 1
                while j < len(json_text) and depth > 0:
                    c = json_text[j]
                    if in_str:
                        if c == "\\" and j + 1 < len(json_text):
                            j += 2
                            continue
                        if c == '"':
                            in_str = False
                    else:
                        if c == '"':
                            in_str = True
                        elif c in ("[", "{"):
                            depth += 1
                        elif c in ("]", "}"):
                            depth -= 1
                    j += 1
                raw_value = json_text[value_start:j]
                try:
                    result[key] = json.loads(raw_value)
                except json.JSONDecodeError:
                    result[key] = raw_value  # store raw, better than nothing

            elif first_char == '"':
                # String value — find the end by looking for the next key boundary
                str_start = value_start + 1  # skip opening quote

                if idx + 1 < len(key_positions):
                    next_key_pos = key_positions[idx + 1][0]
                    # The string ends somewhere before the next key.
                    # Walk backwards from next_key_pos to find the closing quote
                    # Pattern: ..."  ,  "next_key":  or  ...",\n  "next_key":
                    scan = next_key_pos - 1
                    while scan > str_start and json_text[scan] in " \t\n\r,":
                        scan -= 1
                    if json_text[scan] == '"':
                        raw_str = json_text[str_start:scan]
                    else:
                        raw_str = json_text[str_start:scan + 1]
                else:
                    # Last key — find closing quote before final }
                    end_brace = json_text.rfind("}")
                    scan = end_brace - 1
                    while scan > str_start and json_text[scan] in " \t\n\r,":
                        scan -= 1
                    if json_text[scan] == '"':
                        raw_str = json_text[str_start:scan]
                    else:
                        raw_str = json_text[str_start:scan + 1]

                # Escape inner quotes and control chars
                clean = (
                    raw_str
                    .replace("\\", "\\\\")
                    .replace('"', '\\"')
                    .replace("\n", "\\n")
                    .replace("\r", "")
                    .replace("\t", "\\t")
                )
                result[key] = json.loads(f'"{clean}"')

        if not result:
            raise ValueError("No fields extracted")

        logger.info("Recovered %d fields via key-boundary extraction", len(result))
        return result

    def _build_prompt(self, niche_id: str, idea: dict, niche_config: dict) -> str:
        # Build compliance and variety addendums (applied to both Jinja and inline)
        hook_style = random.choice(HOOK_STYLES)
        structure_style = random.choice(STRUCTURE_STYLES)
        cta_style = random.choice(CTA_STYLES)

        ftc_disclosure = niche_config.get("ftc_disclosure", {})
        ftc_verbal = ftc_disclosure.get("verbal", "")

        addendums = []
        addendums.append(
            f"\nSTRUCTURE INSTRUCTIONS (follow for variety):\n"
            f"- Hook approach: {hook_style}\n"
            f"- Script structure: {structure_style}\n"
            f"- Ending approach: {cta_style}\n"
            f"Do NOT follow a formulaic intro→body→CTA template.\n\n"
            f"AUTHENTICITY RULES (critical for quality):\n"
            f"- NEVER use these overused AI phrases: {', '.join(BANNED_PHRASES[:8])}\n"
            f"- Write like a real person talking, not an AI generating content\n"
            f"- Vary sentence length dramatically: some 3 words. Some 20+ words with subclauses.\n"
            f"- Use specific details over vague claims: '$47,000' not 'a lot of money'\n"
            f"- Include 1-2 imperfections: incomplete thoughts, self-corrections, genuine reactions\n"
            f"- Every factual claim must be verifiable — no fabricated statistics or predictions"
        )
        if ftc_verbal:
            addendums.append(
                f"\nMANDATORY DISCLOSURE: The voiceover script MUST include this exact line "
                f"naturally woven into the narration (near the end): \"{ftc_verbal}\""
            )
        if niche_config.get("paraphrasing_enforcement") or niche_id == "reddit_stories":
            addendums.append(
                "\nPARAPHRASING REQUIREMENT: Rewrite the story in your own words. "
                "At least 80% of the language must be original — do NOT copy verbatim quotes. "
                "Paraphrase dialogue, change names, restructure sentences."
            )
        addendum_text = "\n".join(addendums)

        # Try Jinja2 template first
        template_path = f"{niche_id}/script_prompt.jinja2"
        if self.jinja_env:
            try:
                template = self.jinja_env.get_template(template_path)
                base_prompt = template.render(idea=idea, niche=niche_config)
                return base_prompt + "\n" + addendum_text
            except Exception:
                pass

        # Fallback to inline prompt
        tone = niche_config.get("tone", "engaging")
        target_duration = niche_config.get("target_duration", 40)
        has_voiceover = niche_config.get("has_voiceover", True)
        cta = niche_config.get("cta", {})
        hashtags = niche_config.get("hashtags", [])

        # Detect long-form mode (5+ minutes)
        is_long_form = target_duration >= 300

        if is_long_form:
            prompt = self._build_long_form_prompt(
                idea, tone, target_duration, has_voiceover, hashtags, niche_config,
            )
        else:
            prompt = self._build_short_form_prompt(
                idea, tone, target_duration, has_voiceover, hashtags,
            )

        return prompt + "\n" + addendum_text

    def _build_short_form_prompt(
        self, idea: dict, tone: str, target_duration: int,
        has_voiceover: bool, hashtags: list,
    ) -> str:
        voiceover_instruction = (
            "250-350 words. Write as NATURAL HUMAN SPEECH — not a script, not an essay. "
            "Use short punchy sentences. Mix in rhetorical questions. "
            "Add conversational fillers like 'honestly', 'look', 'here's the thing', 'and get this'. "
            "Use dashes — for dramatic pauses. Use ellipses... for suspense. "
            "Vary sentence length: some very short. Some longer and flowing. "
            "Never say 'in this video' or 'today we'll discuss' — just START the story. "
            "Write like you're telling a friend something crazy that happened."
            if has_voiceover
            else "(leave as empty string — no voiceover for this niche)"
        )

        return f"""Write a complete short-form video script.

Topic: {idea.get("title", "")}
Hook: {idea.get("hook", "")}
Angle: {idea.get("angle", "")}
Tone: {tone}
Target duration: {target_duration} seconds
Has voiceover: {has_voiceover}

IMPORTANT CONTEXT: This video uses stock footage clips from Pexels with crossfade transitions. The voiceover narration carries the story — footage illustrates it visually.

Requirements:
1. hook_text: A punchy, curiosity-driving hook displayed as a title card for the first 4 seconds. This is CRITICAL for retention — write something that makes viewers NEED to keep watching. Max 15 words. Examples: "My husband left me and regretted it terribly", "This AI tool just replaced a $50K employee", "They found the killer 40 years later — here's how"
2. voiceover_script: Full voiceover narration, {voiceover_instruction}
3. scenes: Array of 8-10 scene objects, each with:
   - search_keywords: 2-4 word search query for finding stock footage on Pexels (e.g. "bitcoin trading screen", "dark alley night", "scientist laboratory"). Be specific and visual. IMPORTANT: NEVER use search terms that would return clips with plain white, blank, or bright solid-color backgrounds. Avoid terms like "white background", "product shot", "mockup", "app interface", "phone screen". Instead prefer visually rich, dark, moody, or colorful footage — e.g. "hacker dark room" instead of "person laptop", "trading floor monitors" instead of "stock chart", "city night aerial" instead of "skyline".
   - image_prompt: Fallback — detailed prompt for an AI-generated still photograph if no stock footage found. NEVER describe white or plain backgrounds — always specify dramatic lighting, dark environments, or rich colors.
   - ken_burns: One of: zoom_in, zoom_out, pan_left, pan_right, pan_up, pan_down (vary across scenes)
   - duration: 4-7 seconds per scene
   - text_overlay: Optional on-screen text (max 8 words)
4. captions: Object with keys: youtube, tiktok, instagram, facebook — each a platform-optimized caption (100-200 chars)
5. hashtags: Array of 10 relevant hashtags (include: {", ".join(hashtags[:5])})
6. thumbnail_prompt: A detailed prompt for generating an eye-catching thumbnail image

7. music_tags: Array of 3-5 descriptive tags for searching royalty-free background music that matches THIS specific video's mood, energy, and topic. Think about what background music would play in a professional version of this video. Examples: ["electronic", "hiphop", "energetic"] for exciting tech content, ["dark", "cinematic", "suspenseful"] for true crime, ["lofi", "chill", "ambient"] for storytelling. Be specific to the video's emotional tone — not just the niche.

8. music_speed: One of "verylow", "low", "medium", "high", "veryhigh" — the tempo that best matches this video's pacing and energy level.

Return as valid JSON only. No markdown formatting, no code blocks."""

    def _build_long_form_prompt(
        self, idea: dict, tone: str, target_duration: int,
        has_voiceover: bool, hashtags: list, niche_config: dict,
    ) -> str:
        target_minutes = target_duration // 60
        word_count = f"{target_minutes * 130}-{target_minutes * 170}"  # ~150 wpm narration
        scene_count = f"{target_minutes * 2}-{target_minutes * 3}"

        return f"""Write a complete LONG-FORM documentary-style video script.

Topic: {idea.get("title", "")}
Hook: {idea.get("hook", "")}
Angle: {idea.get("angle", "")}
Tone: {tone}
Target duration: {target_minutes}-{target_minutes + 5} minutes ({target_duration} seconds)
Has voiceover: {has_voiceover}
Format: Cinematic documentary — deep dive, data-driven analysis, compelling narrative

IMPORTANT CONTEXT: This is a LONG-FORM YouTube video. It uses a mix of stock footage (Pexels) and AI-generated cinematic images. The voiceover narration is the backbone. This needs to be engaging enough to hold viewers for {target_minutes}+ minutes. Think Bloomberg, CNBC mini-docs, or Vox explainers.

Requirements:
1. hook_text: A punchy title card hook (max 15 words) that creates immediate curiosity. This appears for the first 4 seconds.

2. voiceover_script: Full narration, {word_count} words. Write as a professional narrator — authoritative but accessible.
   - Open with a dramatic hook that grabs attention in the first 10 seconds
   - Build a clear narrative arc: setup → rising tension → key insight → conclusion
   - Include specific data points, numbers, and examples
   - Use rhetorical questions to maintain engagement
   - Vary pacing: fast sections for excitement, slower for important points
   - Include natural transitions between sections
   - Write for AUDIO — it should sound great when read aloud

3. chapters: Array of 4-7 chapter objects for YouTube chapter markers, each with:
   - title: Chapter name (3-6 words, e.g. "The Hidden Pattern", "What the Data Shows")
   - approximate_timestamp: Estimated start time in "MM:SS" format
   These chapters will become YouTube description timestamps.

4. scenes: Array of {scene_count} scene objects. Each scene with:
   - search_keywords: 2-4 word Pexels search query for stock footage. IMPORTANT: NEVER use search terms that return clips with plain white, blank, or bright solid-color backgrounds. Avoid "white background", "product shot", "mockup", "app interface", "phone screen". Prefer visually rich, dark, moody, or colorful footage.
   - image_prompt: Detailed AI image prompt (cinematic, dramatic lighting, specific composition). Used when stock footage isn't available. NEVER describe white or plain backgrounds — always specify dramatic lighting, dark environments, or rich colors.
   - ken_burns: One of: zoom_in, zoom_out, pan_left, pan_right, pan_up, pan_down (vary them)
   - duration: 15-30 seconds per scene (proportional to narration coverage)
   - text_overlay: Key stat, quote, or data point (max 10 words) — not every scene needs one
   - section: Which chapter this scene belongs to (chapter title)

5. shorts_hooks: Array of 3-5 standalone highlight moments from the script, each with:
   - hook_text: A punchy hook for the Short (max 12 words)
   - voiceover_excerpt: 50-70 words extracted from the main voiceover that work as a standalone clip
   - scene_range: [start_scene_index, end_scene_index] indicating which scenes to use
   These will be extracted as YouTube Shorts / TikTok / Reels from the long-form master.

6. captions: Object with keys: youtube, tiktok, instagram, facebook — each a platform-optimized caption (youtube: 200-500 chars with chapter timestamps; others: 100-200 chars)

7. hashtags: Array of 15 relevant hashtags (include: {", ".join(hashtags[:5])})

8. thumbnail_prompt: A dramatic, cinematic thumbnail image prompt — bold subject, dark moody lighting, high contrast

9. music_tags: Array of 3-5 descriptive tags for searching royalty-free background music that matches THIS specific video's mood, energy, and topic. Examples: ["electronic", "hiphop", "energetic", "inspiring"] for bullish/exciting content, ["dark", "cinematic", "tense", "orchestral"] for serious investigative pieces, ["epic", "dramatic", "cinematic"] for sweeping market analysis. Be specific to the video's emotional arc — not just the niche.

10. music_speed: One of "verylow", "low", "medium", "high", "veryhigh" — the tempo that best matches this video's pacing.

Return as valid JSON only. No markdown formatting, no code blocks."""
