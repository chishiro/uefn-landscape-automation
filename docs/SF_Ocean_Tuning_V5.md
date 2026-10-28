# Sidekick Frontier — Ocean Tuning V5

## Read-only discovery

- Ocean actor: `VK Waterbody Ocean C`; `Affects Landscape = OFF` (preserved).
- Water material: `/FortWater/Materials/WaterSurface/M_Water_Ocean_02_NewModel_Inst`.
- Water-zone override: none; the actor uses its owning WaterZone.
- MCP exposes the Ocean actor and material references for reading, but no editable surface-opacity, absorption, scattering, shallow/deep colour, or extinction parameter was exposed on this installed material instance. `finalOpacity` is also not readable.
- The exposed material scalars are `Far Fade Start`, `Far Fade Length`, foam, specular, mask and refraction-bias controls; they are not a safe replacement for true water extinction.
- Therefore: **MCP direct transparency adjustment: not supported/verified.** No Ocean property was changed.

## Human-only recommended adjustment

1. Select **VK Waterbody Ocean C** in the Outliner. In Details, confirm **Affects Landscape** remains off and do not alter Water Height.
2. Inspect **Water Material**. Do not edit `/FortWater/...M_Water_Ocean_02_NewModel_Inst` in place. If the UI permits an island-local Material Instance override, create/select a project-local child instance first.
3. Only if that instance exposes named parameters for **absorption/extinction**, **scattering**, or **shallow/deep water colour**, increase extinction/absorption slightly and make the deep-water colour only modestly darker/cooler. Begin with one small increment, then test from the beach and from offshore.
4. Keep the shallow colour relatively bright. The target is visible beach shallows but reduced visibility of far/offshore seabed; avoid global opacity or darkening that makes the shore murky.
5. If the only exposed parameters match the current list above, stop rather than guessing parameter names. A custom approved water-material workflow is then required.

## Notes

- Underwater post-process material affects the camera while submerged; it is not the primary control for looking through the ocean surface from above.
- `waterBodyPrimaryColor` currently reads `(0.5, 1.0, 1.0, 1.0)` and is documented for water-related FX tuning, not verified as surface transparency.
