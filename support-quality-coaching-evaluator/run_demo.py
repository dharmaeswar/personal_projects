"""End-to-end demo: retrieve, grade, coach, simulate, evaluate."""

from support_quality import (
    CASES, check_dataset, RuleBasedJudge, KnowledgeRetriever,
    build_coaching_plan, SimulationSession, compare_prompts,
)


def main():
    problems = check_dataset()
    print(f"Dataset check: {'OK' if not problems else problems}")

    # 1. Natural-language search over the help-center KB.
    retriever = KnowledgeRetriever()
    print("\n-- Agent search: 'when will my refund arrive' --")
    for hit in retriever.retrieve("when will my refund arrive", k=2):
        print(f"  [{hit.article_id}] {hit.title} (score {hit.score})")
        print(f"    {hit.snippet}")

    # 2. LLM-as-judge quality evaluation of three cases.
    judge = RuleBasedJudge("v1")
    print("\n-- Quality evaluation (judge v1) --")
    for case in CASES[:3]:
        result = judge.grade(case)
        human = sum(case.human_labels.values())
        print(f"  {case.case_id}: judge {result.overall:.2f}/2.00 "
              f"({'PASS' if result.passed else 'FAIL'}), "
              f"human labels sum {human}/10")
        for key, score in result.scores.items():
            print(f"    {key}: {score} — {result.evidence[key]}")

    # 3. AI coaching plan from the weakest case's evidence.
    worst = min((judge.grade(c) for c in CASES), key=lambda r: r.overall)
    plan = build_coaching_plan(worst)
    print(f"\n-- Coaching plan for {plan.case_id} --")
    print(f"  {plan.summary}")
    print(f"  Strengths: {', '.join(plan.strengths) or 'none'}")
    for drill in plan.drills:
        print(f"  Drill [{drill['criterion']}, score {drill['score']}]: "
              f"{drill['drill']} — {drill['exercise']}")
        print(f"    Read: {drill['kb_article']} | Practise: "
              f"{drill['practice_scenario']}")

    # 4. Simulation: trainee practises the unsafe-stay scenario.
    session = SimulationSession("sim-unsafe-stay")
    session.reply("I'm really sorry you're dealing with this — your safety "
                  "comes first. I've escalated this to our safety team right "
                  "now and I can help you rebook somewhere safe tonight.")
    report = session.finish()
    print(f"\n-- Simulation '{report.title}' --")
    print(f"  Mean turn score: {report.mean_overall:.2f}/2.00")
    print(f"  {report.coaching_plan.summary}")

    # 5. Offline evaluation + prompt A/B + release gate.
    print("\n-- Offline evaluation vs human labels + prompt A/B --")
    for row in compare_prompts():
        print(f"  Judge {row.prompt_version}: agreement {row.agreement:.3f}, "
              f"MAE {row.mean_abs_error:.3f}, pass/fail agreement "
              f"{row.overall_agreement:.3f}, gate "
              f"{'PASS' if row.gate_passed else 'FAIL'} "
              f"({row.n_cases} cases)")
    print("\nDemo complete.")


if __name__ == "__main__":
    main()
