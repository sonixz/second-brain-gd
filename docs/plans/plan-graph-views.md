# Plan — richer views in the graph (loops VIEW-A to VIEW-G)

**Status: started.** Written on 2026-11-10 after a brainstorm with the owner, who said the same day « commence par
VIEW-A et enchaine ». The loops are built in the suggested order; the 3D loops (F, G) wait for the owner's answers
to the open questions at the end.

The owner's words (2026-11-10): « Les vues possibles dans la vue graph, filtrer, chronologie, c'est une vue.
J'aime bien la vue chronologie. Est-ce qu'on pourrait avoir des vues plus avancées, plus étendues, plus
mouvables, peut-être même une en 3D ? Comment on pourrait enrichir vraiment les vues dans le graph ? »

## Where the graph stands today

- One hand-drawn 2D `Control`: `scenes/brain/graph_view.gd` (about 1,650 lines). Force layout on a worker thread,
  one zone per place, semantic zoom (points → circles → cards → readable text), a minimap.
- Two layouts, chosen by `set_layout(mode)`: `"zones"` and `"timeline"` (Loop 15: items slide onto a time axis,
  one lane per place). The Timeline button lives in the filter bar (`scenes/brain/graph_filters.gd`).
- Filters: type, origin, date (today, 7 days, 30 days), a word or theme, packs.
- The engine already holds a meaning vector per item and « related » links (`engine/brain/meaning.py`).
- The project renders with **GL Compatibility**. 3D works there (MultiMesh, glow, simple fog), without the heavy
  Forward+ effects (global illumination, volumetric fog).

## The principle

A **view** = a layout (where items sit) + a filter (which items show) + a camera (where you look). Today these
three are wired by hand for two cases. The plan makes « view » a first-class thing, so each new view is a small
addition and the graph can glide from one to the next.

## The loops

Sizes: S = about one session, M = two or three, L = a week of sessions or more.

### VIEW-A — Views as a first-class thing (S, foundation)

- A small registry of layouts in `graph_view.gd`: each layout gives every item a target position; the graph
  glides to it (the timeline already works this way with its `tl` targets).
- The Timeline toggle becomes a **view picker** in the filter bar (Zones, Timeline, then the new ones).
- No visible change beyond the picker. Every later loop plugs in here.
- Tests: switching layouts keeps positions, selection and filters; the existing timeline tests still pass.

**Done (2026-11-10).** `GraphView.LAYOUTS`, `_layout_targets`, `_frame_layout`, `_glide_step`; `GraphFilters.views()`,
`view_pick`, `set_view`. The owner said « commence par VIEW-A et enchaine » the same day. Left: capture the How-to
graph guide again (step 7 still shows the old toggle).

### VIEW-B — Saved views (S)

- Save the current layout + filters + camera under a name (« Recettes d'automne », « Projet GD cette
  semaine »); a list to come back in one click; an animated transition between two views.
- Stored locally with the app's settings. The assistant's existing graph actions can open a saved view by name.
- Why: this is what makes views « mouvables »: your own angles on the brain, one click away.

**Done (2026-11-10).** « ★ Views » in the filter bar; `GraphFilters.saved_views / store_view / find_view /
forget_view`, `Brain.save_graph_view / open_graph_view`, `GraphView.view_center`. Left: the assistant opening a
saved view by name (an engine tool and its words), and a How-to step.

### VIEW-C — Focus view (S)

- One item at the centre, its neighbours on rings at 1, 2 and 3 hops; everything else fades out. Click a
  neighbour to make it the new centre; a breadcrumb to walk back.
- Uses the neighbour map the graph already keeps. No engine change.
- Why: follow one idea in depth without the noise of the rest.

**Done (2026-11-10).** « Focus » in the picker; `GraphView.set_focus`, `focus_id`, `focus_trail`, `_focus_reach`
(links and related ideas only), `_focus_targets`, `_draw_focus`, `trail_at`. Checked on real screenshots
(`tools/views_shots.gd`). Left: « focus on X » for the assistant, a How-to step, a way in from an item's panel.

### VIEW-D — Timeline+ (S to M)

- A **time cursor** under the timeline: drag it, or press play, and the brain builds itself day by day.
- Lanes by place (today), or by type, theme, or author (you, the Archivist, an MCP client).
- A density strip along the axis (busy weeks stand out); a free date range instead of only 1 / 7 / 30 days.
- The time cursor also works in the Zones view (« the brain as it was on that day »).
- Why: see how an idea was born and grew; the owner's favourite view, pushed further.

**Done (2026-11-10).** « Time » bar (slider, ▶, date and count): `GraphView.set_time_cursor / set_time_fraction /
time_span`, in every view. Lanes by place, type or origin (`GraphView.LANES`, `set_timeline_lanes`), density strip,
cursor line. Date filter: 90 days, a year. Left: lanes by theme and by author (needs the author in the graph's data,
an engine change), a free from/to range, « replay my week » for the assistant, a How-to step.

### VIEW-E — Meaning map (M)

- Items placed by their meaning vector, projected to 2D, whatever place they are filed in. Islands of themes
  appear; items filed far from their meaning neighbours, and lone items, stand out.
- Engine: a new route that returns the 2D coordinates, computed from the stored vectors and cached; recomputed
  when enough items changed. Pure Python first (PCA); a finer projection only if the islands look muddy.
- Why: the Zones view shows how things are *filed*; this one shows what they *mean*.
- Risk: a projection moves when items are added. Keep it stable by anchoring the old points.

### VIEW-F — Layers in 3D (M, optional step toward G)

- The existing 2D graph drawn on planes stacked in space, one plane per period or per place, that you tilt and
  turn. Each plane is the 2D view rendered to a texture (a SubViewport).
- Why: a real 3D feel without a second graph renderer. A cheap test of whether 3D helps in daily use.

### VIEW-G — Constellation 3D (L)

- A true 3D scene beside the 2D graph: places as bodies, items as stars (MultiMesh), links as light filaments,
  an orbit camera and free flight, click to dive to an item.
- The axes mean something: X and Z = meaning (from VIEW-E, with a third coordinate), Y = time. The brain
  becomes a galaxy that rises with the years.
- Reading stays in 2D: diving onto an item « lands » in the 2D view at card or text zoom.
- What must be rebuilt: picking by ray, labels (`Label3D`, a few at a time), the layout in 3D, link drawing.
- Stays in GL Compatibility so it runs on every machine: glow and fog yes, heavy effects no.
- Risks: a second renderer to maintain; labels and readability; performance beyond a few thousand items
  (MultiMesh covers the stars, links need care).

### Also possible, not scheduled

- **Side by side:** two views at once (this month and last month, or two places). M. Easier after VIEW-A.

## Suggested order

A → B → C → D → E, then decide on 3D with the meaning map in hand: F as a cheap trial, or straight to G.
The order changes with the answers below: if the 3D comes first, A → E → G, since G needs E's coordinates.

## Open questions for the owner

1. **Priority:** understand the brain better first (C, D, E), or the wow effect first (G)?
2. **3D:** a daily working view, or mostly a showcase (exploring, demos, the website)? Is a more sober 3D
   acceptable to stay in GL Compatibility?
3. **Timeline:** is it the time axis itself you like, or watching the brain grow? That decides between pushing
   the play cursor (D) and the galaxy where time rises (G).
