extends "res://tools/capture_base.gd"
## Screenshots of the three themes added on 2026-11-07 (Terminal, Paper, Neon): the whole Brain from afar in each.
## Run with: SBGD_CAPTURE_SCRIPT=theme_shots tools/showcase.sh themes


func _run() -> void:
	OS.set_environment("SBGD_ASSISTANT_PROVIDER", "showcase")
	boot_env()
	if not await open_brain():
		quit(1)
		return
	for theme in ["terminal", "paper", "neon"]:
		app.set_theme_choice(theme)  # a theme switch rebuilds the brain screen
		await pause(6.0)
		b = app.current()
		g = b.get("graph")
		g.zoom_to(0.5, Vector2(-60, 0), 0.3)
		await pause(3.0)
		calm()
		await shot(theme)
	await finish()
