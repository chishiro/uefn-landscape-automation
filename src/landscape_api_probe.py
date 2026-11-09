"""Read-only inspection of exposed Unreal/UEFN Python Landscape symbols.

Optional diagnostic ONLY; not required for offline heightmap generation.
Run in an editor environment that exposes the `unreal` module, for example
by pasting: exec(open(r"<absolute-path-to-this-file>", encoding="utf-8").read())

This file does not modify, import, save, load, or create any editor assets.
"""
import unreal

SYMBOLS = (
    "LandscapeEditorObject", "LandscapeEditorSubsystem", "LandscapeSubsystem",
    "LandscapeProxy", "Landscape", "LandscapeStreamingProxy",
    "LandscapeBlueprintLibrary", "EditorLevelLibrary", "EditorActorSubsystem",
    "LevelEditorSubsystem",
)
KEYWORDS = ("landscape", "import", "height", "heightmap", "transform",
            "location", "create", "spawn", "actor")


def relevant_members(symbol):
    names = []
    for name in dir(symbol):
        if any(key in name.lower() for key in KEYWORDS):
            try:
                val = getattr(symbol, name)
                kind = "callable" if callable(val) else "property"
            except Exception as exc:
                kind = "unreadable:" + type(exc).__name__
            names.append((name, kind))
    return names


print("[LANDSCAPE_PROBE] START read_only=true")
print("[LANDSCAPE_PROBE] Names exposed by this installed Unreal binding, not permission to edit.")
for name in SYMBOLS:
    symbol = getattr(unreal, name, None)
    if symbol is None:
        print(f"[LANDSCAPE_PROBE] SYMBOL={name} EXPOSED=false")
        continue
    print(f"[LANDSCAPE_PROBE] SYMBOL={name} EXPOSED=true TYPE={type(symbol).__name__}")
    for member, kind in relevant_members(symbol):
        print(f"[LANDSCAPE_PROBE] MEMBER={name}.{member} KIND={kind}")
print("[LANDSCAPE_PROBE] END")
