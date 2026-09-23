import logging
from datetime import datetime

from fastapi import HTTPException

from core.config import settings
from core.db import db

logger = logging.getLogger(__name__)


def _push_status(push_fn, no_order: str, background_tasks=None) -> str:
    if background_tasks is None or settings.is_vercel:
        try:
            return "ok" if push_fn(no_order) else "failed"
        except Exception as e:
            logger.error("GSheets push failed for %s: %s", no_order, e)
            return "failed"
    background_tasks.add_task(push_fn, no_order)
    return "queued"


class RegistrationService:
    @staticmethod
    def getParticipant(no_order: str):
        participant = db.get_participant_by_order(no_order)
        if not participant:
            raise HTTPException(status_code=404, detail="Peserta tidak ditemukan")
        return {"row_index": participant.get("id", 0), "data": participant}

    @staticmethod
    def checkParticipant(no_order: str, actor: dict = None, background_tasks=None):
        actor = actor or {}
        participant = db.get_participant_by_order(no_order)
        if not participant:
            raise HTTPException(status_code=404, detail="Peserta tidak ditemukan")

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        updated = db.update_checkin(
            no_order, current_time,
            actor_id=actor.get("id"),
            actor_username=actor.get("username", ""),
            ip=actor.get("ip", ""),
            user_agent=actor.get("user_agent", ""),
        )

        if not updated:
            raise HTTPException(status_code=400, detail="Racepack sudah diambil")

        sync = _push_status(db.push_checkin_to_gsheets, no_order, background_tasks)

        return {
            "status": "success",
            "message": "Check-in tercatat!",
            "no_order": no_order,
            "waktu_diambil": current_time,
            "gsheets_sync": sync,
        }

    @staticmethod
    def attendParticipant(no_order: str, actor: dict = None, background_tasks=None):
        actor = actor or {}
        participant = db.get_participant_by_order(no_order)
        if not participant:
            raise HTTPException(status_code=404, detail="Peserta tidak ditemukan")

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        updated = db.update_attendance(
            no_order, current_time,
            actor_id=actor.get("id"),
            actor_username=actor.get("username", ""),
            ip=actor.get("ip", ""),
            user_agent=actor.get("user_agent", ""),
        )

        if not updated:
            raise HTTPException(status_code=400, detail="Peserta sudah tercatat hadir!")

        sync = _push_status(db.push_attendance_to_gsheets, no_order, background_tasks)

        return {
            "status": "success",
            "message": "Kehadiran peserta tercatat!",
            "no_order": no_order,
            "waktu_hadir": current_time,
            "gsheets_sync": sync,
        }

    @staticmethod
    def undoCheckIn(no_order: str, actor: dict = None, background_tasks=None):
        actor = actor or {}
        participant = db.get_participant_by_order(no_order)
        if not participant:
            raise HTTPException(status_code=404, detail="Peserta tidak ditemukan")

        cleared = db.clear_checkin(
            no_order,
            actor_id=actor.get("id"),
            actor_username=actor.get("username", ""),
            ip=actor.get("ip", ""),
            user_agent=actor.get("user_agent", ""),
        )
        if not cleared:
            raise HTTPException(status_code=400, detail="Racepack belum diambil")

        sync = _push_status(db.push_checkin_to_gsheets, no_order, background_tasks)

        return {
            "status": "success",
            "message": "Ambil race pack dibatalkan!",
            "no_order": no_order,
            "gsheets_sync": sync,
        }

    @staticmethod
    def undoAttendance(no_order: str, actor: dict = None, background_tasks=None):
        actor = actor or {}
        participant = db.get_participant_by_order(no_order)
        if not participant:
            raise HTTPException(status_code=404, detail="Peserta tidak ditemukan")

        cleared = db.clear_attendance(
            no_order,
            actor_id=actor.get("id"),
            actor_username=actor.get("username", ""),
            ip=actor.get("ip", ""),
            user_agent=actor.get("user_agent", ""),
        )
        if not cleared:
            raise HTTPException(status_code=400, detail="Peserta belum tercatat hadir")

        sync = _push_status(db.push_attendance_to_gsheets, no_order, background_tasks)

        return {
            "status": "success",
            "message": "Status hadir dibatalkan!",
            "no_order": no_order,
            "gsheets_sync": sync,
        }

    @staticmethod
    def getAllParticipant():
        data = db.get_all_participants()
        return {
            "status": "success",
            "total": len(data),
            "data": data
        }

    @staticmethod
    def searchParticipants(keyword: str):
        keyword = keyword.strip()
        if not keyword:
            raise HTTPException(status_code=422, detail="Keyword tidak boleh kosong")
        data = db.search_participants(keyword)
        return {
            "status": "success",
            "keyword": keyword.lower(),
            "total_found": len(data),
            "data": data
        }

    @staticmethod
    def getStatistics():
        stats = db.get_statistics()
        return {
            "status": "success",
            "statistics": stats
        }
