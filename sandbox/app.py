import traceback

from fastapi import FastAPI, HTTPException

from .schemas import (
    RenderRequest,
    UnpackRequest,
    QrExtractRequest,
    EvalJsRequest,
    ExtractLinksRequest,
    RunShellRequest,
    ExtractDocumentRequest,
    RenderPdfRequest,
    DownloadRequest,
)
from .services import (
    renderer,
    qr_reader,
    unpacker,
    js_runner,
    extractor,
    runner,
    documents,
    downloader,
)

app = FastAPI(title="threat-intel-sandbox", docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/ping")
def ping():
    return {"status": "ok", "zone": "sandbox", "pid": __import__("os").getpid()}


@app.post("/render")
def render(req: RenderRequest):
    try:
        payload = req.model_dump()
        result = renderer.render(payload)
        if not result.get("ok"):
            raise HTTPException(status_code=502, detail=result.get("error", "render failed"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"render error: {e}") from e


@app.post("/extract_qr")
def extract_qr(req: QrExtractRequest):
    try:
        result = qr_reader.extract(req.model_dump())
        if not result.get("ok"):
            raise HTTPException(status_code=422, detail=result.get("error", "qr extract failed"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"qr error: {e}") from e


@app.post("/unpack")
def unpack(req: UnpackRequest):
    try:
        result = unpacker.unpack(req.model_dump())
        if not result.get("ok"):
            raise HTTPException(status_code=422, detail=result.get("error", "unpack failed"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"unpack error: {e}") from e


@app.post("/eval_js")
def eval_js(req: EvalJsRequest):
    try:
        result = js_runner.run_js(req.model_dump())
        if not result.get("ok"):
            raise HTTPException(status_code=502, detail=result.get("error", "js eval failed"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"js eval error: {e}") from e


@app.post("/extract_links")
def extract_links(req: ExtractLinksRequest):
    try:
        result = extractor.extract_links(req.model_dump())
        if not result.get("ok"):
            raise HTTPException(status_code=422, detail=result.get("error", "extract links failed"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"extract links error: {e}") from e


@app.post("/run_shell")
def run_shell(req: RunShellRequest):
    try:
        result = runner.run_command(req.model_dump())
        if not result.get("ok"):
            raise HTTPException(status_code=422, detail=result.get("error", "shell run failed"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"shell error: {e}") from e


@app.post("/extract_document")
def extract_document(req: ExtractDocumentRequest):
    try:
        result = documents.extract_document(req.model_dump())
        if not result.get("ok"):
            raise HTTPException(status_code=422, detail=result.get("error", "doc extract failed"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"doc extract error: {e}") from e


@app.post("/render_pdf")
def render_pdf(req: RenderPdfRequest):
    try:
        result = documents.render_pdf_to_png(req.model_dump())
        if not result.get("ok"):
            raise HTTPException(status_code=422, detail=result.get("error", "render pdf failed"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"render pdf error: {e}") from e


@app.post("/download")
def download_file(req: DownloadRequest):
    try:
        result = downloader.download(req.model_dump())
        if not result.get("ok"):
            raise HTTPException(status_code=422, detail=result.get("error", "download failed"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"download error: {e}") from e