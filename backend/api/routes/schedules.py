"""Scheduling endpoints."""

from fastapi import APIRouter, HTTPException
from api.deps import SessionDep, UserDep
from repositories.radio import RadioRepository
from scheduler.service import station_scheduler
from schemas.radio import ScheduleCreate, ScheduleOut
from services.radio import RadioService

router = APIRouter(prefix="/schedules", tags=["scheduler"])


@router.get("", response_model=list[ScheduleOut])
async def list_schedules(session: SessionDep, _: UserDep) -> list[ScheduleOut]:
    """List programmed events."""
    return list(await RadioRepository(session).list_schedules())


@router.post("", response_model=ScheduleOut, status_code=201)
async def create_schedule(payload: ScheduleCreate, session: SessionDep, user: UserDep) -> ScheduleOut:
    """Persist and register a time-bound event."""
    if payload.event_type == "playlist" and payload.playlist_id is None:
        raise HTTPException(status_code=422, detail="Playlist schedules require playlist_id")
    if payload.playlist_id and not await RadioRepository(session).get_playlist(payload.playlist_id):
        raise HTTPException(status_code=404, detail="Playlist not found")
    schedule = await RadioService(session).schedule(payload)
    if payload.event_type == "playlist" and payload.playlist_id:
        station_scheduler.register_playlist(schedule.id, payload.playlist_id, payload.run_at)
    await RadioService(session).log("scheduler", f"Scheduled {schedule.name}", user.email, {"schedule_id": schedule.id})
    return schedule


@router.delete("/{schedule_id}", status_code=204)
async def delete_schedule(schedule_id: int, session: SessionDep, user: UserDep) -> None:
    """Delete a scheduled event."""
    repository = RadioRepository(session)
    schedule = await repository.get_schedule(schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule event not found")
    name = schedule.name
    await repository.delete_schedule(schedule)
    await RadioService(session).log("scheduler", f"Deleted schedule {name}", user.email, {"schedule_id": schedule_id})

