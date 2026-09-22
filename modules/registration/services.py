from fastapi import HTTPException
from datetime import datetime
import logging
from core.config import settings

logger = logging.getLogger(__name__)

if settings.use_neon:
    from core import neon_db as db
else:
    from core import sqlite_db as db


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

        sync_ok = False
        try:
            sync_ok = db.push_checkin_to_gsheets(no_order)
        except Exception as e:
            logger.error(f"GSheets push check-in failed for {no_order}: {e}")

        return {
            "status": "success",
            "message": "Check-in tercatat!",
            "no_order": no_order,
            "waktu_diambil": current_time,
            "gsheets_sync": "ok" if sync_ok else "failed",
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

        sync_ok = False
        try:
            sync_ok = db.push_attendance_to_gsheets(no_order)
        except Exception as e:
            logger.error(f"GSheets push attendance failed for {no_order}: {e}")

        return {
            "status": "success",
            "message": "Kehadiran peserta tercatat!",
            "no_order": no_order,
            "waktu_hadir": current_time,
            "gsheets_sync": "ok" if sync_ok else "failed",
        }

    @staticmethod
    def undoCheckIn(no_order: str):
        participant = db.get_participant_by_order(no_order)
        if not participant:
            raise HTTPException(status_code=404, detail="Peserta tidak ditemukan")

        cleared = db.clear_checkin(no_order)
        if not cleared:
            raise HTTPException(status_code=400, detail="Racepack belum diambil")

        sync_ok = False
        try:
            sync_ok = db.push_checkin_to_gsheets(no_order)
        except Exception as e:
            logger.error(f"GSheets push undo check-in failed for {no_order}: {e}")

        return {
            "status": "success",
            "message": "Ambil race pack dibatalkan!",
            "no_order": no_order,
            "gsheets_sync": "ok" if sync_ok else "failed",
        }

    @staticmethod
    def undoAttendance(no_order: str):
        participant = db.get_participant_by_order(no_order)
        if not participant:
            raise HTTPException(status_code=404, detail="Peserta tidak ditemukan")

        cleared = db.clear_attendance(no_order)
        if not cleared:
            raise HTTPException(status_code=400, detail="Peserta belum tercatat hadir")

        sync_ok = False
        try:
            sync_ok = db.push_attendance_to_gsheets(no_order)
        except Exception as e:
            logger.error(f"GSheets push undo attendance failed for {no_order}: {e}")

        return {
            "status": "success",
            "message": "Status hadir dibatalkan!",
            "no_order": no_order,
            "gsheets_sync": "ok" if sync_ok else "failed",
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
