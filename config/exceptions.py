from rest_framework.views import exception_handler


def custom_exception_handler(exc, context):
    """Normalize all DRF error responses to {"error": "..."} format."""
    response = exception_handler(exc, context)
    if response is not None and "detail" in response.data:
        response.data = {"error": str(response.data["detail"])}
    return response
