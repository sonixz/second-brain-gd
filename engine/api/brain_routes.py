"""Second brain HTTP routes. All require the local token."""
from __future__ import annotations

from typing import Any, Callable, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field

from engine import brain, database
from engine.brain import meaning, structure
from engine.assistant.llm import make_client
from engine.voice import secrets
from engine.paths import Layout


class SpaceIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: Literal["project", "area", "resource", "archive"] = "project"
    color: str | None = Field(default=None, max_length=16)
    icon: str | None = Field(default=None, max_length=32)


class NoteIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    body: str = Field(default="", max_length=200_000)
    space_id: str | None = None
    kind: Literal["note", "idea", "task", "journal", "reference"] = "note"
    source: Literal["typed", "voice", "import", "agent"] = "typed"


class SpacePatch(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    kind: Literal["project", "area", "resource", "archive"] | None = None
    color: str | None = Field(default=None, max_length=16)
    goal: str | None = Field(default=None, max_length=2000)
    why: str | None = Field(default=None, max_length=2000)
    due_date: str | None = Field(default=None, max_length=10)
    status: Literal["active", "waiting", "someday", "done"] | None = None
    area_id: str | None = None
    instructions: str | None = Field(default=None, max_length=4000)


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    area_id: str | None = None
    goal: str | None = Field(default=None, max_length=2000)
    due_date: str | None = Field(default=None, max_length=10)
    color: str | None = Field(default=None, max_length=16)


class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    space_id: str | None = None
    due_date: str | None = Field(default=None, max_length=10)


class TaskPatch(BaseModel):
    done: bool | None = None
    due_date: str | None = Field(default=None, max_length=10)
    clear_due: bool = False


class ChecklistIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    space_id: str | None = None


class ItemsIn(BaseModel):
    items: list[str] = Field(min_length=1, max_length=100)


class ItemPatch(BaseModel):
    done: bool | None = None
    text: str | None = Field(default=None, max_length=200)


class ContextIn(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    space_id: str | None = None
    kind: Literal["project", "area", "resource"] = "project"


class FolderIn(BaseModel):
    path: str = Field(min_length=1, max_length=1000)  # a folder of notes on this PC (Loop 39)
    keep_folders: bool = True                           # folders become places; False: everything to the Inbox


class NotePatch(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    body: str | None = Field(default=None, max_length=200_000)
    space_id: str | None = None
    kind: Literal["note", "idea", "task", "journal", "reference"] | None = None
    status: Literal["active", "done", "archived"] | None = None
    pinned: bool | None = None
    due_date: str | None = Field(default=None, max_length=10)


class TypeIn(BaseModel):
    name_en: str = Field(default="", max_length=60)
    name_fr: str = Field(default="", max_length=60)
    fields: list[dict[str, Any]] = Field(default_factory=list, max_length=30)
    id: str | None = Field(default=None, max_length=40)
    created_by: str | None = Field(default=None, max_length=60)


class ViewIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    type: str = Field(default="", max_length=40)
    query: str = Field(default="", max_length=200)
    sort: str = Field(default="", max_length=40)
    desc: bool = False


class GroceryIn(BaseModel):
    picks: list[dict[str, Any]] = Field(min_length=1, max_length=40)  # [{id, servings?}]
    save: bool = False


class PointIn(BaseModel):
    name: str = Field(default="", max_length=80)


class RewindIn(BaseModel):
    action_id: int | None = None
    point_id: str | None = Field(default=None, max_length=20)
    author: str = Field(default="", max_length=80)


class ExportIn(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=60)
    format: Literal["pdf", "html"] = "pdf"
    title: str = Field(default="", max_length=120)
    servings: dict[str, float] = Field(default_factory=dict)  # recipe id -> servings to print


class PropsIn(BaseModel):
    type: str = Field(min_length=1, max_length=40)
    props: dict[str, Any] = Field(default_factory=dict)
    rewrite: bool = True


def make_router(layout: Layout, auth: Callable[..., None]) -> APIRouter:
    r = APIRouter(prefix="/brain", dependencies=[Depends(auth)])

    def run(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        try:
            with database.session(layout.database) as conn:
                return fn(conn, *args, **kwargs)
        except brain.NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @r.get("/briefing")
    def get_briefing() -> dict[str, Any]:
        return run(brain.briefing)

    @r.get("/graph")
    def get_graph() -> dict[str, Any]:
        return run(brain.graph)

    @r.get("/spaces")
    def get_spaces() -> dict[str, Any]:
        return {"spaces": run(brain.list_spaces)}

    @r.post("/spaces", status_code=201)
    def post_space(body: SpaceIn) -> dict[str, Any]:
        return run(brain.create_space, body.name, body.kind, body.color, body.icon)

    @r.get("/notes")
    def get_notes(space_id: str | None = None, limit: int = Query(200, ge=1, le=1000)) -> dict[str, Any]:
        return {"notes": run(brain.list_notes, space_id, limit)}

    @r.post("/notes", status_code=201)
    def post_note(body: NoteIn) -> dict[str, Any]:
        return run(brain.create_note, body.title, body.body, body.space_id, body.kind, body.source)

    @r.get("/notes/{note_id}")
    def get_note(note_id: str) -> dict[str, Any]:
        return run(brain.get_note, note_id)

    @r.patch("/notes/{note_id}")
    def patch_note(note_id: str, body: NotePatch) -> dict[str, Any]:
        return run(brain.update_note, note_id, **body.model_dump(exclude_none=True))

    @r.delete("/notes/{note_id}", status_code=204, response_class=Response)
    def del_note(note_id: str) -> Response:
        run(brain.delete_note, note_id)
        return Response(status_code=204)

    def client_or_none():
        key, _ = secrets.get(layout, "openai")
        try:
            return make_client(key)
        except PermissionError:
            return None

    @r.get("/search")
    def get_search(q: str = Query(min_length=1, max_length=200), limit: int = Query(30, ge=1, le=200)) -> dict[str, Any]:
        return {"results": run(meaning.search_notes, client_or_none(), q, limit)}

    @r.post("/import/scan")
    def post_import_scan(body: FolderIn) -> dict[str, Any]:
        """The preview of a folder import: what was detected, what would come in, the cost."""
        from engine.sources import folder_import
        return run(folder_import.scan, body.path, body.keep_folders)

    @r.post("/import/run")
    def post_import_run(body: FolderIn) -> dict[str, Any]:
        from engine.sources import folder_import
        return run(folder_import.run, body.path, body.keep_folders)

    @r.post("/import/stop")
    def post_import_stop() -> dict[str, Any]:
        """« Stop » in the preview: the scan or import under way ends at its next file; nothing of it stays."""
        from engine.sources import folder_import
        folder_import.stop()
        return {"stopping": True}

    @r.get("/mention")
    def get_mention(q: str = Query("", max_length=200), limit: int = Query(8, ge=1, le=20)) -> dict[str, Any]:
        """The « @ » picker: items by title as you type (no model call)."""
        from engine.brain import mentions
        return {"items": run(mentions.suggest, q, limit)}

    @r.get("/path")
    def get_path(a: str = Query(alias="from", min_length=1, max_length=300), b: str = Query(alias="to", min_length=1, max_length=300)) -> dict[str, Any]:
        from engine.brain import connect

        def go(conn):
            ia, ib = connect.resolve(conn, a, client_or_none()), connect.resolve(conn, b, client_or_none())
            if not ia or not ib:
                raise brain.NotFound("item")
            return connect.path(conn, ia, ib)
        return run(go)

    @r.post("/related/{a}/{b}/{choice}")
    def post_related(a: str, b: str, choice: Literal["keep", "dismiss"]) -> dict[str, Any]:
        from engine.brain import connect
        return run(connect.choose_related, a, b, "kept" if choice == "keep" else "dismissed")

    @r.get("/feed")
    def get_feed(limit: int = Query(50, ge=1, le=500)) -> dict[str, Any]:
        from engine.brain import archivist
        return {"items": run(archivist.feed, limit)}

    @r.get("/table")
    def get_table(type: str = Query("", max_length=40), place: str = Query("", max_length=64),
                  q: str = Query("", max_length=200)) -> dict[str, Any]:
        """The table view (Loop 37C): rows of one type with its fields as columns, or every item."""
        from engine.assistant.core import ui_language
        from engine.brain import table

        def go(conn):
            return {**table.rows(conn, type, place, q, ui_language(conn)), "views": table.views(conn)}
        return run(go)

    @r.post("/table/views")
    def post_view(body: ViewIn) -> dict[str, Any]:
        from engine.brain import table
        return {"views": run(table.save_view, body.name, body.type, body.query, body.sort, body.desc)}

    @r.delete("/table/views/{name}")
    def delete_view(name: str) -> dict[str, Any]:
        from engine.brain import table
        return {"views": run(table.delete_view, name)}

    @r.post("/grocery")
    def post_grocery(body: GroceryIn) -> dict[str, Any]:
        """The grocery list from ticked recipes: added up, by aisle; save=true keeps it (note + « Épicerie »)."""
        from engine.assistant.core import ui_language
        from engine.brain import table

        def go(conn):
            fn = table.save_grocery if body.save else table.grocery
            return fn(conn, body.picks, ui_language(conn))
        return run(go)

    @r.get("/timeline")
    def get_timeline(author: str = Query("", max_length=80), limit: int = Query(200, ge=1, le=1000)) -> dict[str, Any]:
        """The timeline of changes (Loop MCP-B2): actions and restore points, newest first, and who made them."""
        from engine.brain import timeline

        def go(conn):
            return {"entries": timeline.entries(conn, author, limit), "authors": timeline.authors(conn)}
        return run(go)

    @r.post("/timeline/points")
    def post_point(body: PointIn) -> dict[str, Any]:
        from engine.brain import timeline
        return run(timeline.create_point, body.name or "Point de retour")

    @r.post("/timeline/rewind")
    def post_rewind(body: RewindIn) -> dict[str, Any]:
        """Go back to a moment: every action after it undone (for everyone or one author); conflicts are listed."""
        from engine.brain import timeline
        if body.point_id:
            return run(timeline.rewind_to_point, body.point_id, body.author)
        if body.action_id is None:
            raise HTTPException(status_code=422, detail="a point_id or an action_id")
        return run(timeline.rewind, body.action_id, body.author)

    @r.post("/export")
    def post_export(body: ExportIn) -> dict[str, Any]:
        """Items on paper (Loop 37D): a Letter HTML page, and a PDF printed by Edge headless when asked."""
        from engine.assistant.core import ui_language
        from engine.brain import export_doc

        def go(conn):
            return export_doc.export(conn, body.ids, body.format, body.title, ui_language(conn), body.servings)
        return run(go)

    @r.get("/types")
    def get_types() -> dict[str, Any]:
        """Item types (Loop 37B): the recipe, and the ones agents defined, with their fields and counts."""
        from engine.brain import types
        return {"types": run(types.list_types)}

    @r.post("/types")
    def post_type(body: TypeIn) -> dict[str, Any]:
        from engine.brain import types
        return run(types.define_type, body.name_en, body.name_fr, body.fields, body.created_by or "user", body.id)

    @r.post("/items/{note_id}/props")
    def post_props(note_id: str, body: PropsIn) -> dict[str, Any]:
        """Sets an item's fields (merged with the ones it has; an empty value clears one); its text follows."""
        from engine.brain import types

        def go(conn):
            brain.get_note(conn, note_id)
            return types.set_props(conn, note_id, body.type, body.props, merge=True, rewrite_body=body.rewrite)
        return run(go)

    @r.get("/items/{note_id}")
    def get_item(note_id: str) -> dict[str, Any]:
        from engine.brain import archivist
        return run(archivist.item, note_id, True)

    @r.get("/context")
    def get_context() -> dict[str, Any]:
        from engine.brain import archivist
        return {"context": run(archivist.get_context)}

    @r.put("/context")
    def put_context(body: ContextIn) -> dict[str, Any]:
        from engine.brain import archivist
        return {"context": run(archivist.set_context, body.name, body.space_id, body.kind)}

    @r.get("/notes/{note_id}/related")
    def get_related(note_id: str) -> dict[str, Any]:
        run(brain.get_note, note_id)  # 404 for an unknown note
        return {"related": run(meaning.related, note_id)}

    @r.get("/meaning/status")
    def get_meaning_status() -> dict[str, Any]:
        from engine.sources.core import embeddings_model

        def st(conn):
            return {**meaning.status(conn, embeddings_model(conn)), "model": embeddings_model(conn),
                    "embeddings": database.get_setting(conn, "embeddings_status") or {"available": None}}
        return run(st)

    # ---------------------------------------------------------- structure
    @r.get("/structure")
    def get_structure() -> dict[str, Any]:
        return run(structure.structure)

    @r.get("/today")
    def get_today() -> dict[str, Any]:
        return run(structure.today)

    @r.get("/spaces/{space_id}/card")
    def get_card(space_id: str) -> dict[str, Any]:
        return run(structure.card, space_id)

    @r.delete("/spaces/{space_id}")
    def delete_space(space_id: str) -> dict[str, Any]:
        """Removes a place: its items go back to the Inbox. Journalled, so the toast's Undo restores it."""
        from engine.assistant.core import _journal

        def go(conn):
            out = brain.remove_space(conn, space_id)
            out["action_id"] = _journal(conn, "remove_place", space_id, {"note_ids": out["moved_to_inbox"],
                                        "children": out["children"]}, {"name": out["removed"]}, f"place {out['removed']} retirée")
            return out
        return run(go)

    @r.patch("/spaces/{space_id}")
    def patch_space(space_id: str, body: SpacePatch) -> dict[str, Any]:
        return run(structure.update_space, space_id, **body.model_dump(exclude_none=True))

    @r.post("/projects", status_code=201)
    def post_project(body: ProjectIn) -> dict[str, Any]:
        return run(structure.create_project, body.name, body.area_id, body.goal, body.due_date, body.color)

    @r.get("/tasks")
    def get_tasks(space_id: str | None = None, include_done: bool = False) -> dict[str, Any]:
        return {"tasks": run(structure.tasks, space_id, include_done)}

    @r.post("/tasks", status_code=201)
    def post_task(body: TaskIn) -> dict[str, Any]:
        return run(structure.add_task, body.title, body.space_id, body.due_date)

    @r.patch("/tasks/{note_id}")
    def patch_task(note_id: str, body: TaskPatch) -> dict[str, Any]:
        due: Any = None if body.clear_due else (body.due_date if body.due_date is not None else "__keep__")
        return run(structure.set_task, note_id, body.done, due)

    @r.get("/checklists")
    def get_checklists() -> dict[str, Any]:
        return {"checklists": run(structure.list_checklists)}

    @r.post("/checklists", status_code=201)
    def post_checklist(body: ChecklistIn) -> dict[str, Any]:
        return run(structure.create_checklist, body.name, body.space_id)

    @r.post("/checklists/{checklist_id}/items")
    def post_items(checklist_id: str, body: ItemsIn) -> dict[str, Any]:
        return run(structure.add_items, checklist_id, body.items)

    @r.patch("/checklist-items/{item_id}")
    def patch_item(item_id: int, body: ItemPatch) -> dict[str, Any]:
        return run(structure.set_item, item_id, body.done, body.text)

    @r.delete("/checklist-items/{item_id}", status_code=204, response_class=Response)
    def del_item(item_id: int) -> Response:
        run(structure.delete_item, item_id)
        return Response(status_code=204)

    @r.post("/checklists/{checklist_id}/clear")
    def post_clear(checklist_id: str) -> dict[str, Any]:
        return run(structure.clear_done, checklist_id)

    return r
