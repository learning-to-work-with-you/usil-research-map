# Research context: User-Specific Interaction Learning (USIL)

<!-- Edit this file as the position paper evolves. Changing it invalidates only the
     mapping and verification caches (stage 2-3); extracted evidence is reused. -->

## Position
Agent interaction policies are currently designed and evaluated for an average user. For persistent
AI agents, the individual user should be a unit of learning and evaluation for *how an agent works*
(when to ask, act, confirm, explain, defer, or return control), not only for *what it produces*.

## Definition
User-Specific Interaction Learning (USIL) studies how interactive AI systems learn from
user-specific evidence (edits, corrections, approvals/rejections, takeovers, interruptions,
answers to questions, demonstrations, interaction history) to adapt how they communicate, elicit
input, collaborate, respond to feedback, and exercise autonomy across contexts and over time.
Central object: a user-conditioned interaction policy pi_u(a_t | s_t, h_t^u), where h_t^u is the
user-specific history, s_t the current task/interaction context, and a_t an interaction or task action.
A user representation z_u = g(h) is optional (conceptual decomposition, not required architecture).

## The 2x2 framing
Rows: OUTCOME (what is produced) vs PROCEDURE (how the work is done: asking, confirming, autonomy, communication).
Columns: AVERAGED across users vs INDIVIDUAL user.
- outcome_averaged: standard RLHF / preference learning / task-success benchmarks
- outcome_individual: personalized reward models, user summaries, personalized generation
- procedure_averaged: mixed-initiative principles, clarification/asking policies, confirmation scheduling, levels of autonomy, learned for a population
- procedure_individual: USIL — learning per-user interaction policies

## Research pillars
- P1 Learning from sparse and evolving user evidence (few-shot user adaptation, online/continual adaptation, drift vs. noise)
- P2 Representing and generalizing user-specific interaction preferences (profiles, memory, latent models, procedural preferences, cross-task transfer)
- P3 Learning when to infer, ask, act, or defer (clarification, value of information, adaptive autonomy, deference, confirmation, return of control)
- P4 Evaluating USIL (benchmarks and metrics for personalized, longitudinal human-agent interaction beyond task success)

## Literature-map categories
User modeling & personalization; Memory & procedural learning; Preference & reward learning;
Continual / online learning; Mixed-initiative & autonomy; Human–AI collaboration;
Active elicitation & feedback; Agent evaluation & benchmarks.

## Field definitions (use exactly these meanings)
- what_is_learned: output preference | user model | interaction preference | interaction policy | reward model | memory | other
- per_user: yes = the method/analysis is personalized to an individual user; partial = conditioned on groups, personas, or user features but not individually learned; no = population-level
- across_sessions: yes = adapts or persists over time or across sessions
- interaction_decisions: which agent decisions are actually affected (ask, clarify, act, confirm, suggest, explain, defer, intervene, return_control, none)
- evaluates_transfer: yes = evaluates generalization to new tasks, contexts, or users
- Use "not established" when the paper does not establish something; never assume a capability is absent.
