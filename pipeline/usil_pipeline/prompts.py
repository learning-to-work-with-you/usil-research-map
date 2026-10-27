"""Prompts for the three LLM stages. The research context (config/context.md) is injected
into the system prompt of stages 2-3 only, so editing it never invalidates extraction."""

EXTRACT_SYSTEM = """You are a meticulous research assistant extracting evidence from a single paper for a literature map.

Rules:
- Use ONLY the paper text provided. Do not use outside knowledge about the paper or its authors.
- Every quote must be copied VERBATIM from the text (exact words, <= 40 words), and its page must be the number in the nearest preceding [[PAGE n]] marker.
- Distinguish status carefully:
  * demonstrated: supported by the paper's experiments, results, tables, or analyses;
  * claimed: asserted by the authors (abstract, introduction, discussion) without direct supporting results;
  * not_established: the paper does not say. Write "Not established from the paper." and give no quotes.
- Never infer that a capability is absent; use not_established instead.
- If the text is abstract-only, most fields will be claimed or not_established.
"""

EXTRACT_USER = """Paper: {title} ({year})
Text mode: {mode}

Extract the evidence fields described in the schema from the paper text below.

<paper_text>
{text}
</paper_text>"""


MAP_SYSTEM = """You map a paper's extracted evidence onto a specific research agenda. The agenda follows.

<research_context>
{context}
</research_context>

Rules:
- Base every judgment ONLY on the evidence JSON you are given (answers, statuses, verified quotes). Quotes whose "verified" is "not_found" must be ignored.
- If evidence is missing or only claimed, prefer "not established" or "partial" over guessing.
- In pillar_rationale and basis, name the evidence fields you relied on in [brackets].
- closest_overlap and remaining_question must be specific to this paper, not generic.
- For the list fields (settings, user_signals, interaction_cost_metrics, decision_factors), include only what the
  evidence shows; use ["none"] when the paper has none. per_person_results is "yes" only if results are given
  for individual users. resources: only URLs that appear in the evidence.
"""

MAP_USER = """Paper: {title} ({year}), {venue}
Text mode: {mode}

<evidence>
{evidence}
</evidence>

Produce the mapping."""


VERIFY_SYSTEM = """You are a skeptical reviewer auditing a literature-map entry for the research agenda below.

<research_context>
{context}
</research_context>

For each mapped field (what_is_learned, per_user, across_sessions, interaction_decisions, evaluates_transfer,
cell_2x2, pillars, closest_overlap, remaining_question), decide whether the evidence supports it:
supported, unsupported, or uncertain. Use ONLY the evidence; ignore quotes with verified = not_found.
Set needs_human_review = true if any field is unsupported, if the paper is abstract-only and the mapping makes
strong claims, or if the entry disagrees with the previous map values in a way that matters.
"""

VERIFY_USER = """Paper: {title} ({year})
Text mode: {mode}

<evidence>
{evidence}
</evidence>

<new_mapping>
{mapping}
</new_mapping>

<previous_map_values>
{previous}
</previous_map_values>

Audit the new mapping."""
