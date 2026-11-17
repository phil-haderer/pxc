"""The parked Expand graphs of Krea 2 and MOSS (models.PARKED_EXPAND) stay in the workflows folder but are not offered in
the Workflow list: picked there they counted as a workflow of your own and "Image -> image" appeared (user 29.10.). A
saved state that still points to one gets the chosen model's own workflow back and keeps the model. Stubbed Tk.

    python tests/test_parked_workflows.py
"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_reset_all as ra  # noqa: E402  (installs the Tk stub and a temporary PCCOMFY_HOME)

from pccomfy import models  # noqa: E402


def main():
    assert models.PARKED_WORKFLOWS == {"krea2-turbo-inpaint.json", "moss-image-inpaint.json"}
    app = ra.make()
    for f in models.PARKED_WORKFLOWS:                     # in the folder, as in the repo
        shutil.copy(ra.t.ROOT / "workflows" / f, Path(app.workflows_dir) / f)
    ra.go(app, "flux3", "outpaint")
    app._apply_refresh({})
    values = list(app.cb_workflow["values"])
    assert not set(values) & models.PARKED_WORKFLOWS, values
    assert "flux3-klein-outpaint.json" in values and "krea2-turbo-inpaint.json" not in values
    # the state of 19:01: Flux 3, Expand, a parked graph
    app.v_workflow.set("krea2-turbo-inpaint.json")
    app._apply_refresh({})
    assert app.v_workflow.get() == "flux3-klein-outpaint.json", app.v_workflow.get()
    assert app.v_model.get() == "flux3" and not app._custom_workflow()
    # a workflow of your own still counts as one
    own = Path(app.workflows_dir) / "my-own.json"
    shutil.copy(ra.t.ROOT / "workflows" / "flux3-klein-edit.json", own)
    app._apply_refresh({})
    app.v_workflow.set("my-own.json")
    app._sync_model()
    assert app._custom_workflow() and app.v_model.get() == ""
    # a function clicked before ComfyUI answered (11.11.): the list held only the built-in graph, MiniMax Edit kept the Text
    # to image workflow and the run failed ("no LoadImage node titled pc:image"); the refresh gives the function its own
    ra.go(app, "minimax", "txt2img")
    assert app.v_workflow.get() == "minimax-h3-image-t2i.json", app.v_workflow.get()
    full = list(app.cb_workflow["values"])
    app.cb_workflow["values"] = [ra.t.gui.BUILTIN]
    app.v_mode.set("edit")
    app._on_mode()
    assert app.v_workflow.get() == "minimax-h3-image-t2i.json"      # the old behaviour before the list is there
    app.cb_workflow["values"] = full
    app._apply_refresh({})
    assert app.v_mode.get() == "edit" and app.v_workflow.get() == "minimax-h3-image-edit.json", (app.v_mode.get(), app.v_workflow.get())
    app._apply_refresh({})                                # the right one stays
    assert app.v_workflow.get() == "minimax-h3-image-edit.json"
    print("ALL OK (parked workflows; a function clicked before the workflow list was there)")


if __name__ == "__main__":
    main()
