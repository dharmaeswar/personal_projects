"""End-to-end demo: review a sample change with a hardcoded secret in it.

Run from the project root:  python run_demo.py
"""

from changereview.cli import analyze
from changereview.report import to_markdown

SAMPLE_DIFF = """diff --git a/src/payments/charge.py b/src/payments/charge.py
--- a/src/payments/charge.py
+++ b/src/payments/charge.py
@@ -1,4 +1,7 @@
 def charge(amount, card):
+    # TODO: retry on timeout
+    api_key = "sk-live-1234567890"
+    query = "select * from charges where id = '" + card + "'"
     return process(amount, card)
"""

COVERAGE = {"src/payments/charge.py": {1, 4}}
OWNERS = {"src/payments/": ["payments-team", "priya"]}


def main() -> None:
    review = analyze(SAMPLE_DIFF, coverage=COVERAGE, owners=OWNERS)
    print(to_markdown(review))


if __name__ == "__main__":
    main()
