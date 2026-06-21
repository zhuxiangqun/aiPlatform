u"""Diagram API — LLM-generated draw.io diagrams (zero external deps)."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse, HTMLResponse
from pydantic import BaseModel


router = APIRouter(prefix="/diagrams", tags=["diagrams"])


class DiagramGenerateRequest(BaseModel):
    description: str = ""
    modify_id: str = ""


@router.post("/generate")
async def generate_diagram_api(req: DiagramGenerateRequest):
    from core.harness.syscalls.drawio_gen import generate_diagram, save_diagram, load_diagram
    context = load_diagram(req.modify_id) if req.modify_id else None
    xml = await generate_diagram(req.description, context)
    did = save_diagram(xml)
    return {"diagram_id": did, "viewer_url": f"/diagrams/viewer/{did}", "xml_preview": xml[:300]}


@router.get("")
async def list_diagrams_api():
    from core.harness.syscalls.drawio_gen import list_diagrams
    return {"diagrams": list_diagrams()}


@router.get("/{diagram_id}")
async def get_diagram_xml(diagram_id: str):
    from core.harness.syscalls.drawio_gen import load_diagram
    import asyncio
    xml = await asyncio.to_thread(load_diagram, diagram_id)
    if not xml:
        raise HTTPException(404, f"Diagram '{diagram_id}' not found")
    return PlainTextResponse(xml, media_type="application/xml")


@router.get("/viewer/{diagram_id}")
async def view_diagram(diagram_id: str):
    from core.harness.syscalls.drawio_gen import load_diagram
    import asyncio
    xml = await asyncio.to_thread(load_diagram, diagram_id)
    if not xml:
        raise HTTPException(404, f"Diagram '{diagram_id}' not found")
    html = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<title>{diagram_id}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:100%;height:100%;overflow:hidden}}
iframe{{position:fixed;top:0;left:0;width:100%;height:100%;border:none}}
</style>
</head>
<body>
<script>
var xml={xml!r};
function send(){{document.querySelector('iframe').contentWindow.postMessage(
  JSON.stringify({{action:'load',autosave:0,xml:xml}}),'*');}}
window.addEventListener('message',function(e){{if(e.data=='init')send();}});
document.write('<iframe src=\"https://embed.diagrams.net/?embed=1&ui=min&spin=1\"></iframe>');
setTimeout(send,800);
</script>
</body></html>"""
    return HTMLResponse(html)


@router.delete("/{diagram_id}")
async def delete_diagram_api(diagram_id: str):
    from core.harness.syscalls.drawio_gen import delete_diagram
    ok = delete_diagram(diagram_id)
    if not ok:
        raise HTTPException(404, f"Diagram '{diagram_id}' not found")
    return {"status": "ok"}
