from django.core.management.base import BaseCommand

from poc import runner


class Command(BaseCommand):
    help = "Run all Nutritionix POC checks and write poc/results/latest.json + results_sheet.csv"

    def handle(self, *args, **options):
        out = runner.run_all()
        for r in out["summary"]:
            self.stdout.write(f"{r['status']:5}  {r['check']}: {r['value']} {r['unit']}  (bar {r['bar']})")
        for e in out["errors"]:
            self.stderr.write(f"error: {e}")
