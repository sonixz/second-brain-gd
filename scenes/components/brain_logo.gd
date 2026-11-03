class_name BrainLogo
extends Control
## Animated knowledge-graph mark: nodes breathe, a pulse travels the edges.

const NODES: Array[Vector2] = [
	Vector2(0.50, 0.50), Vector2(0.24, 0.30), Vector2(0.74, 0.27), Vector2(0.80, 0.66),
	Vector2(0.22, 0.70), Vector2(0.50, 0.86), Vector2(0.50, 0.12), Vector2(0.92, 0.44), Vector2(0.08, 0.48),
]
const EDGES: Array[Vector2i] = [
	Vector2i(0, 1), Vector2i(0, 2), Vector2i(0, 3), Vector2i(0, 4), Vector2i(1, 2), Vector2i(4, 5),
	Vector2i(5, 3), Vector2i(1, 6), Vector2i(6, 2), Vector2i(2, 7), Vector2i(7, 3), Vector2i(1, 8), Vector2i(8, 4),
]

@export var animate := true
var _t := 0.0


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE


func _process(delta: float) -> void:
	if animate and is_visible_in_tree():
		_t += delta
		queue_redraw()


func _draw() -> void:
	var s := minf(size.x, size.y)
	var off := (size - Vector2(s, s)) * 0.5
	var pts: Array[Vector2] = []
	for i in NODES.size():
		var wobble := Vector2(sin(_t * 0.7 + i * 1.3), cos(_t * 0.6 + i * 0.9)) * s * 0.008
		pts.append(off + NODES[i] * s + wobble)
	draw_circle(off + Vector2(s, s) * 0.5, s * 0.46, Color(SbTheme.FOREST, 0.10))
	for e in EDGES:
		draw_line(pts[e.x], pts[e.y], Color(SbTheme.FOREST_LIGHT, 0.55), maxf(1.5, s * 0.012), true)
	# Travelling pulse
	var k := int(_t * 0.8) % EDGES.size()
	var f := fmod(_t * 0.8, 1.0)
	var pe := EDGES[k]
	draw_circle(pts[pe.x].lerp(pts[pe.y], f), s * 0.018, Color(SbTheme.MINT_SOFT, 0.9))
	for i in pts.size():
		var r := s * (0.055 if i == 0 else 0.032 + 0.008 * (i % 3))
		var glow := 0.5 + 0.5 * sin(_t * 1.6 + i)
		draw_circle(pts[i], r * 1.9, Color(SbTheme.MINT, 0.07 + 0.06 * glow))
		draw_circle(pts[i], r, SbTheme.MINT if i == 0 else SbTheme.MINT.lerp(SbTheme.FOREST_LIGHT, 0.35))
