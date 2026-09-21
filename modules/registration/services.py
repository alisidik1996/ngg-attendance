from fastapi import HTTPException
from datetime import datetime
import logging
import threading
from core.config import settings
from core import sqlite_db

logger = logging.getLogger(__name__)

if settings.use_neon:
    from core import neon_db as db
else:
    from core import sqlite_db as db


def _push_checkin_async(no_order: str):
    try:
        db.push_checkin_to_gsheets(no_order)
    except Exception as e:
        logger.error(f"Background push check-in failed: {e}")


def _push_attendance_async(no_order: str):
    try:
        db.push_attendance_to_gsheets(no_order)
    except Exception as e:
        logger.error(f"Background push attendance failed: {e}")


class RegistrationService:
    @staticmethod
    def getParticipant(no_order: str):
        participant = db.get_participant_by_order(no_order)
        if not participant:
            raise HTTPException(status_code=404, detail="Peserta tidak ditemukan")
        return {"row_index": participant.get("id", 0), "data": participant}

    @staticmethod
    def checkParticipant(no_order: str):
        participant = db.get_participant_by_order(no_order)
        if not participant:
            raise HTTPException(status_code=404, detail="Peserta tidak ditemukan")

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        updated = db.update_checkin(no_order, current_time)

        if not updated:
            raise HTTPException(status_code=400, detail="Racepack sudah diambil")

        threading.Thread(target=_push_checkin_async, args=(no_order,), daemon=True).start()

        return {
            "status": "success",
            "message": "Check-in tercatat!",
            "no_order": no_order,
            "waktu_diambil": current_time
        }

    @staticmethod
    def attendParticipant(no_order: str):
        participant = db.get_participant_by_order(no_order)
        if not participant:
            raise HTTPException(status_code=404, detail="Peserta tidak ditemukan")

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        updated = db.update_attendance(no_order, current_time)

        if not updated:
            raise HTTPException(status_code=400, detail="Peserta sudah tercatat hadir!")

        threading.Thread(target=_push_attendance_async, args=(no_order,), daemon=True).start()

        return {
            "status": "success",
            "message": "Kehadiran peserta tercatat!",
            "no_order": no_order,
            "waktu_hadir": current_time
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
        data = db.search_participants(keyword)
        return {
            "status": "success",
            "keyword": keyword.lower().strip(),
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
