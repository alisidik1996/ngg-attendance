from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request

from core.auth import client_meta, require_staff
from modules.registration.schemas import AttendanceRequest, CheckInRequest
from modules.registration.services import RegistrationService

router = APIRouter(prefix="/api/registration", tags=["Registration Module"])


def _actor(request: Request, user: dict) -> dict:
    meta = client_meta(request)
    return {
        "id": user["id"],
        "username": user["username"],
        "ip": meta["ip"],
        "user_agent": meta["user_agent"],
    }


@router.get("/participant/{no_order}")
def get_participant_endpoint(no_order: str, user: dict = Depends(require_staff)):
    result = RegistrationService.getParticipant(no_order)
    return {
        "status": "success",
        "row_index": result["row_index"],
        "data": result["data"]
    }

@router.post("/check-in")
def check_in_endpoint(payload: CheckInRequest, request: Request,
                      background_tasks: BackgroundTasks, user: dict = Depends(require_staff)):
    return RegistrationService.checkParticipant(
        payload.no_order, actor=_actor(request, user), background_tasks=background_tasks
    )

@router.post("/check-in/undo")
def undo_check_in_endpoint(payload: CheckInRequest, request: Request,
                           background_tasks: BackgroundTasks, user: dict = Depends(require_staff)):
    return RegistrationService.undoCheckIn(
        payload.no_order, actor=_actor(request, user), background_tasks=background_tasks
    )

@router.post("/attendance")
def attendance_endpoint(payload: AttendanceRequest, request: Request,
                        background_tasks: BackgroundTasks, user: dict = Depends(require_staff)):
    return RegistrationService.attendParticipant(
        payload.no_order, actor=_actor(request, user), background_tasks=background_tasks
    )

@router.post("/attendance/undo")
def undo_attendance_endpoint(payload: AttendanceRequest, request: Request,
                             background_tasks: BackgroundTasks, user: dict = Depends(require_staff)):
    return RegistrationService.undoAttendance(
        payload.no_order, actor=_actor(request, user), background_tasks=background_tasks
    )

@router.get("/participants")
def get_all_participants_endpoint(user: dict = Depends(require_staff)):
    return RegistrationService.getAllParticipant()

@router.get("/search")
def search_participants_endpoint(keyword: str = Query(..., min_length=1),
                                 user: dict = Depends(require_staff)):
    return RegistrationService.searchParticipants(keyword)

@router.get("/stats")
def get_statistics_endpoint(user: dict = Depends(require_staff)):
    return RegistrationService.getStatistics()


@router.post("/sync")
def sync_from_sheets_endpoint(request: Request, user: dict = Depends(require_staff)):
    return RegistrationService.syncFromSheets(actor=_actor(request, user))
