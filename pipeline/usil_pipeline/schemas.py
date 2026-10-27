"""Pydantic schemas for structured outputs (sent to Claude via messages.parse)."""
from typing import List, Literal, Optional
from pydantic import BaseModel, Field

Status = Literal["demonstrated", "claimed", "not_established"]
Tri = Literal["yes", "partial", "no", "not established"]
YesNo = Literal["yes", "no", "not established"]
Decision = Literal["ask", "clarify", "act", "confirm", "suggest", "explain", "defer",
                   "intervene", "return_control", "none"]
Pillar = Literal["P1", "P2", "P3", "P4"]
Cell = Literal["outcome_averaged", "outcome_individual", "procedure_averaged",
               "procedure_individual", "mixed"]
Learned = Literal["output preference", "user model", "interaction preference", "interaction policy",
                  "reward model", "memory", "other"]
PaperType = Literal["method", "benchmark, dataset, or environment", "user study", "survey or position", "theory", "system or framework"]
Setting = Literal["coding agent", "web or GUI agent", "chat assistant", "embodied robot", "decision support", "recommendation",
                  "education", "health", "productivity or office", "other"]
Signal = Literal["edits or corrections", "approvals or rejections", "takeovers or interventions", "answers to questions",
                 "ratings or comparisons", "stated preferences or profile", "implicit behavior or history", "persona or demographics", "none"]
Representation = Literal["natural-language profile or memory", "latent vector", "per-user parameters", "reward or preference model",
                         "rules or permissions", "belief distribution", "none", "not established"]
Unit = Literal["individual user", "group or persona", "repository or project", "population", "not established"]
EvalUsers = Literal["real users", "simulated users", "both", "no user evaluation", "not established"]
CostMetric = Literal["questions asked", "interruptions", "user effort or time", "trust", "satisfaction or preference", "workload", "none"]
Factor = Literal["stakes", "reversibility", "uncertainty", "authorization or permission", "user expertise", "workload or interruptibility", "none"]


# ---------------- Stage 1: evidence extraction ----------------
class Quote(BaseModel):
    quote: str = Field(description="Verbatim span copied exactly from the paper text (<= 40 words).")
    page: Optional[int] = Field(description="Page number from the [[PAGE n]] marker preceding the quote, or null.")
    section: str = Field(description="Section heading the quote appears under, or '' if unknown.")


class EvidenceField(BaseModel):
    answer: str = Field(description="Concise answer in your own words (1-3 sentences). 'Not established from the paper' if absent.")
    status: Status = Field(description="demonstrated = shown in results/experiments; claimed = stated by authors (abstract/intro/discussion) without direct evidence; not_established = paper does not say.")
    quotes: List[Quote] = Field(description="1-3 supporting verbatim quotes; empty list if not_established.")


class Evidence(BaseModel):
    research_question: EvidenceField
    claimed_contribution: EvidenceField
    what_is_learned: EvidenceField
    user_evidence: EvidenceField
    personalization: EvidenceField = Field(description="Is the method/analysis personalized to an individual user, a group/persona, or the population?")
    temporal_adaptation: EvidenceField = Field(description="Does it adapt over time or across sessions?")
    interaction_decisions: EvidenceField = Field(description="Which interaction decisions (ask, act, confirm, explain, defer, intervene, return control) are actually affected?")
    transfer: EvidenceField = Field(description="Does it evaluate transfer to new tasks, contexts, or users?")
    metrics_and_baselines: EvidenceField
    key_results: EvidenceField
    limitations: EvidenceField
    user_signals: EvidenceField = Field(description="Which signals from individual users it learns from or conditions on: edits, corrections, approvals or rejections, takeovers, answers to questions, ratings, stated preferences, interaction history, persona or demographics.")
    user_representation: EvidenceField = Field(description="How what is learned about a user is represented: natural-language profile or memory, latent vector, per-user parameters, reward model, rules or permissions, belief distribution.")
    evaluation_setup: EvidenceField = Field(description="Who the users in the evaluation are (real people, LLM-simulated personas, scripted users), how many, over how many sessions or how long, and whether results are reported per person.")
    decision_context: EvidenceField = Field(description="Which contextual factors drive interaction decisions: stakes, reversibility, uncertainty, authorization or permission, user expertise, workload or interruptibility.")
    interaction_costs: EvidenceField = Field(description="Whether it measures the burden on the user: number of questions, interruptions, effort or time, trust, satisfaction, workload.")
    resources: EvidenceField = Field(description="Released code, data, or benchmarks, with the links given in the paper.")


# ---------------- Stage 2: mapping to the research agenda ----------------
class Mapping(BaseModel):
    what_is_learned: Learned
    what_is_learned_detail: str
    per_user: Tri
    across_sessions: YesNo
    interaction_decisions: List[Decision]
    evaluates_transfer: YesNo
    cell_2x2: Cell
    pillars: List[Pillar]
    pillar_rationale: str = Field(description="One sentence per pillar, citing evidence field names in brackets, e.g. [personalization].")
    category: str = Field(description="One of the literature-map categories from the context.")
    closest_overlap: str = Field(description="Closest overlap with USIL, grounded in the evidence.")
    remaining_question: str = Field(description="A specific open question this paper leaves for USIL.")
    paper_type: PaperType
    settings: List[Setting]
    user_signals: List[Signal]
    user_representation: Representation
    preference_change: Literal["assumes fixed preferences", "handles drift or change", "not established"]
    personalization_unit: Unit
    evaluation_users: EvalUsers
    evaluation_scale: str = Field(description="Who and how much, e.g. '24 participants over 2 weeks' or '1,000 LLM-simulated personas'; '' if no user evaluation.")
    per_person_results: YesNo = Field(description="Are results reported for each user (not only averaged)?")
    interaction_cost_metrics: List[CostMetric]
    decision_factors: List[Factor]
    resources: List[str] = Field(description="URLs of released code, data, or benchmarks given in the evidence; empty if none.")
    summary_100w: str = Field(description="~100-word summary for the research map.")
    basis: str = Field(description="Which evidence fields (by name) support per_user, across_sessions, interaction_decisions and evaluates_transfer.")


# ---------------- Stage 3: verification ----------------
class Check(BaseModel):
    field: str
    verdict: Literal["supported", "unsupported", "uncertain"]
    note: str


class Verification(BaseModel):
    checks: List[Check]
    overall_confidence: Literal["high", "medium", "low"]
    needs_human_review: bool
    review_reason: str
