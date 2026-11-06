"""Missions (Loop 32): an agent's longer job in the background.

  GET  /missions?agent=&limit=     the recent missions (of one agent), active first, and what they cost this month
  GET  /missions/limits?agent=     the ceiling and model a new mission of this agent gets (its own, else the global)
  POST /missions/{id}/again        the same goal with the same agent, as a new mission
  GET  /missions/{id}              one mission: plan, feed, findings, question, draft, cost
  POST /missions                   {agent, goal, max_cost?, max_minutes?}: start one
  POST /missions/{id}/answer       {answer: text or [choices]}: the mission resumes
  POST /missions/{id}/revise       {changes}: the mission works again on its draft
  POST /missions/{id}/approve      the draft becomes items in the Brain (one undo)
  POST /missions/{id}/stop         stop it (what it found is kept)
  GET/PUT /missions/settings       default ceiling {max_cost, max_minutes}
"""
from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from engine import database, missions
from engine.paths import Layout


class StartIn(BaseModel):
    agent: str = Field(default="archivist", max_length=40)
    goal: str = Field(min_length=4, max_length=2000)
    max_cost: float | None = Field(default=None, gt=0, le=20)
    max_minutes: float | None = Field(default=None, gt=0, le=240)
    mentions: list[str] = Field(default_factory=list, max_length=8)  # Brain items pinned with @ (Loop 38)


class AnswerIn(BaseModel):
    answer: str | list[str]


class ReviseIn(BaseModel):
    changes: str = Field(min_length=1, max_length=4000)


class SettingsIn(BaseModel):
    max_cost: float | None = Field(default=None, gt=0, le=20)
    max_minutes: float | None = Field(default=None, gt=0, le=240)


def make_router(layout: Layout, auth: Callable[..., None]) -> APIRouter:
    r = APIRouter(prefix="/missions", dependencies=[Depends(auth)])

    def run(fn: Callable[..., Any], *args: Any) -> Any:
        try:
            with database.session(layout.database) as conn:
                out = fn(conn, *args)
                if isinstance(out, dict) and "id" in out and "goal" in out:
                    return missions.get(conn, out["id"])
                return out
        except missions.MissionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @r.get("/settings")
    def get_settings() -> dict[str, Any]:
        return run(missions.settings)

    @r.put("/settings")
    def put_settings(body: SettingsIn) -> dict[str, Any]:
        def go(conn):
            s = missions.settings(conn)
            s.update({k: v for k, v in body.model_dump().items() if v is not None})
            database.set_setting(conn, "missions", s)
            return s
        return run(go)

    @r.get("")
    def listing(agent: str | None = Query(default=None, max_length=40), limit: int = Query(20, ge=1, le=100)) -> dict[str, Any]:
        return {"missions": run(missions.listing, limit, agent), "summary": run(missions.summary)}

    @r.get("/limits")
    def limits(agent: str | None = Query(default=None, max_length=40)) -> dict[str, Any]:
        return run(missions.limits, agent)

    @r.post("/{mission_id}/again")
    def again(mission_id: str) -> dict[str, Any]:
        return run(missions.again, mission_id)

    @r.get("/{mission_id}")
    def one(mission_id: str) -> dict[str, Any]:
        return run(missions.get, mission_id)

    @r.post("")
    def start(body: StartIn) -> dict[str, Any]:
        return run(missions.start, body.agent, body.goal, body.max_cost, body.max_minutes, body.mentions)

    @r.post("/{mission_id}/answer")
    def answer(mission_id: str, body: AnswerIn) -> dict[str, Any]:
        return run(missions.answer, mission_id, body.answer)

    @r.post("/{mission_id}/revise")
    def revise(mission_id: str, body: ReviseIn) -> dict[str, Any]:
        return run(missions.revise, mission_id, body.changes)

    @r.post("/{mission_id}/approve")
    def approve(mission_id: str) -> dict[str, Any]:
        return run(missions.approve, mission_id)

    @r.post("/{mission_id}/stop")
    def stop(mission_id: str) -> dict[str, Any]:
        return run(missions.stop, mission_id)

    return r
