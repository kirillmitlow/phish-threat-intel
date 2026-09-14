from typing import Optional
from pydantic import BaseModel, Field


class RenderRequest(BaseModel):
    url: Optional[str] = Field(None, description="URL страницы для рендера")
    html: Optional[str] = Field(None, description="Сырой HTML для рендера")
    screenshot: bool = Field(True, description="Делать ли скриншот")
    task_id: Optional[str] = Field(None, description="Подпапка артефактов (например, sample_5)")
    max_bytes: int = Field(2_000_000, ge=1024, le=10_000_000,
                           description="Лимит тела страницы, байт")

    def model_post_init(self, __context) -> None:
        if not self.url and not self.html:
            raise ValueError("Нужно указать либо 'url', либо 'html'")


class UnpackRequest(BaseModel):
    archive_path: str = Field(..., min_length=1, description="Путь к архиву")
    task_id: str = Field(..., min_length=1, max_length=64,
                         description="Имя подпапки артефактов для распаковки")


class QrExtractRequest(BaseModel):
    image_path: str = Field(..., min_length=1, description="Путь к изображению")
    max_size: int = Field(4096, ge=64, le=8192)


class EvalJsRequest(BaseModel):
    code: str = Field(..., min_length=1, description="JS-сниппет для исполнения")
    timeout: int = Field(10, ge=1, le=60, description="Таймаут исполнения, сек")
    extract_urls: bool = Field(True, description="Искать URL в результате")


class ExtractLinksRequest(BaseModel):
    html: Optional[str] = Field(None, description="Сырой HTML")
    html_path: Optional[str] = Field(None, description="Путь к HTML-файлу на томе")

    def model_post_init(self, __context) -> None:
        if not self.html and not self.html_path:
            raise ValueError("Нужно указать либо 'html', либо 'html_path'")


class RunShellRequest(BaseModel):
    command: str = Field(..., min_length=1, description="Команда для выполнения")
    timeout: int = Field(15, ge=1, le=60, description="Таймаут, сек")


class ExtractDocumentRequest(BaseModel):
    file_path: str = Field(..., min_length=1, description="Путь к документу на томе")


class RenderPdfRequest(BaseModel):
    file_path: str = Field(..., min_length=1, description="Путь к PDF")
    max_pages: int = Field(5, ge=1, le=50, description="Макс. число страниц для рендера")
    task_id: Optional[str] = Field(None, description="Подпапка артефактов")


class DownloadRequest(BaseModel):
    url: str = Field(..., min_length=4, description="http(s)-ссылка на файл")
    task_id: Optional[str] = Field(None, description="Подпапка артефактов")