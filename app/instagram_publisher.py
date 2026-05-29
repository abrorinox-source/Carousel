from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from urllib.parse import quote

import requests
from dotenv import load_dotenv

GRAPH_BASE_URL = "https://graph.facebook.com/v25.0"


class InstagramPublishError(RuntimeError):
    pass


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise InstagramPublishError(f"{name} is missing in .env")
    return value


def _safe_caption(caption_path: Path) -> str:
    if not caption_path.exists():
        return ""
    return caption_path.read_text(encoding="utf-8")[:2200]


def _copy_images_to_public_dir(image_paths: list[Path], run_dir: Path) -> list[str]:
    upload_dir = Path(_required_env("PUBLIC_UPLOAD_DIR"))
    public_base_url = _required_env("PUBLIC_BASE_URL").rstrip("/")

    public_run_name = run_dir.name
    target_dir = upload_dir / public_run_name
    target_dir.mkdir(parents=True, exist_ok=True)

    public_urls: list[str] = []
    for image_path in image_paths:
        target_path = target_dir / image_path.name
        shutil.copy2(image_path, target_path)
        public_urls.append(f"{public_base_url}/{quote(public_run_name)}/{quote(image_path.name)}")

    return public_urls


def _graph_post(path: str, data: dict) -> dict:
    url = f"{GRAPH_BASE_URL}/{path.lstrip('/')}"
    response = requests.post(url, data=data, timeout=120)
    payload = response.json()
    if response.status_code >= 400 or "error" in payload:
        raise InstagramPublishError(f"Graph API error: {payload}")
    return payload


def _graph_get(path: str, params: dict) -> dict:
    url = f"{GRAPH_BASE_URL}/{path.lstrip('/')}"
    response = requests.get(url, params=params, timeout=120)
    payload = response.json()
    if response.status_code >= 400 or "error" in payload:
        raise InstagramPublishError(f"Graph API error: {payload}")
    return payload


def _wait_for_container(creation_id: str, access_token: str, timeout_seconds: int = 180) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        payload = _graph_get(
            creation_id,
            {"fields": "status_code", "access_token": access_token},
        )
        status = payload.get("status_code")
        if status in {"FINISHED", "PUBLISHED"}:
            return
        if status in {"ERROR", "EXPIRED"}:
            raise InstagramPublishError(f"Container failed with status: {status}")
        time.sleep(5)

    raise InstagramPublishError("Timed out waiting for Instagram media container")


def publish_carousel(image_paths: list[Path], caption_path: Path, run_dir: Path) -> dict:
    load_dotenv()

    access_token = _required_env("META_ACCESS_TOKEN")
    ig_user_id = _required_env("IG_USER_ID")
    caption = _safe_caption(caption_path)
    image_urls = _copy_images_to_public_dir(image_paths, run_dir)

    if len(image_urls) < 2:
        raise InstagramPublishError("Instagram carousel needs at least 2 images")
    if len(image_urls) > 10:
        image_urls = image_urls[:10]

    child_ids: list[str] = []
    for image_url in image_urls:
        payload = _graph_post(
            f"{ig_user_id}/media",
            {
                "image_url": image_url,
                "is_carousel_item": "true",
                "access_token": access_token,
            },
        )
        creation_id = payload.get("id")
        if not creation_id:
            raise InstagramPublishError(f"No creation id returned for image: {image_url}")
        _wait_for_container(creation_id, access_token)
        child_ids.append(creation_id)

    carousel_payload = _graph_post(
        f"{ig_user_id}/media",
        {
            "media_type": "CAROUSEL",
            "children": ",".join(child_ids),
            "caption": caption,
            "access_token": access_token,
        },
    )
    carousel_id = carousel_payload.get("id")
    if not carousel_id:
        raise InstagramPublishError("No carousel container id returned")

    _wait_for_container(carousel_id, access_token)

    publish_payload = _graph_post(
        f"{ig_user_id}/media_publish",
        {
            "creation_id": carousel_id,
            "access_token": access_token,
        },
    )

    return {
        "instagram_media_id": publish_payload.get("id"),
        "carousel_container_id": carousel_id,
        "image_urls": image_urls,
    }
