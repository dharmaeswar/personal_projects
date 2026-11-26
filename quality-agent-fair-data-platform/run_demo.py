"""Demo: run one agentic Quality investigation end to end."""

from quality_platform.pipeline import run

if __name__ == "__main__":
    report = run()
    print("Question:", report["question"])
    print("Answer:", report["answer"])
    print(f"Investigation passed validation: {report['investigation_passed']}")
    print(f"Tool calls: {report['tool_calls']}")
    print(f"Evals: {report['evals_passed']}/{report['evals_total']} passed "
          f"(pass rate {report['eval_pass_rate']})")
    print(f"Monitor alert: {report['monitor_alert']} {report['monitor_reasons']}")
