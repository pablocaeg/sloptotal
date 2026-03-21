import logging

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse

log = logging.getLogger("sloptotal.routes.queue")

router = APIRouter(prefix="/api/queue")


@router.get("/status")
async def api_queue_status(request: Request):
    """Returns capacity info for all endpoint queues."""
    queue_manager = request.app.state.queue_manager
    if not queue_manager:
        return {"error": "Queue not initialized"}
    return queue_manager.queue_status()


@router.get("/ticket/{ticket_id}")
async def api_queue_ticket(request: Request, ticket_id: str):
    """Poll for a queued request's result.

    Returns 200 with result if done, 202 with position if queued, 404 if expired.
    """
    queue_manager = request.app.state.queue_manager
    if not queue_manager:
        raise HTTPException(status_code=404, detail="Queue not initialized")

    status = queue_manager.get_ticket_status(ticket_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Ticket not found or expired")

    if status["status"] == "completed":
        return status["result"]
    else:
        return JSONResponse(status, status_code=202)
