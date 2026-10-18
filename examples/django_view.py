"""Django view: settings.py -> RSFLOWHUB_API_KEY = env("RSFLOWHUB_API_KEY")."""

import json

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_POST

import rsflowhub
from rsflowhub import RSFlowHub

client = RSFlowHub(api_key=settings.RSFLOWHUB_API_KEY)


@require_POST
def ask_help_center(request):
    question = json.loads(request.body)["question"]
    try:
        res = client.knowledge_bases.ask(settings.HELP_CENTER_KB_ID, question=question)
    except rsflowhub.APIError as e:
        return JsonResponse({"error": e.message}, status=e.status_code)
    return JsonResponse(res.data)
