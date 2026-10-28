"""Read-only UEFN Landscape Python API probe.

This script never creates, imports, edits, saves, selects, or loads project content.
It only inspects names already exposed by the current `unreal` Python module.
Run from UEFN: Output Log -> Python, then:
    exec(open(r"C:\\Users\\chishiro\\Documents\\SF_Forest_Heightmap_Phase2\\landscape_api_probe.py", encoding="utf-8").read())
"""

import unreal

SYMBOLS = (
    "LandscapeEditorObject",
    "LandscapeEditorSubsystem",
    "LandscapeSubsystem",
    "LandscapeProxy",
    "Landscape",
    "LandscapeStreamingProxy",
    "LandscapeBlueprintLibrary",
    "EditorLevelLibrary",
    "EditorActorSubsystem",
    "LevelEditorSubsystem",
)
KEYWORDS = ("landscape", "import", "height", "heightmap", "transform", "location", "create", "spawn", "actor")

def relevant_members(symbol):
    names = []
    for name in dir(symbol):
        if any(key in name.lower() for key in KEYWORDS):
            try:
                value = getattr(symbol, name)
                kind = "callable" if callable(value) else "property"
            except Exception as exc:
                kind = "unreadable:" + type(exc).__name__
            names.append((name, kind))
    return names

print("[SF_LANDSCAPE_PROBE] START read_only=true")
print("[SF_LANDSCAPE_PROBE] Unreal Python binding inspection only; no import or level mutation is performed.")
for symbol_name in SYMBOLS:
    symbol = getattr(unreal, symbol_name, None)
    if symbol is None:
        print(f"[SF_LANDSCAPE_PROBE] SYMBOL={symbol_name} EXPOSED=false")
        continue
    print(f"[SF_LANDSCAPE_PROBE] SYMBOL={symbol_name} EXPOSED=true TYPE={type(symbol).__name__}")
    members = relevant_members(symbol)
    if members:
        for name, kind in members:
            print(f"[SF_LANDSCAPE_PROBE] MEMBER={symbol_name}.{name} KIND={kind}")
    else:
        print(f"[SF_LANDSCAPE_PROBE] MEMBER={symbol_name} NONE_MATCHING")

print("[SF_LANDSCAPE_PROBE] INTERPRETATION:")
print("[SF_LANDSCAPE_PROBE] A listed member is Python-public in this UEFN build only.")
print("[SF_LANDSCAPE_PROBE] It does not prove a Landscape import call is supported, allowed by validation, or safe for this project.")
print("[SF_LANDSCAPE_PROBE] END")
