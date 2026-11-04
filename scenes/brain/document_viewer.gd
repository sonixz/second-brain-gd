class_name DocumentViewer
extends Control
## Full-screen view of a kept original (Loop 12): PDF pages rendered by the engine, or an image;
## HTML, .docx and text files open in a reading view of their full text.
## Wheel = zoom around the cursor, drag = move, ←/→ or PageUp/PageDown = page, + / − / 0 = zoom,
## Esc = close. Sharper pages are fetched as you zoom in.

signal closed

var app: SbApp
var doc: Dictionary = {}
var page := 1
var zoom := 1.0
var offset := Vector2.ZERO
var textures: Dictionary = {}     # "page:width" -> Texture2D
var _pending: Dictionary = {}
var _drag := false
var title_label: Label
var page_label: Label
var hint_label: Label
var last_opened_original := ""     # tests: what « ouvre l'original » would open
var page_controls: Array[Control] = []  # hidden in the reading view
var reader: ScrollContainer        # the reading view (mode "text")
var reader_text: RichTextLabel
var font_size := 18


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)  # once in the tree, so it covers the whole screen


func setup(a: SbApp) -> DocumentViewer:
	app = a
	mouse_filter = Control.MOUSE_FILTER_STOP
	focus_mode = Control.FOCUS_ALL
	visible = false
	var bar := PanelContainer.new()
	bar.theme_type_variation = "Glass"
	bar.set_anchors_and_offsets_preset(Control.PRESET_TOP_WIDE)
	bar.offset_left = 24
	bar.offset_right = -24
	bar.offset_top = 16
	add_child(bar)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 10)
	bar.add_child(row)
	title_label = Label.new()
	title_label.theme_type_variation = "Heading"
	title_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	title_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	title_label.clip_text = true
	row.add_child(title_label)
	for spec in [["◀", "Previous page (←)", func() -> void: go_page(page - 1)],
			["▶", "Next page (→)", func() -> void: go_page(page + 1)]]:
		var b := Button.new()
		b.text = str(spec[0])
		b.tooltip_text = str(spec[1])
		b.pressed.connect(spec[2] as Callable)
		row.add_child(b)
		page_controls.append(b)
	page_label = Label.new()
	page_label.theme_type_variation = "Muted"
	row.add_child(page_label)
	page_controls.append(page_label)
	for spec in [["−", "Zoom out (−)", func() -> void: set_zoom(zoom / 1.4)], ["Fit", "Fit the page (0)", func() -> void: fit()],
			["+", "Zoom in (+)", func() -> void: set_zoom(zoom * 1.4)]]:
		var b := Button.new()
		b.text = str(spec[0])
		b.tooltip_text = str(spec[1])
		b.theme_type_variation = "GhostButton"
		b.pressed.connect(spec[2] as Callable)
		row.add_child(b)
	var orig := Button.new()
	orig.text = "Open original"
	orig.tooltip_text = "Open the kept file in your usual app (PDF reader, image viewer, browser)"
	orig.pressed.connect(open_original)
	row.add_child(orig)
	var close := Button.new()
	close.text = "✕"
	close.tooltip_text = "Close (Esc)"
	close.theme_type_variation = "GhostButton"
	close.pressed.connect(hide_viewer)
	row.add_child(close)
	hint_label = Label.new()
	hint_label.theme_type_variation = "Muted"
	hint_label.set_anchors_and_offsets_preset(Control.PRESET_CENTER_BOTTOM)
	hint_label.offset_top = -40
	hint_label.offset_left = -300
	hint_label.offset_right = 300
	hint_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	hint_label.text = "Wheel to zoom · drag to move · ← → pages · Esc to close"
	add_child(hint_label)
	reader = ScrollContainer.new()
	reader.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	reader.offset_top = 84
	reader.offset_bottom = -56
	reader.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	reader.visible = false
	add_child(reader)
	var center := CenterContainer.new()
	center.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	reader.add_child(center)
	var sheet := PanelContainer.new()
	sheet.theme_type_variation = "Glass"
	center.add_child(sheet)
	reader_text = RichTextLabel.new()
	reader_text.bbcode_enabled = false
	reader_text.fit_content = true
	reader_text.selection_enabled = true
	reader_text.custom_minimum_size = Vector2(820, 0)
	reader_text.add_theme_font_size_override("normal_font_size", font_size)
	reader_text.add_theme_constant_override("line_separation", 6)
	sheet.add_child(reader_text)
	return self


func is_text() -> bool:
	return str(doc.get("mode", "pages")) == "text"


## Opens the original of a source (its id comes from an item's "source").
func open(source_id: String, at_page: int = 1) -> bool:
	var res := await app.backend.api.call_api("/sources/%s/document" % source_id)
	if not res["ok"]:
		return false
	doc = res["data"]
	if not bool(doc.get("viewable", false)):
		return false
	if is_text():
		var t := await app.backend.api.call_api("/sources/%s/text" % source_id)
		if not t["ok"]:
			return false
		reader_text.text = str((t["data"] as Dictionary).get("text", ""))
		reader.scroll_vertical = 0
	reader.visible = is_text()
	for c in page_controls:
		c.visible = not is_text()
	hint_label.text = ("Scroll to read · + / − text size · Esc to close" if is_text()
		else "Wheel to zoom · drag to move · ← → pages · Esc to close")
	textures.clear()
	_pending.clear()
	page = clampi(at_page, 1, maxi(1, int(doc.get("pages", 1))))
	title_label.text = str(doc.get("title", ""))
	visible = true
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	if get_parent() is Control:
		position = Vector2.ZERO
		size = (get_parent() as Control).size
	grab_focus()
	fit()
	_update_label()
	return true


func hide_viewer() -> void:
	visible = false
	closed.emit()


func pages() -> int:
	return maxi(1, int(doc.get("pages", 1)))


func go_page(n: int) -> void:
	page = clampi(n, 1, pages())
	offset = Vector2.ZERO
	_update_label()
	queue_redraw()


func fit() -> void:
	zoom = 1.0
	offset = Vector2.ZERO
	queue_redraw()


func set_zoom(z: float, anchor: Variant = null) -> void:
	if is_text():  # the reading view zooms its text instead
		font_size = clampi(roundi(font_size * (1.15 if z > zoom else 1.0 / 1.15)), 12, 40)
		reader_text.add_theme_font_size_override("normal_font_size", font_size)
		reader_text.custom_minimum_size.x = clampf(820.0 * font_size / 18.0, 600.0, size.x - 80.0)
		return
	var old := zoom
	zoom = clampf(z, 0.25, 8.0)
	if anchor is Vector2:  # keep the point under the cursor where it is
		var c := size * 0.5 + offset
		offset += ((anchor as Vector2) - c) * (1.0 - zoom / old)
	queue_redraw()


func open_original() -> void:
	var p := str(doc.get("original_path", ""))
	if p == "" or p == "<null>":
		return
	last_opened_original = p
	if OS.get_environment("SBGD_TEST_NO_SHELL") != "1":
		OS.shell_open(p)


func _update_label() -> void:
	page_label.text = "Page %d / %d" % [page, pages()] if str(doc.get("kind", "")) == "pdf" else "Image"


## The page's rectangle at fit zoom: as large as the area allows, below the bar.
func _fit_rect(tex_size: Vector2) -> Rect2:
	var area := Rect2(Vector2(24, 84), size - Vector2(48, 140))
	var aspect := tex_size.x / maxf(1.0, tex_size.y) if tex_size != Vector2.ZERO else 0.72
	var h := area.size.y
	var w := h * aspect
	if w > area.size.x:
		w = area.size.x
		h = w / aspect
	return Rect2(area.position + (area.size - Vector2(w, h)) * 0.5, Vector2(w, h))


func current_texture() -> Texture2D:
	var best: Texture2D = null
	var best_w := 0
	for key in textures:
		var parts := str(key).split(":")
		if int(parts[0]) == page and int(parts[1]) > best_w:
			best = textures[key]
			best_w = int(parts[1])
	return best


func _wanted_width() -> int:
	var tex := current_texture()
	var r := _fit_rect(tex.get_size() if tex else Vector2.ZERO)
	return int(r.size.x * zoom)


func _ensure_page() -> void:
	if doc.is_empty():
		return
	var want := _wanted_width()
	var have := 0
	for key in textures:
		var parts := str(key).split(":")
		if int(parts[0]) == page:
			have = maxi(have, int(parts[1]))
	if have >= want * 0.8 and have > 0:
		return
	var w := 320
	for b in [320, 640, 1024, 1600, 2400]:
		w = b
		if b >= want:
			break
	var key := "%d:%d" % [page, w]
	if _pending.has(key) or textures.has(key):
		return
	_pending[key] = true
	var res := await app.backend.api.call_api("/sources/%s/page/%d?width=%d" % [str(doc.get("id", "")), page, w], true,
		HTTPClient.METHOD_GET, "", true)
	_pending.erase(key)
	if res["ok"]:
		var tex := texture_from(res["bytes"], str(doc.get("mime", "image/png")))
		if tex != null:
			textures[key] = tex
			queue_redraw()


static func texture_from(data: PackedByteArray, mime: String) -> Texture2D:
	var img := Image.new()
	var err := ERR_FILE_UNRECOGNIZED
	if data.size() >= 8 and data[0] == 0x89 and data[1] == 0x50:
		err = img.load_png_from_buffer(data)
	elif data.size() >= 3 and data[0] == 0xFF and data[1] == 0xD8:
		err = img.load_jpg_from_buffer(data)
	elif mime == "image/webp":
		err = img.load_webp_from_buffer(data)
	if err != OK:
		return null
	return ImageTexture.create_from_image(img)


func _draw() -> void:
	draw_rect(Rect2(Vector2.ZERO, size), Color(SbTheme.BG, 0.96))
	if is_text():
		return
	var tex := current_texture()
	var base := _fit_rect(tex.get_size() if tex else Vector2.ZERO)
	var rect := Rect2(base.get_center() + offset - base.size * zoom * 0.5, base.size * zoom)
	draw_rect(rect.grow(1.0), Color(0, 0, 0, 0.35))
	if tex != null:
		draw_texture_rect(tex, rect, false)
	else:
		draw_rect(rect, Color(1, 1, 1, 0.92))
		draw_string(get_theme_default_font(), rect.get_center() - Vector2(40, 0), "Loading…", HORIZONTAL_ALIGNMENT_LEFT, -1, 16,
			Color(0, 0, 0, 0.6))
	_ensure_page()


func _gui_input(event: InputEvent) -> void:
	if is_text() and event is InputEventKey and (event as InputEventKey).pressed:
		match (event as InputEventKey).keycode:
			KEY_ESCAPE:
				hide_viewer()
			KEY_EQUAL, KEY_PLUS, KEY_KP_ADD:
				set_zoom(zoom * 1.4)
			KEY_MINUS, KEY_KP_SUBTRACT:
				set_zoom(zoom / 1.4)
			KEY_DOWN, KEY_PAGEDOWN:
				reader.scroll_vertical += 400 if (event as InputEventKey).keycode == KEY_PAGEDOWN else 60
			KEY_UP, KEY_PAGEUP:
				reader.scroll_vertical -= 400 if (event as InputEventKey).keycode == KEY_PAGEUP else 60
		accept_event()
		return
	if event is InputEventMouseButton:
		var mb := event as InputEventMouseButton
		if mb.pressed and mb.button_index == MOUSE_BUTTON_WHEEL_UP:
			set_zoom(zoom * 1.15, mb.position)
		elif mb.pressed and mb.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			set_zoom(zoom / 1.15, mb.position)
		elif mb.button_index == MOUSE_BUTTON_LEFT:
			_drag = mb.pressed
		accept_event()
	elif event is InputEventMouseMotion and _drag:
		offset += (event as InputEventMouseMotion).relative
		queue_redraw()
		accept_event()
	elif event is InputEventKey and (event as InputEventKey).pressed:
		match (event as InputEventKey).keycode:
			KEY_ESCAPE:
				hide_viewer()
			KEY_RIGHT, KEY_PAGEDOWN, KEY_DOWN:
				go_page(page + 1)
			KEY_LEFT, KEY_PAGEUP, KEY_UP:
				go_page(page - 1)
			KEY_EQUAL, KEY_PLUS, KEY_KP_ADD:
				set_zoom(zoom * 1.4)
			KEY_MINUS, KEY_KP_SUBTRACT:
				set_zoom(zoom / 1.4)
			KEY_0, KEY_KP_0:
				fit()
		accept_event()
