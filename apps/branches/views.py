from django.http import JsonResponse
from django.views.decorators.http import require_GET

from .models import Branch


@require_GET
def branch_list(request):
    branches = list(
        Branch.objects.filter(is_active=True).values('id', 'name', 'location')
    )
    return JsonResponse({'branches': branches})
