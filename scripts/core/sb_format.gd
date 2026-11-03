class_name SbFormat
extends RefCounted

const NA := "Not available"


static func bytes(value: Variant) -> String:
	if value == null:
		return NA
	return String.humanize_size(int(value))


static func duration(seconds: Variant) -> String:
	if seconds == null:
		return NA
	var s := int(seconds)
	if s < 60:
		return "%d s" % s
	if s < 3600:
		return "%d min %02d s" % [s / 60, s % 60]
	return "%d h %02d min" % [s / 3600, (s % 3600) / 60]


## ISO-8601 UTC ("2026-11-03T00:55:55.859Z") to local "HH:MM:SS" or full date.
static func local_time(iso: Variant, with_date: bool = false) -> String:
	if iso == null or str(iso) == "":
		return NA
	var s := str(iso)
	var unix := Time.get_unix_time_from_datetime_string(s.substr(0, 19))
	var bias: int = Time.get_time_zone_from_system().get("bias", 0)
	var local := Time.get_datetime_dict_from_unix_time(unix + bias * 60)
	var hms := "%02d:%02d:%02d" % [local["hour"], local["minute"], local["second"]]
	if with_date:
		return "%04d-%02d-%02d %s" % [local["year"], local["month"], local["day"], hms]
	return hms


static func value_or_na(value: Variant, suffix: String = "") -> String:
	if value == null:
		return NA
	return number(value) + suffix


## JSON numbers arrive as floats in Godot; show whole numbers without ".0".
static func number(value: Variant) -> String:
	if value is float and is_equal_approx(value, roundf(value)) and absf(value) < 1e15:
		return str(int(value))
	return str(value)
