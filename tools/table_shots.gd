extends "res://tools/capture_base.gd"
## Table view screenshots (Loop 37C): tools/showcase.sh table-en with SBGD_CAPTURE_SCRIPT=table_shots
## (SBGD_UI_LANG=fr for French). Four sample recipes written here (our own), no model call.

const RECIPES := [
	["Paella du samedi", 4, 65, 4.6, true, ["375 ml (1 ½ tasse) de riz à paella", "30 ml (2 c. à soupe) d'huile d'olive", "1 oignon, haché",
		"1 boîte de 796 ml de tomates en dés", "454 g de crevettes", "1 pincée de safran", "Sel et poivre"]],
	["Chili de semaine", 6, 50, 4.2, false, ["2 oignons moyens", "1 boîte de 796 ml de tomates en dés", "1 kg de boeuf haché",
		"1 boîte de 540 ml de haricots rouges", "15 ml (1 c. à soupe) de cumin", "Sel"]],
	["Pâté chinois", 4, 80, 5.0, true, ["680 g de pommes de terre", "55 g de beurre", "125 ml de lait", "450 g de boeuf haché",
		"1 oignon, haché", "1 boîte de 540 ml de maïs en crème"]],
	["Soupe aux légumes", 6, 45, 4.0, false, ["2 carottes", "1 oignon", "2 branches de céleri", "1,5 l de bouillon de poulet",
		"1 boîte de 796 ml de tomates en dés"]],
]


func _run() -> void:
	OS.set_environment("SBGD_ASSISTANT_PROVIDER", "showcase")
	boot_env()
	if not await open_brain():
		quit(1)
		return
	for r in RECIPES:
		var n: Dictionary = await app.backend.api.call_api("/brain/notes", true, HTTPClient.METHOD_POST, JSON.stringify({"title": r[0], "body": ""}))
		await app.backend.api.call_api("/brain/items/%s/props" % str((n["data"] as Dictionary)["id"]), true, HTTPClient.METHOD_POST,
			JSON.stringify({"type": "recipe", "props": {"servings": r[1], "total_min": r[2], "rating": r[3], "tried": r[4],
				"category": "Plats principaux" if OS.get_environment("SBGD_UI_LANG") == "fr" else "Main dishes", "ingredients": r[5]}}))
	await b.call("set_view", "table")
	var tv: PanelContainer = b.get("table_view")
	tv.set("type_id", "recipe")
	tv.set("sort_key", "total_min")
	await tv.call("refresh")
	var picked: Dictionary = tv.get("picked")
	var tree: Tree = tv.get("tree")
	for it in tree.get_root().get_children():
		if str((it as TreeItem).get_text(1)).begins_with("Paella") or str((it as TreeItem).get_text(1)).begins_with("Chili"):
			picked[str((it as TreeItem).get_metadata(0))] = true
	await tv.call("refresh")
	calm()
	await pause(1.0)
	await shot("t1-table")
	var dlg: AcceptDialog = tv.call("open_grocery")
	await pause(2.0)
	calm()
	await shot("t2-grocery")
	dlg.hide()
	quit(0)
