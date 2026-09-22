from fastapi import APIRouter, Query
from modules.registration.schemas import CheckInRequest, AttendanceRequest
from modules.registration.services import RegistrationService

router = APIRouter(prefix="/api/registration", tags=["Registration Module"])

@router.get("/participant/{no_order}")
def get_participant_endpoint(no_order: str):
    result = RegistrationService.getParticipant(no_order)
    return {
        "status": "success",
        "row_index": result["row_index"],
        "data": result["data"]
    }

@router.post("/check-in")
def check_in_endpoint(payload: CheckInRequest):
    return RegistrationService.checkParticipant(payload.no_order)

@router.post("/check-in/undo")
def undo_check_in_endpoint(payload: CheckInRequest):
    return RegistrationService.undoCheckIn(payload.no_order)

@router.post("/attendance")
def attendance_endpoint(payload: AttendanceRequest):
    return RegistrationService.attendParticipant(payload.no_order)

@router.post("/attendance/undo")
def undo_attendance_endpoint(payload: AttendanceRequest):
    return RegistrationService.undoAttendance(payload.no_order)

@router.get("/participants")
def get_all_participants_endpoint():
    return RegistrationService.getAllParticipant()

@router.get("/search")
def search_participants_endpoint(keyword: str = Query(..., min_length=1)):
    return RegistrationService.searchParticipants(keyword)

@router.get("/stats")
def get_statistics_endpoint():
    return RegistrationService.getStatistics()
