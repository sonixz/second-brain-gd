extends SceneTree
## Graph performance bench (Loop 15): synthetic brains of N items, time per layout step and per draw.
##   godot --headless --path . --script res://tools/graph_bench.gd
func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	var sizes := [500, 2000, 5000]
	for n in sizes:
		var g := GraphView.new()
		g.size = Vector2(1280, 800)
		root.add_child(g)
		await process_frame
		var nodes: Array = []
		var edges: Array = []
		var places := maxi(4, n / 150)
		for p in places:
			nodes.append({"id": "space:p%d" % p, "type": "space", "label": "Place %d" % p, "kind": "resource", "weight": n / places})
		for i in n:
			var sid := "p%d" % (i % places)
			nodes.append({"id": "n%d" % i, "type": "note", "label": "Item %d" % i, "kind": "note", "space_id": sid,
				"created_at": "2026-%02d-%02dT10:00:00Z" % [1 + i % 11, 1 + i % 27]})
			edges.append({"from": "n%d" % i, "to": "space:" + sid, "type": "space"})
			if i > 0 and i % 3 == 0:
				edges.append({"from": "n%d" % i, "to": "n%d" % (i - 1), "type": "link"})
		g.set_graph({"nodes": nodes, "edges": edges})
		var t := Time.get_ticks_usec()
		for k in 5:
			g._simulate(1.0)
		var sim_ms := (Time.get_ticks_usec() - t) / 5000.0
		g.zoom = 1.0
		t = Time.get_ticks_usec()
		for k in 5:
			g.queue_redraw()
			await process_frame
		var frame_ms := (Time.get_ticks_usec() - t) / 5000.0
		g.heat = 0.0
		var draws := 0.0
		for z in [0.3, 1.0, 3.0]:
			g.zoom = z
			g.queue_redraw()
			await process_frame
			g.queue_redraw()
			await process_frame
			draws = maxf(draws, g.draw_ms)
			print("  n=%d zoom %.1f draw %.1f ms (dense=%s)" % [n, z, g.draw_ms, g._dense])
		print("BENCH n=%d places=%d  layout step %.1f ms  frame %.1f ms  worst draw %.1f ms" % [n, places, sim_ms, frame_ms, draws])
		g.queue_free()
		await process_frame
	quit()
