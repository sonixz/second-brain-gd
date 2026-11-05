class_name CostChart
extends Control
## Daily billed cost, one stacked bar per day, one colour per product.
## Hover a bar for that day's breakdown. Colours follow the product's slot in `groups`.

# Categorical slots, dark-surface steps, fixed order (validated for the app's four themes).
const SERIES := [Color("3987e5"), Color("d95926"), Color("199e70"), Color("c98500"), Color("d55181"), Color("9085e9")]
const GAP := 2.0
const LEFT := 52.0
const BOTTOM := 22.0
const TOP := 8.0

var days: Array = []
var groups: Array = []
var currency := "usd"
var _hover := -1


static func color_for(group: String, all_groups: Array) -> Color:
	if group == "Other":
		return SbTheme.FAINT
	var i := all_groups.find(group)
	return SERIES[i % SERIES.size()] if i >= 0 else SbTheme.FAINT


func _ready() -> void:
	custom_minimum_size = Vector2(0, 220)
	tooltip_text = " "  # enables _get_tooltip
	mouse_filter = Control.MOUSE_FILTER_STOP


func set_data(d: Array, g: Array, cur: String) -> void:
	days = d
	groups = g
	currency = cur
	queue_redraw()


static func money(v: float, cur: String = "usd") -> String:
	var sym := "$" if cur.to_lower() == "usd" else cur.to_upper() + " "
	if v >= 100.0:
		return sym + str(snappedf(v, 1.0)).trim_suffix(".0")
	if v >= 1.0:
		return sym + "%.2f" % v
	return sym + "%.3f" % v if v > 0.0 else sym + "0"


func _nice_max(v: float) -> float:
	if v <= 0.0:
		return 0.01
	var mag := pow(10.0, floor(log(v) / log(10.0)))
	for step in [1.0, 2.0, 2.5, 5.0, 10.0]:
		if v <= step * mag:
			return step * mag
	return 10.0 * mag


func _plot() -> Rect2:
	return Rect2(LEFT, TOP, maxf(10.0, size.x - LEFT - 4.0), maxf(10.0, size.y - TOP - BOTTOM))


func _bar_index(x: float) -> int:
	var r := _plot()
	if days.is_empty() or x < r.position.x or x > r.end.x:
		return -1
	return clampi(int((x - r.position.x) / (r.size.x / days.size())), 0, days.size() - 1)


func _gui_input(event: InputEvent) -> void:
	if event is InputEventMouseMotion:
		var i := _bar_index((event as InputEventMouseMotion).position.x)
		if i != _hover:
			_hover = i
			queue_redraw()


func _notification(what: int) -> void:
	if what == NOTIFICATION_MOUSE_EXIT and _hover != -1:
		_hover = -1
		queue_redraw()


func _get_tooltip(at_position: Vector2) -> String:
	var i := _bar_index(at_position.x)
	if i < 0:
		return ""
	var d: Dictionary = days[i]
	var lines := ["%s — %s" % [str(d.get("day", "")), money(float(d.get("cost", 0.0)), currency)]]
	var split: Dictionary = d.get("by_group", {})
	for g in groups:
		var v := float(split.get(g, 0.0))
		if v > 0.0:
			lines.append("  %s: %s" % [g, money(v, currency)])
	return "\n".join(lines)


func _draw() -> void:
	var font := get_theme_default_font()
	var fs := 11
	var r := _plot()
	var top := 0.0
	for d in days:
		top = maxf(top, float(d.get("cost", 0.0)))
	var vmax := _nice_max(top)
	# Recessive grid: 4 lines with labels on the left.
	for k in range(5):
		var v := vmax * k / 4.0
		var y := r.end.y - r.size.y * k / 4.0
		draw_line(Vector2(r.position.x, y), Vector2(r.end.x, y), Color(SbTheme.BORDER, 0.55 if k > 0 else 1.0), 1.0)
		draw_string(font, Vector2(0, y + 4), money(v, currency), HORIZONTAL_ALIGNMENT_RIGHT, LEFT - 8, fs, SbTheme.MUTED)
	if days.is_empty():
		draw_string(font, Vector2(r.position.x, r.position.y + r.size.y / 2), I18n.t("No data yet"), HORIZONTAL_ALIGNMENT_CENTER,
			r.size.x, 13, SbTheme.MUTED)
		return
	var slot := r.size.x / days.size()
	var w := maxf(2.0, slot - GAP)
	for i in days.size():
		var d: Dictionary = days[i]
		var x := r.position.x + i * slot + GAP / 2.0
		if i == _hover:
			draw_rect(Rect2(x - GAP / 2.0, r.position.y, slot, r.size.y), Color(SbTheme.TEXT, 0.06))
		var y := r.end.y
		var split: Dictionary = d.get("by_group", {})
		var stack: Array = []
		for g in groups:
			var v := float(split.get(g, 0.0))
			if v > 0.0:
				stack.append([g, v])
		for j in stack.size():
			var h := r.size.y * float(stack[j][1]) / vmax
			var seg := Rect2(x, y - h, w, h)
			var col := color_for(str(stack[j][0]), groups)
			if j == stack.size() - 1 and h >= 4.0:
				var sb := StyleBoxFlat.new()
				sb.bg_color = col
				sb.corner_radius_top_left = 3
				sb.corner_radius_top_right = 3
				draw_style_box(sb, seg)
			else:
				draw_rect(seg, col)
			y -= h
			if j < stack.size() - 1 and h > GAP * 2:
				draw_line(Vector2(x, y), Vector2(x + w, y), SbTheme.PANEL, GAP)  # 2px surface gap between segments
		# x labels: first, every 7th, last
		if i == 0 or i == days.size() - 1 or i % 7 == 0:
			var label := str(d.get("day", "")).substr(5)
			draw_string(font, Vector2(x - 14, size.y - 4), label, HORIZONTAL_ALIGNMENT_LEFT, -1, fs, SbTheme.MUTED)
