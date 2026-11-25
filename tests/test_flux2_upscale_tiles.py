# tags: upscale, flux2, workflows
"""Flux 2 Upscale always runs in tiles (user 12.11.; upscale stage round 9.11.: 2 of 3 good with tiles, 0 of 3 without): no
"Tiles" switch in the window, the tile graph is the base of the workflow, a saved "Tiles off" is ignored, and without
ComfyUI-KJNodes (Color Match) the model Flux 2 is locked. Refine keeps its own graph without tiles.

    python tests/test_flux2_upscale_tiles.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from pccomfy import models, workflows  # noqa: E402

UP = ROOT / "workflows" / "flux2-klein-upscale.json"
REFINE = ROOT / "workflows" / "flux2-klein-refine.json"


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def test_no_stage_and_the_tile_graph_is_the_base():
    assert not workflows.stage_info(load(UP)) and not workflows.stage_switches(load(UP))     # nothing to switch off
    up = models.BY_KEY["flux2"].modes["upscale"]
    assert up.workflow == "flux2-klein-upscale.json" and not up.stage_row and "stage_on" not in up.settings
    assert any(n["class_type"] == "SplitImageToTileList" for n in load(UP).values())
    assert models.BY_KEY["flux2"].modes["refine"].workflow == "flux2-klein-refine.json"      # Refine: unchanged, no tiles, no stage
    assert not workflows.stage_info(load(REFINE))
    assert not any(n["class_type"] == "SplitImageToTileList" for n in load(REFINE).values())


def test_saved_tiles_off_is_ignored():
    """A request that comes from old saved settings (stage_on False, a stage id in stages_off) still sends the tiles graph."""
    from pccomfy.bridge import Bridge, Request
    b = Bridge.__new__(Bridge)
    p = workflows.GenParams(prompt="", seed=1)
    p.extra["megapixels"] = 3.0
    for kw in (dict(stage_on=False), dict(stage_on=True, stages_off=["100", "170"]), dict(stage_on=False, stages_off=["100"])):
        req = Request(mode="upscale", workflow=str(UP), **kw)
        g, _out = b._graph(req, p, "pic.png", None, wf=str(UP))
        classes = {n["class_type"] for n in g.values()}
        assert {"SplitImageToTileList", "ImageMergeTileList", "ColorMatch"} <= classes, kw


def test_window_has_no_tiles_switch_and_ignores_saved_off():
    import test_settings_ui as su
    app = su.make_app()
    app._apply_refresh({"_detect": True, "_inv": su.inventory.Inventory(su.td.full_lists(), su.NODES)})
    app.v_model.set("flux2")
    app.v_mode.set("upscale")
    app._on_model()
    assert not app._stages() and not app.f_stage_row.winfo_manager()
    assert app.v_workflow.get() == "flux2-klein-upscale.json"
    app._apply_settings({"stage_on": False, "stage2_on": False})            # settings saved while Tiles was a switch
    req = app._request()
    assert req.stage_on and not req.stages_off                               # the request carries no way to switch tiles off
    app.v_mode.set("refine")
    app._on_mode()
    assert app.v_workflow.get() == "flux2-klein-refine.json"


def test_flux2_is_locked_without_kjnodes():
    import test_settings_ui as su
    manifest, inventory = su.manifest, su.inventory
    assert manifest.mode_nodes("flux2", "upscale") == ("ColorMatch",) and not manifest.mode_nodes("flux2", "refine")
    full = inventory.Inventory(su.td.full_lists(), su.NODES)
    assert full.tab_status("flux2").state == "ready"
    nope = inventory.Inventory(su.td.full_lists(), su.NODES - {"ColorMatch"})
    st = nope.tab_status("flux2")
    assert st.state == "missing" and "ColorMatch" in st.nodes, st            # the whole model, like a missing file
    assert nope.mode_status("flux2", "refine").state == "ready"               # only Upscale needs the pack
    assert manifest.node_pack("ColorMatch")[0] == "ComfyUI-KJNodes"
    assert nope.tab_status("qwen").state == "ready" and nope.tab_status("fibo").state == "ready"
    assert any("ComfyUI-KJNodes" in l for l in inventory.preflight(nope, "flux2", "upscale"))
    # nodes not read (ComfyUI unreachable): no false alarm
    assert inventory.Inventory(su.td.full_lists(), None).tab_status("flux2").state == "ready"


def test_runs_tile_by_tile_and_matches_the_colours():
    g = load(UP)
    by = {k: n["class_type"] for k, n in g.items()}
    split = next(k for k, c in by.items() if c == "SplitImageToTileList")
    merge = next(k for k, c in by.items() if c == "ImageMergeTileList")
    cm = next(k for k, c in by.items() if c == "ColorMatch")
    enc = next(k for k, c in by.items() if c == "VAEEncode")
    dec = next(k for k, c in by.items() if c == "VAEDecode")
    out = next(k for k, n in g.items() if n["_meta"]["title"].startswith("pc:output"))
    scaled = next(k for k, n in g.items() if n["_meta"]["title"].startswith("pc:upscale"))
    assert g[split]["inputs"]["image"] == [scaled, 0] and g[enc]["inputs"]["pixels"] == [split, 0]
    assert g[merge]["inputs"]["image_list"] == [dec, 0] and g[cm]["inputs"]["image_target"] == [merge, 0]
    assert g[out]["inputs"]["images"] == [cm, 0]
    for cls in ("EmptyFlux2LatentImage", "Flux2Scheduler"):    # latent and scheduler at the size of one tile
        n = next(n for n in g.values() if n["class_type"] == cls)
        assert n["inputs"]["width"] == [g[split]["inputs"]["tile_width"][0], 1]
    links = [v for n in g.values() for v in n["inputs"].values() if isinstance(v, list) and len(v) == 2 and isinstance(v[1], int)]
    assert all(str(v[0]) in g for v in links)
    f3 = load(ROOT / "workflows" / "flux3-klein-upscale.json")       # the same tile rule as Flux 3 Upscale (about 1280 px + 128 overlap)
    assert g["170"]["inputs"]["expression"] == f3["170"]["inputs"]["expression"] and g["100"]["inputs"]["overlap"] == 128


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
