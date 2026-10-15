from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from . import runner
from .llm import clean_transcript, llm_configured
from .nutritionix import NutritionixClient, NutritionixError


def _ctx(**extra):
    client = NutritionixClient()
    return {"nx_configured": client.configured, "llm_configured": llm_configured(), **extra}


def dashboard(request):
    return render(request, "poc/dashboard.html", _ctx(results=runner.load_latest()))


@require_POST
def run_all(request):
    runner.run_all()
    return redirect("dashboard")


def download_csv(request):
    path = runner.RESULTS_DIR / "results_sheet.csv"
    if not path.exists():
        raise Http404("Run the checks first")
    return FileResponse(path.open("rb"), as_attachment=True, filename="nutritionix_poc_results.csv")


def natural(request):
    ctx = _ctx(query=request.POST.get("query", ""), page="natural")
    if request.method == "POST" and ctx["query"]:
        try:
            foods, ms = NutritionixClient().natural_nutrients(ctx["query"])
            ctx.update(foods=[runner.summarize_food(f) for f in foods], ms=round(ms))
        except NutritionixError as e:
            ctx["error"] = str(e)
    return render(request, "poc/natural.html", ctx)


def search(request):
    ctx = _ctx(query=request.GET.get("q", ""), page="search")
    if ctx["query"]:
        try:
            common, branded, ms = NutritionixClient().search_instant(ctx["query"])
            ctx.update(common=common[:5], branded=branded[:5], ms=round(ms))
        except NutritionixError as e:
            ctx["error"] = str(e)
    return render(request, "poc/search.html", ctx)


def barcode(request):
    ctx = _ctx(upc=request.GET.get("upc", "").strip(), page="barcode")
    if ctx["upc"]:
        try:
            food, ms = NutritionixClient().search_upc(ctx["upc"])
            ctx.update(food=food, ms=round(ms), searched=True)
        except NutritionixError as e:
            ctx["error"] = str(e)
    return render(request, "poc/barcode.html", ctx)


def voice(request):
    ctx = _ctx(transcript=request.POST.get("transcript", ""), page="voice")
    if request.method == "POST" and ctx["transcript"]:
        client = NutritionixClient()
        try:
            raw_foods, _ = client.natural_nutrients(ctx["transcript"])
            ctx["raw_foods"] = [runner.summarize_food(f) for f in raw_foods]
            if ctx["llm_configured"]:
                ctx["cleaned"] = clean_transcript(ctx["transcript"])
                clean_foods, _ = client.natural_nutrients(ctx["cleaned"])
                ctx["clean_foods"] = [runner.summarize_food(f) for f in clean_foods]
        except Exception as e:  # noqa: BLE001 — show API/LLM errors on the page
            ctx["error"] = str(e)
    return render(request, "poc/voice.html", ctx)
